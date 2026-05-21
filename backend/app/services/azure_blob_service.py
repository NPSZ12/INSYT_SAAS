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
        name = blob.name.strip("/")

        if not name:
            continue

        parts = name.split("/")

        if parts and parts[0]:
            project_names.add(parts[0])

    return sorted(project_names)


def list_project_files(project_id: str):
    container = get_container_client()

    prefix = project_id.strip("/")

    if prefix:
        prefix = f"{prefix}/"

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name

        if name.endswith("/"):
            continue

        files.append({
            "name": name.split("/")[-1],
            "path": name,
            "project_id": project_id,
            "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
            "size": blob.size,
            "content_type": blob.content_settings.content_type if blob.content_settings else None,
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