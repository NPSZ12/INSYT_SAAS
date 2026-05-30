import json
import os
from datetime import datetime, timezone
from typing import Literal
import math
import random

from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException


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


def list_project_batches(workspace: Workspace, project_id: str):
    container = get_container_client(workspace)

    batch_prefix = f"{project_id}/Batches/"
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
        "project_id": project_id,
        "batches": batches,
    }


def list_project_doc_ids(workspace: Workspace, project_id: str):
    container = get_container_client(workspace)

    prefix = f"{project_id}/"
    doc_ids = []

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name

        if name.endswith("/"):
            continue

        if "/Batches/" in name:
            continue

        if "/QC/" in name:
            continue

        if "/Audit/" in name:
            continue

        if "/SearchFolders/" in name:
            continue

        filename = name.split("/")[-1]

        if not filename:
            continue

        doc_id = os.path.splitext(filename)[0]
        doc_ids.append(doc_id)

    return sorted(set(doc_ids))


def get_already_batched_doc_ids(
    workspace: Workspace,
    project_id: str,
    level: str,
):
    existing = list_project_batches(workspace, project_id)

    already_batched = set()

    for batch in existing["batches"]:
        if batch.get("level") == level:
            already_batched.update(batch.get("doc_ids", []))

    return already_batched

def resolve_search_folder_doc_ids(
    workspace: Workspace,
    project_id: str,
    folder_id: str,
):
    container = get_container_client(workspace)

    possible_blob_names = [
        f"{project_id}/SearchFolders/{folder_id}.json",
        f"{project_id}/SearchFolders/{folder_id}/results.json",
        f"{project_id}/SearchFolderResults/{folder_id}.json",
        f"{project_id}/SearchFolderResults/{folder_id}/results.json",
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

def create_project_batch(
    workspace: Workspace,
    project_id: str,
    batch_size: int,
    level: str,
    workflow_type: str = "standard",
    created_by: str = "admin",
    search_folder_doc_ids: list[str] | None = None,
    options: dict | None = None,
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

    if level == "ALT Workflow":
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
                    )
                )
            else:
                expanded_doc_ids.append(item)

        eligible_doc_ids = sorted(set(expanded_doc_ids))

    else:
        all_doc_ids = list_project_doc_ids(workspace, project_id)

        if level == "1L":
            already_batched = get_already_batched_doc_ids(
                workspace,
                project_id,
                "1L",
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

    if not selected_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=f"No eligible documents available for {level} batch.",
        )

    container = get_container_client(workspace)
    batch_prefix = f"{project_id}/Batches/"

    existing_batch_files = [
        blob.name
        for blob in container.list_blobs(name_starts_with=batch_prefix)
        if blob.name.endswith(".json")
    ]

    next_number = len(existing_batch_files) + 1
    batch_name = f"Batch_{next_number:03d}"

    batch = {
        "batch_name": batch_name,
        "workspace": workspace,
        "project_id": project_id,
        "level": level,
        "workflow_type": workflow_type,
        "status": "Available",
        "batch_size": batch_size,
        "document_count": len(selected_doc_ids),
        "doc_ids": selected_doc_ids,
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

    return {
        "message": "Batch created",
        "batch": batch,
        "eligible_remaining": max(
            len(eligible_doc_ids) - len(selected_doc_ids),
            0,
        ),
    }
    
def remove_docs_from_batch(
    workspace: Workspace,
    project_id: str,
    batch_name: str,
    doc_ids: list[str],
    username: str = "admin",
    preserve_captured_data: bool = True,
):
    if not doc_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one doc_id is required.",
        )

    container = get_container_client(workspace)

    batch_blob_name = f"{project_id}/Batches/{batch_name}.json"
    batch_blob = container.get_blob_client(batch_blob_name)

    if not batch_blob.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Batch not found: {batch_name}",
        )

    data = batch_blob.download_blob().readall()
    batch = json.loads(data.decode("utf-8"))

    existing_doc_ids = batch.get("doc_ids", [])
    remove_set = set(doc_ids)

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
            detail="None of the provided doc_ids were found in this batch.",
        )

    batch["doc_ids"] = remaining_doc_ids
    batch["document_count"] = len(remaining_doc_ids)
    batch["batch_size"] = len(remaining_doc_ids)
    batch["last_modified_by"] = username
    batch["last_modified_at"] = datetime.now(timezone.utc).isoformat()

    if len(remaining_doc_ids) == 0:
        batch["status"] = "Empty"

    batch_blob.upload_blob(
        data=json.dumps(batch, indent=2),
        overwrite=True,
    )

    audit_record = {
        "action": "remove_docs_from_batch",
        "workspace": workspace,
        "project_id": project_id,
        "batch_name": batch_name,
        "removed_doc_ids": removed_doc_ids,
        "preserve_captured_data": preserve_captured_data,
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    audit_blob_name = (
        f"{project_id}/Audit/Batches/"
        f"{batch_name}_remove_docs_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    )

    container.upload_blob(
        name=audit_blob_name,
        data=json.dumps(audit_record, indent=2),
        overwrite=True,
    )

    return {
        "message": "Documents removed from batch.",
        "batch": batch,
        "removed_doc_ids": removed_doc_ids,
        "preserve_captured_data": preserve_captured_data,
    }