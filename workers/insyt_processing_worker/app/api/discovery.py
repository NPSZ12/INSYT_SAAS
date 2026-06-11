import os

from fastapi import APIRouter, HTTPException
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_DISCOVERY_CONTAINER = os.getenv(
    "AZURE_DISCOVERY_CONTAINER",
    "insyt-discovery",
)


def get_discovery_container_client():
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    return service_client.get_container_client(AZURE_DISCOVERY_CONTAINER)


@router.get("/projects")
def list_discovery_projects():
    try:
        container = get_discovery_container_client()

        project_names = set()

        for blob in container.list_blobs():
            parts = blob.name.split("/")

            if len(parts) > 1 and parts[0]:
                project_names.add(parts[0])

        return {
            "container": AZURE_DISCOVERY_CONTAINER,
            "projects": sorted(project_names),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list discovery projects: {type(e).__name__}: {e}",
        )