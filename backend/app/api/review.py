from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client
from app.services.protocol_service import load_protocol_fields
from app.services.project_store import CAPTURED_ENTITIES
from app.services.batch_service import get_container_client
from app.services.pdf_text_service import get_or_create_extracted_text

from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    generate_blob_sas,
    BlobSasPermissions,
)


router = APIRouter(prefix="/api", tags=["Review"])


VALID_WORKSPACES = ["capture", "summaries", "discovery"]


def list_workspace_project_files(workspace: str, project_id: str):
    container = get_container_client(workspace)

    prefix = f"{project_id.strip('/')}/"

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
):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    project_id = project
    protocol_fields = load_protocol_fields(project_id)

    files = list_workspace_project_files(workspace, project_id)

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
            "fields": protocol_fields,
            "native_url": "",
            "native_blob": "",
            "text_blob": "",
            "text_created": False,
        }

    # TODO: later choose the correct file from the checked-out batch.
    # For now, use the first source/native PDF.
    first_pdf = pdf_files[0]
    native_blob = first_pdf["path"]

    container = get_container_client(workspace)

    extraction = get_or_create_extracted_text(
        container=container,
        source_blob_path=native_blob,
    )

    text = extraction["text"]

    doc_id = native_blob.split("/")[-1].rsplit(".", 1)[0]

    return {
        "workspace": workspace,
        "project": project_id.replace("_", " "),
        "project_id": project_id,
        "batch": batch,
        "doc_id": doc_id,
        "blob_name": extraction["text_blob_path"],
        "text": text,
        "fields": protocol_fields,
        "native_url": get_workspace_blob_url(workspace, native_blob),
        "native_blob": native_blob,
        "text_blob": extraction["text_blob_path"],
        "text_metadata_blob": extraction["metadata_blob_path"],
        "text_created": extraction["created"],
    }


@router.get("/review/current")
def get_current_review_document_compat(
    project: str = "Project_Timber",
    batch: str = "Batch_001",
):
    try:
        return load_current_review_document(
            workspace="capture",
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
):
    try:
        return load_current_review_document(
            workspace=workspace,
            project=project,
            batch=batch,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )


class CaptureSaveRequest(BaseModel):
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