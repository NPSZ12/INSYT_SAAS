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

def load_current_review_document(
    workspace: str,
    project: str,
    batch: str,
    client: str = "",
):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    project_id = project
    print(
        "LOAD REVIEW DOC",
        {
            "workspace": workspace,
            "client": client,
            "project": project,
            "batch": batch,
        },
    )
    protocol_fields = load_protocol_fields(project_id)

    files = list_workspace_project_files(
        workspace,
        project_id,
        client,
    )

    print("FILES FOUND", len(files))

    pdf_files = [
        file for file in files
        if file["name"].lower().endswith(".pdf")
        and "/source/native/" in f"/{file['path'].lower()}"
    ]

    if not pdf_files:
        return {
            "workspace": workspace,
            "project": project_id.replace("_", " "),
            "project_id": project_id,
            "batch": batch,
            "doc_id": "No Native PDF",
            "text": "No source/native PDF files found in this Azure project.",
            "text_truncated": False,
            "text_length": 0,
            "outline_items": [],
            "fields": protocol_fields,
            "native_url": "",
            "native_blob": "",
            "text_blob": "",
            "text_exists": False,
        }

    # TODO: later choose the correct file from the checked-out batch.
    # For now, use the first source/native PDF.
    first_pdf = pdf_files[0]
    native_blob = first_pdf["path"]

    container = get_container_client(workspace)

    text_blob_path = get_text_blob_path(native_blob)
    text_blob = container.get_blob_client(text_blob_path)

    text_exists = text_blob.exists()

    text = ""
    outline_items = []

    if text_exists:
        text = text_blob.download_blob().readall().decode(
            "utf-8",
            errors="replace",
        )

        outline_items = parse_summary_outline(text)

    doc_id = native_blob.split("/")[-1].rsplit(".", 1)[0]

    return {
        "workspace": workspace,
        "project": project_id.replace("_", " "),
        "project_id": project_id,
        "batch": batch,
        "doc_id": doc_id,
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
    }


@router.get("/review/current")
def get_current_review_document_compat(
    project: str = "Project_Timber",
    batch: str = "Batch_001",
    client: str = "",
):
    try:
        return load_current_review_document(
            workspace="capture",
            client=client,
            project=project,
            batch=batch,
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
    batch: str,
    client: str = "",
):
    try:
        return load_current_review_document(
            workspace=workspace,
            client=client,
            project=project,
            batch=batch,
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