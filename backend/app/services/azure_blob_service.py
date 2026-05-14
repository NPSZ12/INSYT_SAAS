import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from datetime import datetime, timedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CAPTURE_CONTAINER = os.getenv(
    "AZURE_CAPTURE_CONTAINER",
    "insyt-capture"
)


def get_container_client():
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    return service_client.get_container_client(AZURE_CAPTURE_CONTAINER)


def list_project_folders():
    container = get_container_client()

    project_names = set()

    for blob in container.list_blobs():
        parts = blob.name.split("/")

        if len(parts) > 1:
            project_names.add(parts[0])

    return sorted(project_names)


def list_project_files(project_id: str):
    container = get_container_client()

    files = []

    for blob in container.list_blobs(name_starts_with=f"{project_id}/"):
        files.append({
            "name": blob.name,
            "size": blob.size,
            "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
        })

    return files


def read_blob_text(blob_name: str):
    container = get_container_client()
    blob_client = container.get_blob_client(blob_name)

    data = blob_client.download_blob().readall()

    return data.decode("utf-8", errors="replace")

def create_blob_read_url(blob_name: str, minutes: int = 60):
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    account_name = service_client.account_name

    # Pull account key from connection string
    account_key = None
    for part in AZURE_STORAGE_CONNECTION_STRING.split(";"):
        if part.startswith("AccountKey="):
            account_key = part.replace("AccountKey=", "")

    if not account_key:
        raise RuntimeError("Missing AccountKey in connection string")

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=AZURE_CAPTURE_CONTAINER,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes),
    )

    blob_client = service_client.get_blob_client(
        container=AZURE_CAPTURE_CONTAINER,
        blob=blob_name,
    )

    return f"{blob_client.url}?{sas_token}"