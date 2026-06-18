import json
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client
from app.services.storage_paths import build_project_base_path

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

def get_workspace_container_name(workspace: str):
    container_names = {
        "capture": "insyt-capture",
        "summaries": "insyt-summaries",
        "discovery": "insyt-discovery",
    }

    container_name = container_names.get(workspace)

    if not container_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace container.",
        )

    return container_name

def parse_insyt_project_marker_path(
    blob_name: str,
    workspace: str,
):
    clean_blob_name = str(blob_name or "").strip("/")
    parts = clean_blob_name.split("/")

    # Canonical INSYT project marker:
    # {client}/{workspace}/{project}/project.json
    if len(parts) != 4:
        return None

    if parts[3] != "project.json":
        return None

    client_name = parts[0]
    workspace_name = parts[1]
    project_name = parts[2]

    if workspace_name != workspace:
        return None

    if (
        not client_name
        or client_name.startswith("_")
        or client_name.lower() == "system"
    ):
        return None

    if (
        not project_name
        or project_name.startswith("_")
        or project_name.lower() == "system"
    ):
        return None

    return {
        "client": client_name,
        "workspace": workspace_name,
        "project": project_name,
    }

def get_project_storage_targets(workspace: str):
    try:
        from azure.storage.blob import BlobServiceClient
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Azure Blob SDK unavailable: {error}",
        )

    container_name = get_workspace_container_name(workspace)

    processing_connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    review_connection = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING")
    live_connection = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_STORAGE_CONNECTION_STRING")
    )

    required = [
        ("processing", "insytprodstorage", processing_connection),
        ("review", "insytreviewstorage", review_connection),
        ("live", "cdsintakestorage", live_connection),
    ]

    missing = [
        target_name
        for target_name, _account_name, connection_string in required
        if not connection_string
    ]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing required storage connection string(s): "
                + ", ".join(missing)
            ),
        )

    targets = []

    for target_name, account_name, connection_string in required:
        if f"AccountName={account_name}" not in connection_string:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"{target_name} storage is not pointing to "
                    f"{account_name}."
                ),
            )

        blob_service = BlobServiceClient.from_connection_string(
            connection_string
        )

        container = blob_service.get_container_client(container_name)

        try:
            container.create_container()
        except Exception as error:
            if "ContainerAlreadyExists" not in str(error):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Failed to ensure container {container_name} "
                        f"in {account_name}: {error}"
                    ),
                )

        targets.append(
            {
                "target": target_name,
                "account": account_name,
                "container_name": container_name,
                "container": container,
            }
        )

    return targets
  
@router.get("/registry/workspace-clients")
def list_registered_clients():
    clients = load_registry_list(CLIENT_REGISTRY_BLOB)

    # Also discover existing clients from canonical INSYT project markers only:
    # {client}/{workspace}/{project}/project.json
    existing_by_name = {
        normalize_registry_name(client.get("client_name")): client
        for client in clients
    }

    for workspace in VALID_WORKSPACES:
        container = get_container_client(workspace)

        for blob in container.list_blobs():
            parsed = parse_insyt_project_marker_path(
                blob_name=blob.name,
                workspace=workspace,
            )

            if not parsed:
                continue

            client_name = parsed["client"]
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
                workspaces = (
                    existing_by_name[normalized].get("workspaces")
                    or []
                )

                if workspace not in workspaces:
                    workspaces.append(workspace)

                existing_by_name[normalized]["workspaces"] = sorted(
                    workspaces
                )

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
        parsed = parse_insyt_project_marker_path(
            blob_name=blob.name,
            workspace=workspace,
        )

        if not parsed:
            continue

        clients.add(parsed["client"])

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

    clean_client = client_name.strip("/")
    prefix = f"{clean_client}/{workspace}/"

    projects = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        parsed = parse_insyt_project_marker_path(
            blob_name=blob.name,
            workspace=workspace,
        )

        if not parsed:
            continue

        if parsed["client"] != clean_client:
            continue

        projects.add(parsed["project"])

    return {
        "status": "success",
        "workspace": workspace,
        "client": client_name,
        "projects": sorted(projects),
    }
    
