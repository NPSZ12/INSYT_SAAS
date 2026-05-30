from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.batch_service import get_container_client

router = APIRouter(
    prefix="/api",
    tags=["workspace-file-uploads"],
)

VALID_WORKSPACES = {
    "capture",
    "summaries",
    "discovery",
    "development",
}


def clean_folder(value: str) -> str:
    return value.strip().strip("/")


def get_workspace_container(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    return get_container_client(workspace)


@router.post("/{workspace}/files/upload")
async def upload_workspace_files(
    workspace: str,
    client: str = Form(...),
    project_id: str = Form(...),
    folder: str = Form(...),
    files: list[UploadFile] = File(...),
):
    container = get_workspace_container(workspace)

    client_name = clean_folder(client)
    project_name = clean_folder(project_id)
    folder_name = clean_folder(folder)

    if not client_name:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project_name:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not folder_name:
        raise HTTPException(
            status_code=400,
            detail="Folder is required.",
        )

    uploaded = []

    for upload_file in files:
        file_name = upload_file.filename or ""

        if not file_name:
            continue

        blob_path = (
            f"{client_name}/"
            f"{project_name}/"
            f"{folder_name}/"
            f"{file_name}"
        )

        content = await upload_file.read()

        blob_client = container.get_blob_client(blob_path)

        blob_client.upload_blob(
            content,
            overwrite=True,
        )

        uploaded.append(
            {
                "file_name": file_name,
                "blob_path": blob_path,
                "size": len(content),
            }
        )

    return {
        "workspace": workspace,
        "client": client_name,
        "project": project_name,
        "folder": folder_name,
        "count": len(uploaded),
        "uploaded": uploaded,
    }