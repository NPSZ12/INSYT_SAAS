from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client

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
    "review/batches",
    "review/qc",
    "reports",
    "exports",
    "archive",
]


class CreateWorkspaceProjectRequest(BaseModel):
    client: str
    project_id: str


def clean_folder(value: str) -> str:
    cleaned = value.strip().strip("/")
    cleaned = cleaned.replace("\\", "/")

    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")

    return cleaned


def get_workspace_container(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    return get_container_client(workspace)


@router.post("/{workspace}/projects/create")
def create_workspace_project(
    workspace: str,
    payload: CreateWorkspaceProjectRequest,
):
    container = get_workspace_container(workspace)

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

    created_paths = []

    for folder in DEFAULT_PROJECT_FOLDERS:
        blob_path = (
            f"{client_name}/"
            f"{project_name}/"
            f"{folder}/.keep"
        )

        blob_client = container.get_blob_client(blob_path)

        blob_client.upload_blob(
            b"",
            overwrite=True,
        )

        created_paths.append(blob_path)

    project_json_path = (
        f"{client_name}/{project_name}/project.json"
    )

    project_blob = container.get_blob_client(project_json_path)

    project_blob.upload_blob(
        (
            "{\n"
            f'  "workspace": "{workspace}",\n'
            f'  "client": "{client_name}",\n'
            f'  "project_id": "{project_name}"\n'
            "}\n"
        ).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )

    created_paths.append(project_json_path)

    return {
        "status": "created",
        "workspace": workspace,
        "client": client_name,
        "project": project_name,
        "created_paths": created_paths,
    }