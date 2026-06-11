from fastapi import APIRouter, HTTPException, Query

from app.services.batch_service import get_container_client

router = APIRouter(
    prefix="/api",
    tags=["workspace-clients"],
)

VALID_WORKSPACES = {"capture", "summaries", "discovery", "development"}


def clean_folder(value: str) -> str:
    return value.strip().strip("/")


def get_workspace_container(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    return get_container_client(workspace)


@router.get("/{workspace}/clients")
def list_workspace_clients(workspace: str):
    container = get_workspace_container(workspace)

    clients = set()

    for blob in container.list_blobs():
        parts = blob.name.strip("/").split("/")

        if len(parts) >= 2:
            clients.add(parts[0])

    return {
        "workspace": workspace,
        "clients": sorted(clients),
    }


@router.get("/{workspace}/projects")
def list_workspace_projects_by_client(
    workspace: str,
    client: str = Query(...),
):
    container = get_workspace_container(workspace)

    client_name = clean_folder(client)
    prefix = f"{client_name}/"

    projects = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        parts = blob.name.strip("/").split("/")

        if len(parts) >= 2:
            projects.add(parts[1])

    return {
        "workspace": workspace,
        "client": client_name,
        "projects": sorted(projects),
    }