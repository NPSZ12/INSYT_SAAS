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

@router.get("/{workspace}/clients")
def list_workspace_clients(workspace: str):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, or discovery.",
        )

    container = get_container_client(workspace)

    clients = set()

    for blob in container.list_blobs():
        blob_name = blob.name.strip("/")

        if not blob_name.endswith("/project.json"):
            continue

        parts = blob_name.split("/")

        if len(parts) >= 3:
            client = parts[0]

            if (
                client
                and not client.startswith("_")
                and client.lower() != "system"
            ):
                clients.add(client)

    return {
        "status": "success",
        "workspace": workspace,
        "clients": sorted(clients),
    }


@router.get("/{workspace}/clients/{client_name}/projects")
def list_workspace_client_projects(
    workspace: str,
    client_name: str,
):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, or discovery.",
        )

    container = get_container_client(workspace)

    prefix = f"{client_name.strip('/')}/"

    projects = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        blob_name = blob.name.strip("/")

        if not blob_name.endswith("/project.json"):
            continue

        parts = blob_name.split("/")

        if len(parts) >= 3:
            project = parts[1]

            if (
                project
                and not project.startswith("_")
                and project.lower() != "system"
            ):
                projects.add(project)

    return {
        "status": "success",
        "workspace": workspace,
        "client": client_name,
        "projects": sorted(projects),
    }

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
        if not payload.client_name:
            raise HTTPException(
                status_code=400,
                detail="Client name is required.",
            )

        client_name = normalize_project_name(payload.client_name)

        project_root = f"{client_name}/{project_name}"

        metadata = {
            "project_name": project_name,
            "client_name": payload.client_name or "",
            "workspace": workspace,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        marker_blob = f"{project_root}/project.json"

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
            f"{project_root}/Batches/.keep",

            f"{project_root}/analytics/.keep",

            f"{project_root}/archive/.keep",

            f"{project_root}/logs/.keep",

            f"{project_root}/review/batches/.keep",
            f"{project_root}/review/exports/.keep",
            f"{project_root}/review/qc/.keep",
            f"{project_root}/review/saved_records/.keep",
            f"{project_root}/review/statistical_qc/.keep",
            f"{project_root}/review/linked_entities/.keep",
            f"{project_root}/review/captured_entities/.keep",
            f"{project_root}/review/audit/.keep",
            f"{project_root}/review/workproduct/.keep",

            f"{project_root}/source/metadata/.keep",
            f"{project_root}/source/native/.keep",
            f"{project_root}/source/protocol/.keep",
            f"{project_root}/source/text/.keep",

            f"{project_root}/uploads/.keep",

            f"{project_root}/reports/.keep",

            f"{project_root}/exports/.keep",
        ]

        for folder_blob in project_folders:
            container.upload_blob(
                name=folder_blob,
                data=b"",
                overwrite=True,
            )
        protocol_payload = {
            "project_name": project_name,
            "client_name": client_name,
            "workspace": workspace,
            "protocol_template": payload.protocol_template or "",
            "fields": payload.protocol_fields,
            "created_at": metadata["created_at"],
        }

        protocol_blob = f"{project_root}/{project_name}_Protocol.json"

        container.upload_blob(
            name=protocol_blob,
            data=json.dumps(protocol_payload, indent=2),
            overwrite=True,
        )

        return {
            "message": f"Project created: {client_name}/{project_name}",
            "project": metadata,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create project: {type(e).__name__}: {e}",
        )