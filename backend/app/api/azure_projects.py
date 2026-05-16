from fastapi import APIRouter, Depends

from app.models.user import User
from app.services.security import get_current_user
from app.services.azure_blob_service import (
    list_project_folders,
    list_project_files,
    read_blob_text,
)

router = APIRouter(prefix="/api/azure-projects", tags=["Azure Projects"])


@router.get("")
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

    if current_user.role in ["INSYT Admin", "CDS Admin", "RM", "TL", "QC"]:
        return {
            "status": "success",
            "projects": all_projects,
        }

    allowed_projects = current_user.project_access or "[]"

    try:
        import json
        allowed_projects = json.loads(allowed_projects)
    except Exception:
        allowed_projects = []

    return {
        "status": "success",
        "projects": [
            project for project in all_projects
            if project in allowed_projects
        ],
    }


@router.get("/{project_id}/files")
def get_project_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
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