@router.post("/registry/workspace-projects/create")
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
    workspace = workspace.lower().strip()

    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, or discovery.",
        )

    try:
        storage_targets = get_project_storage_targets(workspace)

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

        project_root = build_project_base_path(
            workspace=workspace,
            client=client_name,
            project=project_name,
        )

        metadata = build_project_metadata(
            workspace=workspace,
            client_name=client_name,
            project_name=project_name,
            client_uuid=client_uuid,
            project_uuid=project_uuid,
        )

        marker_blob = f"{project_root}/project.json"

        existing_targets = []

        for target in storage_targets:
            container = target["container"]

            if container.get_blob_client(marker_blob).exists():
                existing_targets.append(
                    f"{target['target']}:{target['account']}"
                )

        if existing_targets:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Project already exists: {project_name}. "
                    f"Existing target(s): {', '.join(existing_targets)}"
                ),
            )

        project_folders = [
            f"{project_root}/source/native/.keep",
            f"{project_root}/source/text/.keep",
            f"{project_root}/source/protocol/.keep",
            f"{project_root}/source/metadata/.keep",
            f"{project_root}/source/preview/.keep",

            f"{project_root}/processing_center/uploads/.keep",
            f"{project_root}/processing_center/jobs/.keep",
            f"{project_root}/processing_center/staged/.keep",
            f"{project_root}/processing_center/reports/.keep",
            f"{project_root}/processing_center/archive/.keep",
            f"{project_root}/processing_center/removed/.keep",

            f"{project_root}/Batches/.keep",

            f"{project_root}/SearchFolders/.keep",
            f"{project_root}/SearchFolderResults/.keep",

            f"{project_root}/Review/documents/.keep",
            f"{project_root}/Review/batches/.keep",
            f"{project_root}/Review/exports/.keep",
            f"{project_root}/Review/qc/.keep",
            f"{project_root}/Review/saved_records/.keep",
            f"{project_root}/Review/statistical_qc/.keep",
            f"{project_root}/Review/linked_entities/.keep",
            f"{project_root}/Review/captured_entities/.keep",
            f"{project_root}/Review/audit/.keep",
            f"{project_root}/Review/workproduct/.keep",

            f"{project_root}/overlays/raw/.keep",
            f"{project_root}/overlays/final/.keep",

            f"{project_root}/Deleted Data/linked_entities/.keep",

            f"{project_root}/Audit/Batches/.keep",

            f"{project_root}/analytics/.keep",
            f"{project_root}/archive/.keep",
            f"{project_root}/logs/.keep",
            f"{project_root}/reports/.keep",
            f"{project_root}/exports/.keep",
        ]

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

        protocol_blob = (
            f"{project_root}/source/protocol/"
            f"{project_name}_Protocol.json"
        )

        created_targets = []

        for target in storage_targets:
            target_name = target["target"]
            account_name = target["account"]
            container_name = target["container_name"]
            container = target["container"]

            target_created_paths = []

            container.upload_blob(
                name=marker_blob,
                data=json.dumps(
                    {
                        **metadata,
                        "storage_target": target_name,
                        "storage_account": account_name,
                        "container": container_name,
                    },
                    indent=2,
                ),
                overwrite=False,
                content_type="application/json",
            )

            target_created_paths.append(marker_blob)

            for folder_blob in project_folders:
                container.upload_blob(
                    name=folder_blob,
                    data=b"",
                    overwrite=True,
                )

                target_created_paths.append(folder_blob)

            container.upload_blob(
                name=protocol_blob,
                data=json.dumps(protocol_payload, indent=2),
                overwrite=True,
                content_type="application/json",
            )

            target_created_paths.append(protocol_blob)

            created_targets.append(
                {
                    "target": target_name,
                    "account": account_name,
                    "container": container_name,
                    "created_paths": target_created_paths,
                }
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
            "message": (
                f"Project created: "
                f"{client_name}/{workspace}/{project_name}"
            ),
            "workspace": workspace,
            "client": client_name,
            "client_uuid": client_uuid,
            "project": project_name,
            "project_uuid": project_uuid,
            "project_metadata": metadata,
            "storage_targets": created_targets,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create project: {type(e).__name__}: {e}",
        )