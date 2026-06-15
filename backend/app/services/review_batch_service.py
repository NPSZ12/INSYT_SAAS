import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.services.storage_paths import build_project_prefix, build_project_path
from app.services.batch_service import (
    get_container_client,
)


def build_batch_blob_name(
    workspace: str,
    client_id: str,
    project_id: str,
    batch_name: str,
):
    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")
    clean_batch_name = batch_name.strip("/")

    if not clean_client_id:
        raise HTTPException(
            status_code=400,
            detail="Client is required for batch paths.",
        )

    return build_project_path(
        workspace,
        clean_client_id,
        clean_project_id,
        "Batches",
        f"{clean_batch_name}.json",
    )


def build_batches_prefix(
    project_id: str,
    client_id: str | None = None,
    workspace: str = "capture",
):
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Client is required for batch paths.",
        )

    return build_project_prefix(
        workspace,
        client_id,
        project_id,
        "Batches",
    )


def find_existing_checked_out_batch_for_user(
    container,
    workspace: str,
    client_id: str,
    project_id: str,
    username: str,
    requested_batch_blob_name: str,
):
    batches_prefix = build_batches_prefix(
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
    )

    for blob in container.list_blobs(
        name_starts_with=batches_prefix
    ):
        blob_name = blob.name

        if not blob_name.endswith(".json"):
            continue

        if blob_name == requested_batch_blob_name:
            continue

        try:
            blob_client = container.get_blob_client(blob_name)
            data = blob_client.download_blob().readall()
            batch = json.loads(data.decode("utf-8"))
        except Exception:
            continue

        status = str(batch.get("status") or "").strip().lower()
        checked_out_by = str(
            batch.get("checked_out_by") or ""
        ).strip()

        if (
            status == "checked out"
            and checked_out_by == username
        ):
            return batch

    return None


def checkout_batch(
    workspace: str,
    project_id: str,
    batch_name: str,
    username: str,
    client_id: str = "",
):
    container = get_container_client(workspace)

    blob_name = build_batch_blob_name(
        client_id=client_id,
        project_id=project_id,
        batch_name=batch_name,
    )

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

    existing_batch = find_existing_checked_out_batch_for_user(
        container=container,
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
        username=username,
        requested_batch_blob_name=blob_name,
    )

    if existing_batch:
        existing_batch_name = (
            existing_batch.get("batch_name")
            or existing_batch.get("name")
            or existing_batch.get("batch_id")
            or "another batch"
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACTIVE_BATCH_ALREADY_CHECKED_OUT",
                "message": (
                    "You already have a batch checked out. "
                    "Complete or release your current batch before "
                    "checking out another batch."
                ),
                "existing_batch_name": existing_batch_name,
            },
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
    client_id: str = "",
):
    container = get_container_client(workspace)

    blob_name = build_batch_blob_name(
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
        batch_name=batch_name,
    )

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

    blob_name = build_batch_blob_name(
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
        batch_name=batch_name,
    )

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
            detail=(
                "Only the checked out reviewer or authorized "
                "leadership can release this batch."
            ),
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