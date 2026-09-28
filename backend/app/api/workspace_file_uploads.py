from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.services.batch_service import get_container_client
from app.services.summary_text_service import create_summary_text_file
from app.services.storage_paths import build_project_path

from app.models.user import User
from app.services.authorization import normalize_role
from app.services.security import get_current_user, safe_json_list

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

def require_bound_client_scope(
    current_user: User,
    client_name: str,
) -> None:
    role = normalize_role(
        str(current_user.role or "")
    )

    if role not in {
        "Client",
        "Client Admin",
    }:
        return

    client_names: set[str] = set()

    for value in safe_json_list(
        current_user.client_access
    ):
        raw = str(value or "").strip()

        if not raw or raw == "ALL":
            continue

        parts = raw.split("/")

        if len(parts) >= 2:
            client_names.add(
                "/".join(parts[1:]).strip()
            )
        else:
            client_names.add(raw)

    client_names = {
        value
        for value in client_names
        if value
    }

    if len(client_names) != 1:
        raise HTTPException(
            status_code=403,
            detail=(
                "Client and Client Admin accounts "
                "must be assigned to exactly one "
                "Client / DBA."
            ),
        )

    bound_client = next(
        iter(client_names)
    )

    if (
        bound_client.strip().lower()
        != client_name.strip().lower()
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Access denied. This account may "
                "only upload files to its assigned "
                "Client / DBA."
            ),
        )


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
    current_user: User = Depends(get_current_user),
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

    require_bound_client_scope(
        current_user,
        client_name,
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

        blob_path = build_project_path(
            workspace,
            client_name,
            project_name,
            folder_name,
            file_name,
        )

        content = await upload_file.read()

        blob_client = container.get_blob_client(blob_path)

        blob_client.upload_blob(
            content,
            overwrite=True,
        )

        text_blob_path = None
        summary_extract_path = None
        large_text_extract = None
        text_created = False

        if (
            workspace == "summaries"
            and folder_name == "source/native"
            and file_name.lower().endswith(".pdf")
        ):
            summary_text_result = create_summary_text_file(
                container=container,
                native_blob_name=blob_path,
                pdf_bytes=content,
            )

            if isinstance(summary_text_result, dict):
                text_blob_path = summary_text_result.get("text_blob_name")
                summary_extract_path = summary_text_result.get("extract_blob_name")
                large_text_extract = summary_text_result.get("large_text_extract")
            else:
                text_blob_path = summary_text_result

            text_created = bool(text_blob_path)

        uploaded.append(
            {
                "file_name": file_name,
                "blob_path": blob_path,
                "size": len(content),
                "text_blob_path": text_blob_path,
                "summary_extract_path": summary_extract_path,
                "large_text_extract": large_text_extract,
                "text_created": text_created,
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