import json
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client
from app.services.protocol_service import load_protocol_fields
from app.services.project_store import CAPTURED_ENTITIES
from app.services.batch_service import get_container_client
from app.services.summary_outline_service import parse_summary_outline
from app.services.pdf_text_service import get_text_blob_path


from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    generate_blob_sas,
    BlobSasPermissions,
)


router = APIRouter(prefix="/api", tags=["Review"])


VALID_WORKSPACES = ["capture", "summaries", "discovery"]


def list_workspace_project_files(
    workspace: str,
    project_id: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    clean_project_id = project_id.strip("/")
    clean_client_id = client_id.strip("/")

    if clean_client_id:
        prefix = f"{clean_client_id}/{clean_project_id}/"
    else:
        prefix = f"{clean_project_id}/"

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name.split("/")[-1]

        if not name:
            continue

        files.append(
            {
                "name": name,
                "path": blob.name,
                "size": getattr(blob, "size", 0),
            }
        )

    return files


def read_workspace_blob_text(workspace: str, blob_path: str):
    container = get_container_client(workspace)
    blob_client = container.get_blob_client(blob_path)

    return blob_client.download_blob().readall().decode(
        "utf-8",
        errors="replace",
    )


from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    generate_blob_sas,
    BlobSasPermissions,
)


def get_workspace_blob_url(
    workspace: str,
    blob_path: str,
):
    if not blob_path:
        return ""

    container = get_container_client(workspace)

    blob_client = container.get_blob_client(blob_path)

    account_name = container.account_name

    account_key = (
        container.credential.account_key
        if hasattr(container.credential, "account_key")
        else container.credential
    )

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container.container_name,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc)
        + timedelta(hours=4),
    )

    return f"{blob_client.url}?{sas_token}"

SUPPORTED_REVIEW_EXTENSIONS = (
    ".pdf",
    ".txt",
    ".docx",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".csv",
    ".dat",
    ".json",
)


def normalize_doc_id(value: str) -> str:
    name = str(value or "").strip().split("/")[-1]

    if "." in name:
        name = name.rsplit(".", 1)[0]

    return name.strip().lower()


def get_batch_blob_name(
    client: str,
    project_id: str,
    batch: str,
) -> str:
    if client:
        return f"{client}/{project_id}/Batches/{batch}.json"

    return f"{project_id}/Batches/{batch}.json"


def load_batch_payload(
    workspace: str,
    client: str,
    project_id: str,
    batch: str,
):
    container = get_container_client(workspace)

    batch_blob_name = get_batch_blob_name(
        client=client,
        project_id=project_id,
        batch=batch,
    )

    blob_client = container.get_blob_client(batch_blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Batch not found: {batch_blob_name}",
        )

    payload = json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )

    doc_ids = [
        str(doc_id).strip()
        for doc_id in payload.get("doc_ids", [])
        if str(doc_id).strip()
    ]

    if not doc_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Batch {batch} has no assigned documents.",
        )

    return payload, doc_ids


def get_project_files_for_review(
    workspace: str,
    project_id: str,
    client: str,
):
    try:
        return list_workspace_project_files(
            workspace,
            project_id,
            client,
        )
    except TypeError:
        return list_workspace_project_files(
            workspace,
            project_id,
        )


def find_native_file_for_doc(
    files: list[dict],
    doc_id: str,
):
    requested = normalize_doc_id(doc_id)

    native_files = [
        file for file in files
        if "/source/native/" in f"/{str(file.get('path', '')).lower()}"
        and str(file.get("name", "")).lower().endswith(
            SUPPORTED_REVIEW_EXTENSIONS
        )
    ]

    for file in native_files:
        file_name = str(file.get("name", "")).split("/")[-1]
        file_base = normalize_doc_id(file_name)
        blob_base = normalize_doc_id(str(file.get("path", "")))

        if file_base == requested or blob_base == requested:
            return file

    return None


def resolve_text_blob_path(native_blob: str) -> str:
    if native_blob.lower().endswith(".txt"):
        return native_blob

    try:
        return get_text_blob_path(native_blob)
    except Exception:
        base_path, file_name = native_blob.rsplit("/", 1)
        doc_id = file_name.rsplit(".", 1)[0]

        if "/source/native" in base_path:
            text_base = base_path.replace("/source/native", "/source/text")
            return f"{text_base}/{doc_id}.txt"

        return f"{base_path}/{doc_id}.txt"

