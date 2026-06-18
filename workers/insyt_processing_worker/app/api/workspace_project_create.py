import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.storage_paths import (
    build_project_base_path,
    build_project_path,
)


router = APIRouter(
    prefix="/api",
    tags=["workspace-project-create"],
)

VALID_WORKSPACES = {
    "capture",
    "summaries",
    "discovery",
    "development",
}

DEFAULT_PROJECT_FOLDERS = [
    "source/native",
    "source/text",
    "source/metadata",
    "source/protocol",
    "source/preview",
    "source/processing_center/uploads",

    "processing_center/jobs",
    "processing_center/staged",
    "processing_center/reports",
    "processing_center/archive",
    "processing_center/removed",

    "Batches",

    "SearchFolders",
    "SearchFolderResults",

    "Review/documents",
    "Review/batches",
    "Review/exports",
    "Review/qc",
    "Review/saved_records",
    "Review/statistical_qc",
    "Review/linked_entities",
    "Review/captured_entities",
    "Review/audit",
    "Review/workproduct",

    "overlays/raw",
    "overlays/final",
    "overlays/logs",

    "Deleted Data/linked_entities",

    "Audit/Batches",

    "analytics",
    "archive",
    "logs",
    "reports",
    "exports",
]


class CreateWorkspaceProjectRequest(BaseModel):
    client: str
    project_id: str


def clean_folder(value: str) -> str:
    cleaned = str(value or "").strip().strip("/")
    cleaned = cleaned.replace("\\", "/")

    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")

    return cleaned


def validate_workspace(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )


def get_required_storage_targets(workspace: str):
    try:
        from azure.storage.blob import BlobServiceClient
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Azure Blob SDK unavailable: {error}",
        )

    container_names_by_workspace = {
        "capture": "insyt-capture",
        "summaries": "insyt-summaries",
        "discovery": "insyt-discovery",
        "development": "insyt-development",
    }

    container_name = container_names_by_workspace.get(workspace)

    if not container_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace container.",
        )

    processing_connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    review_connection = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING")
    live_connection = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_STORAGE_CONNECTION_STRING")
    )

    required = [
        (
            "processing",
            "insytprodstorage",
            processing_connection,
        ),
        (
            "review",
            "insytreviewstorage",
            review_connection,
        ),
        (
            "live",
            "cdsintakestorage",
            live_connection,
        ),
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
                "name": target_name,
                "account": account_name,
                "container_name": container_name,
                "container": container,
            }
        )

    return targets


@router.post("/{workspace}/projects/create")
def create_workspace_project(
    workspace: str,
    payload: CreateWorkspaceProjectRequest,
):
    validate_workspace(workspace)

    storage_targets = get_required_storage_targets(workspace)

    client_name = clean_folder(payload.client)
    project_name = clean_folder(payload.project_id)

    if not client_name:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project_name:
        raise HTTPException(
            status_code=400,
            detail="Project name is required.",
        )

    project_root = build_project_base_path(
        workspace=workspace,
        client=client_name,
        project=project_name,
    )

    created_paths = []
    created_targets = []

    for target in storage_targets:
        target_name = target["name"]
        account_name = target["account"]
        container = target["container"]

        target_created_paths = []

        for folder in DEFAULT_PROJECT_FOLDERS:
            blob_path = build_project_path(
                workspace,
                client_name,
                project_name,
                folder,
                ".keep",
            )

            blob_client = container.get_blob_client(blob_path)

            blob_client.upload_blob(
                b"",
                overwrite=True,
            )

            target_created_paths.append(blob_path)

        project_json_path = build_project_path(
            workspace,
            client_name,
            project_name,
            "_system",
            "project.json",
        )

        project_blob = container.get_blob_client(project_json_path)

        project_blob.upload_blob(
            (
                "{\n"
                f'  "workspace": "{workspace}",\n'
                f'  "client": "{client_name}",\n'
                f'  "project_id": "{project_name}",\n'
                f'  "project_root": "{project_root}",\n'
                f'  "storage_target": "{target_name}",\n'
                f'  "storage_account": "{account_name}"\n'
                "}\n"
            ).encode("utf-8"),
            overwrite=True,
            content_type="application/json",
        )

        target_created_paths.append(project_json_path)

        created_targets.append(
            {
                "target": target_name,
                "account": account_name,
                "container": target["container_name"],
                "created_paths": target_created_paths,
            }
        )

        created_paths.extend(
            [
                f"{target_name}:{path}"
                for path in target_created_paths
            ]
        )

    return {
        "status": "created",
        "workspace": workspace,
        "client": client_name,
        "project": project_name,
        "project_root": project_root,
        "storage_targets": created_targets,
        "created_paths": created_paths,
    }


@router.post("/{workspace}/projects/ensure-folders")
def ensure_workspace_project_folders(
    workspace: str,
    payload: CreateWorkspaceProjectRequest,
):
    validate_workspace(workspace)

    storage_targets = get_required_storage_targets(workspace)

    client_name = clean_folder(payload.client)
    project_name = clean_folder(payload.project_id)

    if not client_name:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project_name:
        raise HTTPException(
            status_code=400,
            detail="Project name is required.",
        )

    project_root = build_project_base_path(
        workspace=workspace,
        client=client_name,
        project=project_name,
    )

    ensured_paths = []
    ensured_targets = []

    for target in storage_targets:
        target_name = target["name"]
        account_name = target["account"]
        container = target["container"]

        target_ensured_paths = []

        for folder in DEFAULT_PROJECT_FOLDERS:
            blob_path = build_project_path(
                workspace,
                client_name,
                project_name,
                folder,
                ".keep",
            )

            blob_client = container.get_blob_client(blob_path)

            blob_client.upload_blob(
                b"",
                overwrite=True,
            )

            target_ensured_paths.append(blob_path)

        project_json_path = build_project_path(
            workspace,
            client_name,
            project_name,
            "_system",
            "project.json",
        )

        project_blob = container.get_blob_client(project_json_path)

        project_blob.upload_blob(
            (
                "{\n"
                f'  "workspace": "{workspace}",\n'
                f'  "client": "{client_name}",\n'
                f'  "project_id": "{project_name}",\n'
                f'  "project_root": "{project_root}",\n'
                f'  "storage_target": "{target_name}",\n'
                f'  "storage_account": "{account_name}"\n'
                "}\n"
            ).encode("utf-8"),
            overwrite=True,
            content_type="application/json",
        )

        target_ensured_paths.append(project_json_path)

        ensured_targets.append(
            {
                "target": target_name,
                "account": account_name,
                "container": target["container_name"],
                "ensured_paths": target_ensured_paths,
            }
        )

        ensured_paths.extend(
            [
                f"{target_name}:{path}"
                for path in target_ensured_paths
            ]
        )

    return {
        "status": "ensured",
        "workspace": workspace,
        "client": client_name,
        "project": project_name,
        "project_root": project_root,
        "storage_targets": ensured_targets,
        "ensured_paths": ensured_paths,
    }