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
):
    container = get_container_client(workspace)

    blob_name = f"{project_id}/Batches/{batch_name}.json"

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

    blob_name = f"{project_id}/Batches/{batch_name}.json"

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