def normalize_doc_lookup(value: str) -> str:
    clean = str(value or "").strip()
    clean = clean.split("/")[-1]
    clean = clean.rsplit(".", 1)[0]
    return clean.replace("_", " ").lower()


def project_base_path(client: str, project: str) -> str:
    client = str(client or "").strip().strip("/")
    project = str(project or "").strip().strip("/")

    if client:
        return f"{client}/{project}"

    return project


def load_review_document_by_doc_id(
    workspace: str,
    client: str,
    project: str,
    doc_id: str,
):
    container = get_container_client(workspace)
    base_path = project_base_path(client, project)
    requested = normalize_doc_lookup(doc_id)

    project_variants = [
        project,
        project.replace(" ", "_"),
    ]

    base_paths = []

    for project_variant in project_variants:
        if client:
            base_paths.append(f"{client}/{project_variant}")

        base_paths.append(project_variant)

    native_prefixes = [
        f"{base_path}/source/native/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/natives/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/native_docs/"
        for base_path in base_paths
    ]

    text_prefixes = [
        f"{base_path}/source/text/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/texts/"
        for base_path in base_paths
    ]

    matched_native = ""
    matched_doc_id = doc_id

    for native_prefix in native_prefixes:
        for blob in container.list_blobs(name_starts_with=native_prefix):
            filename = blob.name.split("/")[-1]

            if not filename or filename == ".keep":
                continue

            if normalize_doc_lookup(filename) == requested:
                matched_native = blob.name
                matched_doc_id = filename.rsplit(".", 1)[0]
                break

        if matched_native:
            break


    if not matched_native:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found in source/native: {doc_id}",
        )

    matched_text = ""

    for text_prefix in text_prefixes:
        for blob in container.list_blobs(name_starts_with=text_prefix):
            filename = blob.name.split("/")[-1]

            if not filename or filename == ".keep":
                continue

            if normalize_doc_lookup(filename) == requested:
                matched_text = blob.name
                break

        if matched_text:
            break

    text = ""

    if matched_text:
        text = (
            container
            .get_blob_client(matched_text)
            .download_blob()
            .readall()
            .decode("utf-8", errors="replace")
        )

    native_url = get_workspace_blob_url(
        workspace,
        matched_native,
    )

    return {
        "workspace": workspace,
        "project": project.replace("_", " "),
        "project_id": project,
        "batch": "Direct Open",
        "doc_id": matched_doc_id,
        "blob_name": matched_text,
        "text": text,
        "native_url": native_url,
        "native_blob": matched_native,
    }

def load_current_review_document(
    workspace: str,
    project: str,
    batch: str,
    client: str = "",
    doc: str = "",
):
    if doc:
        return load_review_document_by_doc_id(
            workspace=workspace,
            client=client,
            project=project,
            doc_id=doc,
        )

    # existing batch-based logic continues below
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    project_id = project

    protocol_fields = load_protocol_fields(project_id)

    batch_payload, batch_doc_ids = load_batch_payload(
        workspace=workspace,
        client=client,
        project_id=project_id,
        batch=batch,
    )

    reviewed_doc_ids = batch_payload.get("reviewed_doc_ids", [])

    if doc:
        target_doc_id = doc.strip()
    else:
        target_doc_id = next(
            (
                doc_id
                for doc_id in batch_doc_ids
                if doc_id not in reviewed_doc_ids
            ),
            batch_doc_ids[0],
        )

    normalized_batch_doc_ids = {
        normalize_doc_id(doc_id): doc_id
        for doc_id in batch_doc_ids
    }

    normalized_target = normalize_doc_id(target_doc_id)

    if normalized_target not in normalized_batch_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested document {target_doc_id} is not assigned "
                f"to batch {batch}."
            ),
        )

    target_doc_id = normalized_batch_doc_ids[normalized_target]

    files = get_project_files_for_review(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    native_file = find_native_file_for_doc(
        files=files,
        doc_id=target_doc_id,
    )

    if not native_file:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Native file not found for batch document: {target_doc_id}"
            ),
        )

    native_blob = native_file["path"]
    text_blob_path = resolve_text_blob_path(native_blob)

    container = get_container_client(workspace)
    text_blob = container.get_blob_client(text_blob_path)

    text_exists = text_blob.exists()
    text = ""
    outline_items = []

    if text_exists:
        text = text_blob.download_blob().readall().decode(
            "utf-8",
            errors="replace",
        )

        try:
            outline_items = parse_summary_outline(text)
        except Exception:
            outline_items = []

    current_index = batch_doc_ids.index(target_doc_id)

    previous_doc_id = (
        batch_doc_ids[current_index - 1]
        if current_index > 0
        else ""
    )

    next_doc_id = (
        batch_doc_ids[current_index + 1]
        if current_index < len(batch_doc_ids) - 1
        else ""
    )

    return {
        "workspace": workspace,
        "project": project_id.replace("_", " "),
        "project_id": project_id,
        "batch": batch,
        "doc_id": target_doc_id,
        "blob_name": text_blob_path,
        "fields": protocol_fields,
        "native_url": get_workspace_blob_url(workspace, native_blob),
        "native_blob": native_blob,
        "text": text[:200000],
        "text_truncated": len(text) > 200000,
        "text_length": len(text),
        "outline_items": outline_items,
        "text_blob": text_blob_path,
        "text_exists": text_exists,
        "batch_doc_ids": batch_doc_ids,
        "batch_doc_index": current_index,
        "batch_doc_count": len(batch_doc_ids),
        "previous_doc_id": previous_doc_id,
        "next_doc_id": next_doc_id,
        "is_first_doc": current_index == 0,
        "is_last_doc": current_index == len(batch_doc_ids) - 1,
    }


