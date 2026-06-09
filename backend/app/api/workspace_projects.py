import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client


router = APIRouter(prefix="/api", tags=["workspace-projects"])

VALID_WORKSPACES = [
    "capture",
    "summaries",
    "discovery",
]

REGISTRY_WORKSPACE = "capture"
CLIENT_REGISTRY_BLOB = "_registry/clients.json"
PROJECT_REGISTRY_BLOB = "_registry/projects.json"

class CreateProjectRequest(BaseModel):
    project_name: str | None = None
    project_id: str | None = None

    client_name: str | None = None
    client: str | None = None

    client_uuid: str | None = None
    project_uuid: str | None = None

    protocol_template: str | None = None
    protocol_fields: list[dict] = []
    
class RegistryCreateProjectRequest(BaseModel):
    client_uuid: str | None = None
    client_name: str
    workspace: str
    project_name: str
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

def get_registry_container():
    return get_container_client(REGISTRY_WORKSPACE)


def load_registry_list(blob_name: str):
    container = get_registry_container()
    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return []

    try:
        data = blob_client.download_blob().readall()
        parsed = json.loads(data.decode("utf-8"))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def save_registry_list(blob_name: str, items: list[dict]):
    container = get_registry_container()

    container.upload_blob(
        name=blob_name,
        data=json.dumps(items, indent=2),
        overwrite=True,
        content_type="application/json",
    )


def normalize_registry_name(value: str):
    return str(value or "").strip().lower()


def get_or_create_client_uuid(client_name: str):
    clean_client_name = normalize_project_name(client_name)
    normalized = normalize_registry_name(clean_client_name)

    clients = load_registry_list(CLIENT_REGISTRY_BLOB)

    for client in clients:
        if normalize_registry_name(client.get("client_name")) == normalized:
            return client.get("client_uuid"), clean_client_name

    client_uuid = str(uuid.uuid4())

    clients.append(
        {
            "client_uuid": client_uuid,
            "client_name": clean_client_name,
            "normalized_name": normalized,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workspaces": [],
        }
    )

    save_registry_list(CLIENT_REGISTRY_BLOB, clients)

    return client_uuid, clean_client_name


def update_client_workspace(client_uuid: str, workspace: str):
    clients = load_registry_list(CLIENT_REGISTRY_BLOB)

    for client in clients:
        if client.get("client_uuid") == client_uuid:
            workspaces = client.get("workspaces") or []

            if workspace not in workspaces:
                workspaces.append(workspace)

            client["workspaces"] = sorted(workspaces)
            client["updated_at"] = datetime.now(timezone.utc).isoformat()

            save_registry_list(CLIENT_REGISTRY_BLOB, clients)
            return


