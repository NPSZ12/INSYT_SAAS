import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client


router = APIRouter(prefix="/api", tags=["workspace-projects"])


class CreateProjectRequest(BaseModel):
    project_name: str
    client_name: str | None = None
    protocol_template: str | None = None
    protocol_fields: list[dict] = []


def normalize_project_name(name: str):
    cleaned = name.strip().replace(" ", "_")
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", cleaned)

    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="Project name is invalid.",
        )

    return cleaned


@router.post("/{workspace}/projects/create")
def create_workspace_project(
    workspace: str,
    payload: CreateProjectRequest,
    
):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, or discovery.",
        )

    try:
        container = get_container_client(workspace)

        project_name = normalize_project_name(payload.project_name)

        metadata = {
            "project_name": project_name,
            "client_name": payload.client_name or "",
            "workspace": workspace,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        marker_blob = f"{project_name}/project.json"

        if container.get_blob_client(marker_blob).exists():
            raise HTTPException(
                status_code=400,
                detail=f"Project already exists: {project_name}",
            )

        container.upload_blob(
            name=marker_blob,
            data=json.dumps(metadata, indent=2),
            overwrite=False,
        )
        project_folders = [
            f"{project_name}/Batches/.keep",

            f"{project_name}/analytics/.keep",

            f"{project_name}/archive/.keep",

            f"{project_name}/logs/.keep",

            f"{project_name}/review/batches/.keep",
            f"{project_name}/review/exports/.keep",
            f"{project_name}/review/qc/.keep",
            f"{project_name}/review/saved_records/.keep",
            f"{project_name}/review/statistical_qc/.keep",
            f"{project_name}/review/linked_entities/.keep",
            f"{project_name}/review/captured_entities/.keep",
            f"{project_name}/review/audit/.keep",
            f"{project_name}/review/workproduct/.keep",

            f"{project_name}/source/metadata/.keep",
            f"{project_name}/source/native/.keep",
            f"{project_name}/source/protocol/.keep",
            f"{project_name}/source/text/.keep",

            f"{project_name}/uploads/.keep",

            f"{project_name}/reports/.keep",

            f"{project_name}/exports/.keep",
        ]

        for folder_blob in project_folders:
            container.upload_blob(
                name=folder_blob,
                data=b"",
                overwrite=True,
            )
        protocol_payload = {
            "project_name": project_name,
            "client_name": payload.client_name or "",
            "workspace": workspace,
            "protocol_template": payload.protocol_template or "",
            "fields": payload.protocol_fields,
            "created_at": metadata["created_at"],
        }

        protocol_blob = f"{project_name}/{project_name}_Protocol.json"

        container.upload_blob(
            name=protocol_blob,
            data=json.dumps(protocol_payload, indent=2),
            overwrite=True,
        )

        return {
            "message": f"Project created: {project_name}",
            "project": metadata,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create project: {type(e).__name__}: {e}",
        )