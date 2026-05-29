from fastapi import APIRouter, HTTPException, Query

from app.services.batch_service import get_container_client

router = APIRouter(
    prefix="/api",
    tags=["workspace-files"],
)

VALID_WORKSPACES = {"capture", "summaries", "discovery"}


def clean_folder(value: str) -> str:
    return value.strip().strip("/")


def get_workspace_container(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    return get_container_client(workspace)


@router.get("/{workspace}/files")
def list_workspace_files(
    workspace: str,
    project: str = Query(...),
    client: str | None = Query(default=None),
):
    container = get_workspace_container(workspace)

    project_name = clean_folder(project)

    if client:
        client_name = clean_folder(client)
        prefix = f"{client_name}/{project_name}/"
    else:
        prefix = f"{project_name}/"

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        blob_path = blob.name
        file_name = blob_path.split("/")[-1]

        if not file_name:
            continue

        extension = (
            file_name.rsplit(".", 1)[-1].lower()
            if "." in file_name
            else ""
        )

        doc_id = (
            file_name.rsplit(".", 1)[0]
            if "." in file_name
            else file_name
        )

        files.append(
            {
                "doc_id": doc_id,
                "file_name": file_name,
                "extension": extension,
                "blob_path": blob_path,
                "size": str(blob.size or ""),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if blob.last_modified
                    else ""
                ),
                "workspace": workspace,
                "client": client or "",
                "project": project_name,
            }
        )

    return files