@router.get("/review/current")
def get_current_review_document_compat(
    project: str,
    batch: str = "",
    client: str = "",
    doc: str = "",
):
    try:
        return load_current_review_document(
            workspace="capture",
            client=client,
            project=project,
            batch=batch,
            doc=doc,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )


@router.get("/{workspace}/review/current")
def get_workspace_current_review_document(
    workspace: str,
    project: str,
    batch: str = "",
    client: str = "",
    doc: str = "",
):
    try:
        return load_current_review_document(
            workspace=workspace,
            client=client,
            project=project,
            batch=batch,
            doc=doc,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )


class CaptureSaveRequest(BaseModel):
    client_id: str = ""
    project_id: str
    batch_id: str
    doc_id: str
    values: dict = {}
    document_coding: str = ""
    further_review_reason: str = ""
    discovery_tags: dict = {}
    discovery_notes: dict = {}


@router.post("/review/save")
def save_capture(
    payload: CaptureSaveRequest,
    x_username: str = Header(default=""),
):
    entity = {
        "id": len(CAPTURED_ENTITIES) + 1,
        "project_id": payload.project_id,
        "batch_id": payload.batch_id,
        "doc_id": payload.doc_id,
        "captured_by": x_username,
        "linked": True,
        "values": payload.values,
    }

    CAPTURED_ENTITIES.append(entity)
    
    container = get_container_client("capture")

    if payload.client_id:
        batch_blob = (
            f"{payload.client_id}/"
            f"{payload.project_id}/"
            f"Batches/"
            f"{payload.batch_id}.json"
        )
    else:
        batch_blob = (
            f"{payload.project_id}/"
            f"Batches/"
            f"{payload.batch_id}.json"
        )

    blob_client = container.get_blob_client(batch_blob)

    if blob_client.exists():
        batch = json.loads(
            blob_client.download_blob()
            .readall()
            .decode("utf-8")
        )

        reviewed_docs = batch.get(
            "reviewed_doc_ids",
            []
        )

        if payload.doc_id not in reviewed_docs:
            reviewed_docs.append(payload.doc_id)

        batch["reviewed_doc_ids"] = reviewed_docs
        batch["completed_count"] = len(reviewed_docs)
        batch["last_reviewed_doc_id"] = payload.doc_id
        batch["last_reviewed_by"] = x_username
        batch["last_reviewed_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        if batch["completed_count"] >= batch.get("document_count", 0):
            batch["status"] = "Completed"

        blob_client.upload_blob(
            json.dumps(batch, indent=2),
            overwrite=True,
        )

    return {
        "status": "saved",
        "doc_id": payload.doc_id,
        "values": payload.values,
    }


@router.post("/review/save-next")
def save_and_next(payload: CaptureSaveRequest):
    return {
        "status": "saved_next",
        "message": f"Saved {payload.doc_id}. Next document ready.",
    }