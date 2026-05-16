from fastapi import APIRouter, Header
from app.services.user_store import find_user

from app.services.azure_blob_service import (
    list_project_folders,
    list_project_files,
    read_blob_text,
)

router = APIRouter(prefix="/api/azure-projects", tags=["Azure Projects"])


@router.get("")
def get_azure_projects(x_username: str = Header(default="")):
    all_projects = list_project_folders()

    user = find_user(x_username)

    if not user:
        return []

    if user["role"] in ["INSYT Admin", "RM", "TL", "QC"]:
        return all_projects

    allowed_projects = user.get("project_access", [])

    return [
        project for project in all_projects
        if project in allowed_projects
    ]


@router.get("/{project_id}/files")
def get_project_files(project_id: str):
    return list_project_files(project_id)


@router.get("/{project_id}/sample-text")
def get_project_sample_text(project_id: str):
    files = list_project_files(project_id)

    text_files = [
        file for file in files
        if file["name"].lower().endswith(".txt")
    ]

    if not text_files:
        return {
            "project_id": project_id,
            "text": "No .txt files found for this project.",
        }

    first_text_file = text_files[0]["name"]

    return {
        "project_id": project_id,
        "blob_name": first_text_file,
        "text": read_blob_text(first_text_file),
    }