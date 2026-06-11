import os

from fastapi import APIRouter, Depends, HTTPException

from app.models.user import User
from app.services.security import get_current_user

from app.services.azure_blob_service import (
    list_project_folders,
    list_project_files,
    read_blob_text,
    get_container_client,
)

router = APIRouter(
    prefix="/api/azure-projects",
    tags=["Azure Projects"],
)


def user_allowed_project(user: User, project_id: str) -> bool:
    if user.role in [
        "INSYT Admin",
        "CDS Admin",
        "RM",
        "TL",
        "QC",
    ]:
        return True

    try:
        import json

        allowed_projects = json.loads(
            user.project_access or "[]"
        )
    except Exception:
        allowed_projects = []

    return project_id in allowed_projects


@router.get("/")
def get_azure_projects(
    current_user: User = Depends(get_current_user),
):
    try:
        all_projects = list_project_folders()
    except Exception as e:
        return {
            "status": "error",
            "projects": [],
            "message": f"Unable to load Azure projects: {type(e).__name__}",
        }

    visible_projects = all_projects

    return {
        "status": "success",
        "projects": visible_projects,
    }

@router.get("/debug")
def debug_azure_projects():
    container_name = os.getenv("AZURE_CAPTURE_CONTAINER")
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")

    try:
        container = get_container_client()
        blobs = []

        for blob in container.list_blobs():
            blobs.append(blob.name)
            if len(blobs) >= 25:
                break

        return {
            "container": container_name,
            "has_connection_string": bool(conn),
            "connection_string_account_hint": conn.split("AccountName=")[1].split(";")[0] if "AccountName=" in conn else None,
            "blob_count_sample": len(blobs),
            "sample_blobs": blobs,
        }

    except Exception as e:
        return {
            "container": container_name,
            "has_connection_string": bool(conn),
            "error_type": type(e).__name__,
            "error": str(e),
        }

@router.get("/{project_id}/files")
def get_project_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    if not user_allowed_project(
        current_user,
        project_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Project access denied",
        )

    try:
        files = list_project_files(project_id)

        return {
            "status": "success",
            "project_id": project_id,
            "files": files,
        }

    except Exception as e:
        return {
            "status": "error",
            "project_id": project_id,
            "files": [],
            "message": f"Unable to load project files: {type(e).__name__}",
        }


@router.get("/{project_id}/sample-text")
def get_project_sample_text(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    if not user_allowed_project(
        current_user,
        project_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Project access denied",
        )

    try:
        files = list_project_files(project_id)

        text_files = [
            file for file in files
            if file["name"].lower().endswith(".txt")
        ]

        if not text_files:
            return {
                "status": "success",
                "project_id": project_id,
                "text": "No .txt files found for this project.",
            }

        first_text_file = text_files[0]["name"]

        return {
            "status": "success",
            "project_id": project_id,
            "blob_name": first_text_file,
            "text": read_blob_text(first_text_file),
        }

    except Exception as e:
        return {
            "status": "error",
            "project_id": project_id,
            "text": "",
            "message": f"Unable to load sample text: {type(e).__name__}",
        }
        
@router.get("/clients")
def get_capture_clients_compat(
    current_user: User = Depends(get_current_user),
):
    projects = list_project_folders()

    clients = sorted({
        project.split("_")[0]
        for project in projects
        if project
        and not project.startswith("_")
        and project.lower() != "system"
    })

    return {
        "status": "success",
        "clients": clients,
        "projects": projects,
    }