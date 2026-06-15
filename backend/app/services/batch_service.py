import json
import os
import re
from datetime import datetime, timezone
from typing import Literal
import math
import random

from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException
from app.services.storage_paths import build_project_prefix, build_project_path


Workspace = Literal["capture", "summaries", "discovery"]

CONTAINER_ENV_MAP = {
    "capture": "AZURE_CAPTURE_CONTAINER",
    "summaries": "AZURE_SUMMARIES_CONTAINER",
    "discovery": "AZURE_DISCOVERY_CONTAINER",
}

DEFAULT_CONTAINER_MAP = {
    "capture": "insyt-capture",
    "summaries": "insyt-summaries",
    "discovery": "insyt-discovery",
}


def get_container_client(workspace: Workspace):
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not connection_string:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    container_name = os.getenv(
        CONTAINER_ENV_MAP[workspace],
        DEFAULT_CONTAINER_MAP[workspace],
    )
    
    print(f"WORKSPACE={workspace} CONTAINER={container_name}")

    service_client = BlobServiceClient.from_connection_string(
        connection_string
    )

    return service_client.get_container_client(container_name)


def list_project_batches(
    workspace: Workspace,
    project_id: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    batch_prefix = build_project_prefix(
        workspace,
        client_id,
        project_id,
        "Batches",
    )
        

    batches = []

    for blob in container.list_blobs(name_starts_with=batch_prefix):
        if not blob.name.endswith(".json"):
            continue

        data = (
            container
            .get_blob_client(blob.name)
            .download_blob()
            .readall()
        )

        batches.append(json.loads(data.decode("utf-8")))

    return {
        "workspace": workspace,
        "client_id": client_id,
        "project_id": project_id,
        "batches": batches,
    }


def list_project_doc_ids(
    workspace: Workspace,
    project_id: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    prefix = build_project_prefix(
        workspace,
        client_id,
        project_id,
        "source/native",
    )

    doc_ids = []

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name

        if name.endswith("/"):
            continue

        filename = name.split("/")[-1]

        if not filename:
            continue

        if filename == ".keep":
            continue

        if filename.lower().endswith(".json"):
            continue

        doc_id = os.path.splitext(filename)[0]
        doc_ids.append(doc_id)

    return sorted(set(doc_ids))


def get_already_batched_doc_ids(
    workspace: Workspace,
    project_id: str,
    level: str,
    client_id: str = "",
):
    existing = list_project_batches(
        workspace,
        project_id,
        client_id,
    )

    already_batched = set()

    for batch in existing["batches"]:
        if batch.get("level") == level:
            already_batched.update(
                batch.get("doc_ids", [])
            )

    return already_batched

def resolve_search_folder_doc_ids(
    workspace: Workspace,
    project_id: str,
    folder_id: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    possible_blob_names = [
        build_project_path(
            workspace,
            client_id,
            project_id,
            "SearchFolders",
            f"{folder_id}.json",
        ),
        build_project_path(
            workspace,
            client_id,
            project_id,
            "SearchFolders",
            folder_id,
            "results.json",
        ),
        build_project_path(
            workspace,
            client_id,
            project_id,
            "SearchFolderResults",
            f"{folder_id}.json",
        ),
        build_project_path(
            workspace,
            client_id,
            project_id,
            "SearchFolderResults",
            folder_id,
            "results.json",
        ),
    ]

    last_error = None

    for blob_name in possible_blob_names:
        try:
            blob_client = container.get_blob_client(blob_name)

            if not blob_client.exists():
                continue

            data = blob_client.download_blob().readall()
            payload = json.loads(data.decode("utf-8"))

            if isinstance(payload, list):
                return sorted(
                    set(
                        str(item.get("doc_id") or item.get("id") or item)
                        for item in payload
                        if item
                    )
                )

            if isinstance(payload, dict):
                results = (
                    payload.get("results")
                    or payload.get("documents")
                    or payload.get("doc_ids")
                    or payload.get("hits")
                    or []
                )

                doc_ids = []

                for item in results:
                    if isinstance(item, str):
                        doc_ids.append(item)
                    elif isinstance(item, dict):
                        doc_id = (
                            item.get("doc_id")
                            or item.get("document_id")
                            or item.get("id")
                        )

                        if doc_id:
                            doc_ids.append(str(doc_id))

                return sorted(set(doc_ids))

        except Exception as e:
            last_error = e

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unable to resolve Search Folder Results for folder_id "
            f"'{folder_id}'. Checked: {possible_blob_names}. "
            f"Last error: {last_error}"
        ),
    )

def calculate_statistical_sample_size(
    population_size: int,
    confidence_level: float,
    margin_of_error: float,
):
    """
    Statistical sample size calculation using:
    n = (Z² × p × (1-p)) / E²

    with finite population correction.

    Defaults:
    p = 0.5 (maximum variability)
    """

    z_scores = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576,
    }

    z = z_scores.get(confidence_level, 1.96)

    p = 0.5
    e = margin_of_error

    initial_n = ((z ** 2) * p * (1 - p)) / (e ** 2)

    corrected_n = (
        initial_n
        / (
            1
            + ((initial_n - 1) / max(population_size, 1))
        )
    )

    return math.ceil(corrected_n)

