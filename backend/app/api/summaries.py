import os

from fastapi import APIRouter, HTTPException
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/summaries", tags=["summaries"])

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_SUMMARIES_CONTAINER = os.getenv(
    "AZURE_SUMMARIES_CONTAINER",
    "insyt-summaries"
)


def get_summaries_container_client():
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    return service_client.get_container_client(AZURE_SUMMARIES_CONTAINER)


@router.get("/projects")
def list_summaries_projects():
    try:
        container = get_summaries_container_client()

        project_names = set()

        for blob in container.list_blobs():
            parts = blob.name.split("/")

            if len(parts) > 1 and parts[0]:
                project_names.add(parts[0])

        return {
            "container": AZURE_SUMMARIES_CONTAINER,
            "projects": sorted(project_names),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list summaries projects: {type(e).__name__}: {e}",
        )