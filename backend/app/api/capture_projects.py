import json

from fastapi import APIRouter, Depends, HTTPException

from app.models.user import User
from app.services.security import get_current_user
from app.services.azure_blob_service import (
    get_container_client,
    list_project_folders,
)
from app.services.cds_storage_service import (
    list_capture_projects,
    list_project_files,
    read_project_text_file,
)


router = APIRouter(prefix="/api/capture", tags=["Capture"])


ADMIN_ROLES = ["INSYT Admin", "CDS Admin", "RM", "TL", "QC"]


def user_allowed_project(user: User, project_id: str) -> bool:
    if user.role in ADMIN_ROLES:
        return True

    try:
        allowed_projects = json.loads(user.project_access or "[]")
    except Exception:
        allowed_projects = []

    return project_id in allowed_projects


@router.get("/")
def get_capture_projects(
    current_user: User = Depends(get_current_user),
):
    try:
        projects = list_capture_projects()
    except Exception as e:
        return {
            "status": "error",
            "projects": [],
            "message": f"Unable to load capture projects: {type(e).__name__}",
        }

    if current_user.role in ADMIN_ROLES:
        visible_projects = projects
    else:
        try:
            allowed_projects = json.loads(current_user.project_access or "[]")
        except Exception:
            allowed_projects = []

        visible_projects = [
            project for project in projects
            if project in allowed_projects
        ]

    return {
        "status": "success",
        "projects": visible_projects,
    }


@router.get("/clients")
def get_capture_clients(
    current_user: User = Depends(get_current_user),
):
    container = get_container_client()

    clients = set()

    for blob in container.list_blobs():
        parts = blob.name.split("/")

        if len(parts) >= 2:
            client = parts[0]

            if client and not client.startswith("_") and client.lower() != "system":
                clients.add(client)

    return {
        "status": "success",
        "clients": sorted(clients),
    }


@router.get("/clients/{client_name}/projects")
def list_client_projects(
    client_name: str,
    current_user: User = Depends(get_current_user),
):
    container = get_container_client()

    prefix = f"{client_name.strip('/')}/"

    projects = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        parts = blob.name.split("/")

        if len(parts) >= 2:
            project = parts[1]

            if current_user.role in ADMIN_ROLES or user_allowed_project(current_user, project):
                projects.add(project)

    return {
        "status": "success",
        "client": client_name,
        "projects": sorted(projects),
    }


@router.get("/{project_id}/files")
def get_capture_project_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    if not user_allowed_project(current_user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")

    try:
        files = list_project_files(project_id)
    except Exception as e:
        return {
            "status": "error",
            "project_id": project_id,
            "files": [],
            "message": f"Unable to load project files: {type(e).__name__}",
        }

    return {
        "status": "success",
        "project_id": project_id,
        "files": files,
    }


@router.get("/{project_id}/text")
def get_capture_project_text(
    project_id: str,
    blob_name: str,
    current_user: User = Depends(get_current_user),
):
    if not user_allowed_project(current_user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")

    try:
        text = read_project_text_file(project_id, blob_name)
    except Exception as e:
        return {
            "status": "error",
            "project_id": project_id,
            "blob_name": blob_name,
            "text": "",
            "message": f"Unable to read text file: {type(e).__name__}",
        }

    return {
        "status": "success",
        "project_id": project_id,
        "blob_name": blob_name,
        "text": text,
    }