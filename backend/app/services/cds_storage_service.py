import os
from typing import Any

from azure.storage.blob import BlobServiceClient


CDS_STORAGE_CONNECTION_STRING = os.getenv("CDS_STORAGE_CONNECTION_STRING")
CDS_PROJECTS_CONTAINER = os.getenv("CDS_PROJECTS_CONTAINER", "projects")


def get_blob_service_client() -> BlobServiceClient:
    if not CDS_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing CDS_STORAGE_CONNECTION_STRING")

    return BlobServiceClient.from_connection_string(
        CDS_STORAGE_CONNECTION_STRING
    )


def get_container_client():
    blob_service = get_blob_service_client()
    return blob_service.get_container_client(CDS_PROJECTS_CONTAINER)


def list_capture_projects() -> list[str]:
    container = get_container_client()

    project_names: set[str] = set()

    for blob in container.list_blobs():
        parts = blob.name.split("/")

        if parts and parts[0]:
            project_names.add(parts[0])

    return sorted(project_names)


def list_project_files(project_id: str) -> list[dict[str, Any]]:
    container = get_container_client()

    prefix = f"{project_id}/"
    files: list[dict[str, Any]] = []

    for blob in container.list_blobs(name_starts_with=prefix):
        if blob.name.endswith("/"):
            continue

        files.append(
            {
                "name": blob.name,
                "file_name": blob.name.split("/")[-1],
                "size": blob.size,
                "last_modified": blob.last_modified.isoformat()
                if blob.last_modified
                else None,
                "content_type": blob.content_settings.content_type
                if blob.content_settings
                else None,
            }
        )

    return files


def read_project_text_file(project_id: str, blob_name: str) -> str:
    if not blob_name.startswith(f"{project_id}/"):
        raise ValueError("Blob path does not belong to requested project")

    container = get_container_client()
    blob_client = container.get_blob_client(blob_name)

    data = blob_client.download_blob().readall()

    return data.decode("utf-8", errors="replace")