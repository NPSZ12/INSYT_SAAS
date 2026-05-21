import json

from fastapi import APIRouter, HTTPException

from app.services.batch_service import get_container_client
from pydantic import BaseModel
from datetime import datetime, timezone


class SaveProtocolRequest(BaseModel):
    protocol_template: str
    fields: list[dict]
    override: bool = False


router = APIRouter(
    prefix="/api",
    tags=["workspace-protocols"],
)


@router.get("/{workspace}/projects/{project_id}/protocol")
def get_workspace_protocol(
    workspace: str,
    project_id: str,
):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    try:
        container = get_container_client(workspace)

        possible_protocol_files = [
            f"{project_id}/source/protocol/{project_id}_Protocol.json",
            f"{project_id}/source/protocol/{project_id}_Protocol.xlsx",
            f"{project_id}/{project_id}_Protocol.json",
            f"{project_id}/{project_id}_Protocol.xlsx",
            f"{project_id}/Protocol/{project_id}_Protocol.json",
            f"{project_id}/Protocol/{project_id}_Protocol.xlsx",
            f"{project_id}/protocol.json",
            f"{project_id}/protocol.xlsx",
        ]

        for blob_name in possible_protocol_files:
            blob_client = container.get_blob_client(blob_name)

            if blob_client.exists():
                return {
                    "workspace": workspace,
                    "project_id": project_id,
                    "protocol_blob": blob_name,
                    "download_url": blob_client.url,
                }

        return {
            "workspace": workspace,
            "project_id": project_id,
            "protocol_blob": None,
            "download_url": None,
            "message": "No protocol found.",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load protocol: {type(e).__name__}: {e}",
        )
        
@router.post("/{workspace}/projects/{project_id}/protocol")
def save_workspace_protocol(
    workspace: str,
    project_id: str,
    payload: SaveProtocolRequest,
):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    container = get_container_client(workspace)

    protocol_blob = f"{project_id}/source/protocol/{project_id}_Protocol.json"
    blob_client = container.get_blob_client(protocol_blob)

    if blob_client.exists() and not payload.override:
        raise HTTPException(
            status_code=409,
            detail="Protocol already selected. Do you want to override?",
        )

    protocol_payload = {
        "project_id": project_id,
        "workspace": workspace,
        "protocol_template": payload.protocol_template,
        "fields": payload.fields,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    container.upload_blob(
        name=protocol_blob,
        data=json.dumps(protocol_payload, indent=2),
        overwrite=True,
    )

    return {
        "message": "Protocol saved.",
        "workspace": workspace,
        "project_id": project_id,
        "protocol_blob": protocol_blob,
        "protocol": protocol_payload,
    }