def register_project(
    client_uuid: str,
    client_name: str,
    project_uuid: str,
    project_name: str,
    workspace: str,
):
    projects = load_registry_list(PROJECT_REGISTRY_BLOB)

    existing = next(
        (
            item
            for item in projects
            if item.get("workspace") == workspace
            and item.get("client_name") == client_name
            and item.get("project_name") == project_name
        ),
        None,
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing:
        existing["client_uuid"] = client_uuid
        existing["project_uuid"] = existing.get("project_uuid") or project_uuid
        existing["updated_at"] = now
    else:
        projects.append(
            {
                "client_uuid": client_uuid,
                "client_name": client_name,
                "project_uuid": project_uuid,
                "project_name": project_name,
                "workspace": workspace,
                "created_at": now,
            }
        )

    save_registry_list(PROJECT_REGISTRY_BLOB, projects)


def build_project_metadata(
    workspace: str,
    client_name: str,
    project_name: str,
    client_uuid: str,
    project_uuid: str,
):
    return {
        "project_uuid": project_uuid,
        "client_uuid": client_uuid,
        "project_name": project_name,
        "client_name": client_name,
        "workspace": workspace,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
@router.get("/workspace-registry/clients")
def list_registered_clients():
    clients = load_registry_list(CLIENT_REGISTRY_BLOB)

    # Also discover existing clients from all workspaces and backfill registry.
    existing_by_name = {
        normalize_registry_name(client.get("client_name")): client
        for client in clients
    }

    for workspace in VALID_WORKSPACES:
        container = get_container_client(workspace)

        for blob in container.list_blobs():
            blob_name = blob.name.strip("/")

            if not blob_name.endswith("/project.json"):
                continue

            parts = blob_name.split("/")

            if len(parts) < 3:
                continue

            client_name = parts[0]

            if (
                not client_name
                or client_name.startswith("_")
                or client_name.lower() == "system"
            ):
                continue

            normalized = normalize_registry_name(client_name)

            if normalized not in existing_by_name:
                client_uuid = str(uuid.uuid4())

                clients.append(
                    {
                        "client_uuid": client_uuid,
                        "client_name": client_name,
                        "normalized_name": normalized,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "workspaces": [workspace],
                    }
                )

                existing_by_name[normalized] = clients[-1]
            else:
                workspaces = existing_by_name[normalized].get("workspaces") or []

                if workspace not in workspaces:
                    workspaces.append(workspace)

                existing_by_name[normalized]["workspaces"] = sorted(workspaces)

    save_registry_list(CLIENT_REGISTRY_BLOB, clients)

    clients.sort(
        key=lambda item: normalize_registry_name(item.get("client_name"))
    )

    return {
        "status": "success",
        "clients": clients,
    }

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
    
@router.post("/workspace-registry/projects/create")
def create_registered_workspace_project(
    payload: RegistryCreateProjectRequest,
):
    if payload.workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, or discovery.",
        )

    client_uuid, client_name = get_or_create_client_uuid(
        payload.client_name
    )

    if payload.client_uuid:
        client_uuid = payload.client_uuid

    project_uuid = str(uuid.uuid4())

    create_payload = CreateProjectRequest(
        project_name=payload.project_name,
        client_name=client_name,
        client_uuid=client_uuid,
        project_uuid=project_uuid,
        protocol_template=payload.protocol_template,
        protocol_fields=payload.protocol_fields,
    )

    result = create_workspace_project(
        workspace=payload.workspace,
        payload=create_payload,
    )

    update_client_workspace(
        client_uuid=client_uuid,
        workspace=payload.workspace,
    )

    register_project(
        client_uuid=client_uuid,
        client_name=result["client"],
        project_uuid=result["project_uuid"],
        project_name=result["project"],
        workspace=payload.workspace,
    )

    return {
        "status": "created",
        "message": result["message"],
        "workspace": payload.workspace,
        "client": result["client"],
        "client_uuid": client_uuid,
        "project": result["project"],
        "project_uuid": result["project_uuid"],
        "project_metadata": result["project_metadata"],
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

        incoming_project_name = (
            payload.project_name or payload.project_id or ""
        )

        incoming_client_name = (
            payload.client_name or payload.client or ""
        )

        if not incoming_client_name:
            raise HTTPException(
                status_code=400,
                detail="Client name is required.",
            )

        if not incoming_project_name:
            raise HTTPException(
                status_code=400,
                detail="Project name is required.",
            )

        project_name = normalize_project_name(incoming_project_name)
        client_name = normalize_project_name(incoming_client_name)

        client_uuid = payload.client_uuid
        project_uuid = payload.project_uuid or str(uuid.uuid4())

        if not client_uuid:
            client_uuid, client_name = get_or_create_client_uuid(client_name)

        project_root = f"{client_name}/{project_name}"

        metadata = build_project_metadata(
            workspace=workspace,
            client_name=client_name,
            project_name=project_name,
            client_uuid=client_uuid,
            project_uuid=project_uuid,
        )

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
            content_type="application/json",
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
            "project_uuid": project_uuid,
            "client_uuid": client_uuid,
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

        update_client_workspace(
            client_uuid=client_uuid,
            workspace=workspace,
        )

        register_project(
            client_uuid=client_uuid,
            client_name=client_name,
            project_uuid=project_uuid,
            project_name=project_name,
            workspace=workspace,
        )

        return {
            "message": f"Project created: {client_name}/{project_name}",
            "workspace": workspace,
            "client": client_name,
            "client_uuid": client_uuid,
            "project": project_name,
            "project_uuid": project_uuid,
            "project_metadata": metadata,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create project: {type(e).__name__}: {e}",
        )