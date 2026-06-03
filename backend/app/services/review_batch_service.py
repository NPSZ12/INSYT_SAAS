import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.services.batch_service import (
    get_container_client,
)


def checkout_batch(
    workspace: str,
    project_id: str,
    batch_name: str,
    username: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")
    clean_batch_name = batch_name.strip("/")

    if clean_client_id:
        blob_name = f"{clean_client_id}/{clean_project_id}/Batches/{clean_batch_name}.json"
    else:
        blob_name = f"{clean_project_id}/Batches/{clean_batch_name}.json"

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail="Batch not found.",
        )

    data = blob_client.download_blob().readall()

    batch = json.loads(data.decode("utf-8"))

    status = batch.get("status")

    checked_out_by = batch.get("checked_out_by")

    if (
        status == "Checked Out"
        and checked_out_by
        and checked_out_by != username
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Batch already checked out by {checked_out_by}.",
        )

    batch["status"] = "Checked Out"
    batch["checked_out_by"] = username
    batch["checked_out_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    container.upload_blob(
        name=blob_name,
        data=json.dumps(batch, indent=2),
        overwrite=True,
    )

    return {
        "message": "Batch checked out.",
        "batch": batch,
    }


def complete_batch(
    workspace: str,
    project_id: str,
    batch_name: str,
    username: str,
):
    container = get_container_client(workspace)

    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")
    clean_batch_name = batch_name.strip("/")

    if clean_client_id:
        blob_name = f"{clean_client_id}/{clean_project_id}/Batches/{clean_batch_name}.json"
    else:
        blob_name = f"{clean_project_id}/Batches/{clean_batch_name}.json"

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail="Batch not found.",
        )

    data = blob_client.download_blob().readall()

    batch = json.loads(data.decode("utf-8"))

    if batch.get("checked_out_by") != username:
        raise HTTPException(
            status_code=400,
            detail="Only the checked out reviewer can complete this batch.",
        )

    batch["status"] = "Completed"
    batch["completed_by"] = username
    batch["completed_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    container.upload_blob(
        name=blob_name,
        data=json.dumps(batch, indent=2),
        overwrite=True,
    )

    return {
        "message": "Batch completed.",
        "batch": batch,
    }
    
def release_batch(
    workspace: str,
    project_id: str,
    batch_name: str,
    username: str,
    role: str | None = None,
    client_id: str = "",
):
    container = get_container_client(workspace)

    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")
    clean_batch_name = batch_name.strip("/")

    if clean_client_id:
        blob_name = f"{clean_client_id}/{clean_project_id}/Batches/{clean_batch_name}.json"
    else:
        blob_name = f"{clean_project_id}/Batches/{clean_batch_name}.json"

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail="Batch not found.",
        )

    data = blob_client.download_blob().readall()

    batch = json.loads(data.decode("utf-8"))

    allowed_override_roles = [
        "RM",
        "Admin",
        "INSYT Admin",
        "CDS Admin",
    ]

    is_owner = batch.get("checked_out_by") == username
    is_override = role in allowed_override_roles

    if not is_owner and not is_override:
        raise HTTPException(
            status_code=400,
            detail="Only the checked out reviewer or authorized leadership can release this batch.",
        )

    batch["status"] = "Available"
    batch["checked_out_by"] = None
    batch["checked_out_at"] = ""
    batch["released_by"] = username
    batch["released_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    container.upload_blob(
        name=blob_name,
        data=json.dumps(batch, indent=2),
        overwrite=True,
    )

    return {
        "message": "Batch marked available.",
        "batch": batch,
    }