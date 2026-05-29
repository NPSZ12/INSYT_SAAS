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


def build_prefix(
    project: str,
    client: str | None = None,
    folder: str | None = None,
) -> str:
    project_name = clean_folder(project)

    if client:
        client_name = clean_folder(client)
        base_prefix = f"{client_name}/{project_name}/"
    else:
        base_prefix = f"{project_name}/"

    if folder:
        folder_name = clean_folder(folder)
        return f"{base_prefix}{folder_name}/"

    return base_prefix


@router.get("/{workspace}/files")
def list_workspace_files(
    workspace: str,
    project: str = Query(...),
    client: str | None = Query(default=None),
    folder: str | None = Query(default=None),
):
    container = get_workspace_container(workspace)

    project_name = clean_folder(project)
    client_name = clean_folder(client) if client else ""

    prefix = build_prefix(
        project=project,
        client=client,
        folder=folder,
    )
    print(
        "WORKSPACE FILES:",
        workspace,
        project,
        client,
        folder,
        prefix,
    )

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        blob_path = blob.name
        file_name = blob_path.split("/")[-1]

        if not file_name:
            continue

        # Skip virtual folders
        if "." not in file_name:
            continue

        # Skip system files
        if file_name.startswith("."):
            continue

        # Skip metadata files
        if file_name.lower().endswith(".json"):
            continue

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
                "client": client_name,
                "project": project_name,
                "folder": clean_folder(folder) if folder else "",
            }
        )

    return files