def load_project_batch(
    workspace: Workspace,
    project_id: str,
    batch_name: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    batch_blob_name = build_project_path(
        workspace,
        client_id,
        project_id,
        "Batches",
        f"{batch_name}.json",
    )

    blob_client = container.get_blob_client(batch_blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source batch not found: {batch_name}",
        )

    return json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )

def create_project_batch(
    workspace: Workspace,
    project_id: str,
    batch_size: int,
    level: str,
    workflow_type: str = "standard",
    created_by: str = "admin",
    search_folder_doc_ids: list[str] | None = None,
    options: dict | None = None,
    client_id: str = "",
):
    if batch_size <= 0:
        raise HTTPException(
            status_code=400,
            detail="Batch size must be greater than zero.",
        )

    if level not in ["1L", "QC", "ALT Workflow", "Statistical QC"]:
        raise HTTPException(
            status_code=400,
            detail="Level must be one of: 1L, QC, ALT Workflow.",
        )
        
    options = options or {}

    if (
        level == "QC"
        and options.get("qc_sampling")
        and options.get("source_batch_id")
    ):
        source_batch_id = str(
            options.get("source_batch_id") or ""
        ).strip()

        source_batch = load_project_batch(
            workspace=workspace,
            project_id=project_id,
            batch_name=source_batch_id,
            client_id=client_id,
        )

        source_status = str(
            source_batch.get("status", "")
        ).lower().replace("_", " ")

        if source_batch.get("level") != "1L":
            raise HTTPException(
                status_code=400,
                detail="QC sampling source must be a 1L batch.",
            )

        if source_status not in [
            "checked out",
            "in progress",
            "completed",
        ]:
            raise HTTPException(
                status_code=400,
                detail="QC sampling source must be In Progress or Completed.",
            )

        source_doc_ids = [
            str(doc_id).strip()
            for doc_id in source_batch.get("doc_ids", [])
            if str(doc_id).strip()
        ]

        if not source_doc_ids:
            raise HTTPException(
                status_code=400,
                detail="Selected source batch has no documents.",
            )

        qc_percent = float(
            options.get("qc_sample_percentage", 10)
        )

        if qc_percent <= 0 or qc_percent > 100:
            raise HTTPException(
                status_code=400,
                detail="QC sample percentage must be between 1 and 100.",
            )

        sample_size = max(
            1,
            math.ceil(len(source_doc_ids) * (qc_percent / 100)),
        )

        sample_size = min(sample_size, len(source_doc_ids))

        eligible_doc_ids = random.sample(
            source_doc_ids,
            sample_size,
        )

        batch_size = sample_size

        options["qc_source_batch_id"] = source_batch_id
        options["qc_source_document_count"] = len(source_doc_ids)
        options["qc_sample_size"] = sample_size

    elif level == "ALT Workflow":
        if not search_folder_doc_ids:
            raise HTTPException(
                status_code=400,
                detail="ALT Workflow requires Search Folder Results or folder IDs.",
            )

        expanded_doc_ids = []

        for item in search_folder_doc_ids:
            if item.startswith("folder:"):
                folder_id = item.replace("folder:", "", 1)

                expanded_doc_ids.extend(
                    resolve_search_folder_doc_ids(
                        workspace,
                        project_id,
                        folder_id,
                        client_id,
                    )
                )
            else:
                expanded_doc_ids.append(item)

        eligible_doc_ids = sorted(set(expanded_doc_ids))

    else:
        all_doc_ids = list_project_doc_ids(
            workspace,
            project_id,
            client_id,
        )

        if level == "1L":
            already_batched = get_already_batched_doc_ids(
                workspace,
                project_id,
                "1L",
                client_id,
            )

            eligible_doc_ids = [
                doc_id
                for doc_id in all_doc_ids
                if doc_id not in already_batched
            ]

        elif level == "QC":
            already_qc_batched = get_already_batched_doc_ids(
                workspace,
                project_id,
                "QC",
                client_id,
            )

            eligible_doc_ids = [
                doc_id
                for doc_id in all_doc_ids
                if doc_id not in already_qc_batched
            ]

        elif level == "Statistical QC":
            already_stat_qc_batched = get_already_batched_doc_ids(
                workspace,
                project_id,
                "Statistical QC",
                client_id,
            )

            eligible_doc_ids = [
                doc_id
                for doc_id in all_doc_ids
                if doc_id not in already_stat_qc_batched
            ]

        else:
            eligible_doc_ids = all_doc_ids

    if level == "Statistical QC":
        confidence_map = {
            "90_10": (0.90, 0.10),
            "90_5": (0.90, 0.05),
            "95_10": (0.95, 0.10),
            "95_5": (0.95, 0.05),
            "99_5": (0.99, 0.05),
        }

        confidence_preset = (
            options.get("confidence_preset", "95_5")
            if options
            else "95_5"
        )

        confidence_level, margin_of_error = confidence_map.get(
            confidence_preset,
            (0.95, 0.05),
        )

        calculated_sample_size = calculate_statistical_sample_size(
            population_size=len(eligible_doc_ids),
            confidence_level=confidence_level,
            margin_of_error=margin_of_error,
        )

        sample_size = min(
            calculated_sample_size,
            len(eligible_doc_ids),
        )

        selected_doc_ids = random.sample(
            eligible_doc_ids,
            sample_size,
        )

    else:
        selected_doc_ids = eligible_doc_ids[:batch_size]

    if level == "Statistical QC":
        batch_chunks = [selected_doc_ids]
    else:
        batch_chunks = [
            eligible_doc_ids[index:index + batch_size]
            for index in range(0, len(eligible_doc_ids), batch_size)
        ]

    if not batch_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"No eligible documents available for {level} batch.",
        )

    container = get_container_client(workspace)

    batch_prefix = build_project_prefix(
        workspace,
        client_id,
        project_id,
        "Batches",
    )

    existing_batch_files = [
        blob.name
        for blob in container.list_blobs(name_starts_with=batch_prefix)
        if blob.name.endswith(".json")
    ]

    requested_batch_name = (
        options.get("batch_name")
        if options
        else ""
    )

    requested_batch_name = str(requested_batch_name or "").strip()

    if requested_batch_name:
        prefix_match = re.match(r"^(.*?)(?:_\d+)?$", requested_batch_name)
        batch_prefix_name = (
            prefix_match.group(1).strip()
            if prefix_match
            else requested_batch_name
        )
    else:
        batch_prefix_name = "Batch"

    batch_prefix_name = (
        batch_prefix_name
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )

    existing_numbers = []

    for blob_name in existing_batch_files:
        file_name = blob_name.split("/")[-1]
        name_without_ext = file_name.rsplit(".", 1)[0]

        match = re.match(
            rf"^{re.escape(batch_prefix_name)}_(\d+)$",
            name_without_ext,
        )

        if match:
            existing_numbers.append(int(match.group(1)))

    next_number = max(existing_numbers, default=0) + 1

    created_batches = []

    for chunk in batch_chunks:
        if not chunk:
            continue

        batch_name = f"{batch_prefix_name}_{next_number:03d}"

        batch = {
            "batch_name": batch_name,
            "workspace": workspace,
            "project_id": project_id,
            "client_id": client_id,
            "level": level,
            "workflow_type": workflow_type,
            "options": options,
            "source_batch_id": options.get("qc_source_batch_id", ""),
            "qc_sample_percentage": options.get("qc_sample_percentage", ""),
            "qc_source_document_count": options.get("qc_source_document_count", 0),
            "qc_sample_size": options.get("qc_sample_size", 0),
            "status": "Available",
            "batch_size": batch_size,
            "document_count": len(chunk),
            "doc_ids": chunk,
            "checked_out_by": None,
            "completed_count": 0,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        blob_name = f"{batch_prefix}{batch_name}.json"

        container.upload_blob(
            name=blob_name,
            data=json.dumps(batch, indent=2),
            overwrite=True,
        )

        created_batches.append(batch)
        next_number += 1

    if not created_batches:
        raise HTTPException(
            status_code=400,
            detail=f"No eligible documents available for {level} batch.",
        )

    return {
        "message": f"{len(created_batches)} batch(es) created.",
        "batches": created_batches,
        "created_count": len(created_batches),
        "eligible_remaining": 0,
    }

def checkout_project_batch(
    workspace: Workspace,
    project_id: str,
    batch_name: str,
    username: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    batch_blob_name = build_project_path(
        workspace,
        client_id,
        project_id,
        "Batches",
        f"{batch_name}.json",
    )

    blob_client = container.get_blob_client(batch_blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail="Batch not found.",
        )

    batch = json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )

    if batch.get("status") == "Checked Out":
        raise HTTPException(
            status_code=409,
            detail=f"Batch already checked out by {batch.get('checked_out_by')}.",
        )

    batch["status"] = "Checked Out"
    batch["checked_out_by"] = username
    batch["checked_out_at"] = datetime.now(timezone.utc).isoformat()

    blob_client.upload_blob(
        json.dumps(batch, indent=2),
        overwrite=True,
    )

    return {
        "message": "Batch checked out.",
        "batch": batch,
    }
    
def remove_docs_from_batch(
    workspace: Workspace,
    project_id: str,
    batch_name: str,
    doc_ids: list[str] | None = None,
    username: str = "admin",
    preserve_captured_data: bool = True,
    client_id: str = "",
):
    container = get_container_client(workspace)

    batch_blob_name = build_project_path(
        workspace,
        client_id,
        project_id,
        "Batches",
        f"{batch_name}.json",
    )

    batch_blob = container.get_blob_client(batch_blob_name)

    if not batch_blob.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Batch not found: {batch_name}",
        )

    batch = json.loads(
        batch_blob.download_blob()
        .readall()
        .decode("utf-8")
    )

    existing_doc_ids = batch.get("doc_ids", [])

    if doc_ids:
        remove_set = set(doc_ids)
    else:
        remove_set = set(existing_doc_ids)

    remaining_doc_ids = [
        doc_id for doc_id in existing_doc_ids
        if doc_id not in remove_set
    ]

    removed_doc_ids = [
        doc_id for doc_id in existing_doc_ids
        if doc_id in remove_set
    ]

    if not removed_doc_ids:
        raise HTTPException(
            status_code=400,
            detail="No documents were found to remove from this batch.",
        )

    batch["doc_ids"] = remaining_doc_ids
    batch["document_count"] = len(remaining_doc_ids)
    batch["batch_size"] = len(remaining_doc_ids)
    batch["documents"] = str(len(remaining_doc_ids))
    batch["last_modified_by"] = username
    batch["last_modified_at"] = datetime.now(timezone.utc).isoformat()
    batch["last_remove_preserve_data"] = preserve_captured_data

    if len(remaining_doc_ids) == 0:
        batch["status"] = "Empty"
        batch["checked_out_by"] = None

    batch_blob.upload_blob(
        json.dumps(batch, indent=2),
        overwrite=True,
    )

    audit_blob_name = build_project_path(
        workspace,
        client_id,
        project_id,
        "Audit",
        "Batches",
        f"{batch_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json",
    )

    audit_record = {
        "action": "remove_docs_from_batch",
        "workspace": workspace,
        "client_id": client_id,
        "project_id": project_id,
        "batch_name": batch_name,
        "removed_doc_ids": removed_doc_ids,
        "preserve_captured_data": preserve_captured_data,
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    container.upload_blob(
        name=audit_blob_name,
        data=json.dumps(audit_record, indent=2),
        overwrite=True,
    )

    return {
        "status": "removed",
        "message": f"Removed {len(removed_doc_ids)} document(s) from {batch_name}.",
        "batch": batch,
        "removed_doc_ids": removed_doc_ids,
        "removed_doc_count": len(removed_doc_ids),
        "preserve_captured_data": preserve_captured_data,
    }