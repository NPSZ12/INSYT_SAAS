from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from azure.core import MatchConditions
from azure.core.exceptions import (
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.storage.blob import ContentSettings


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Detection index timestamp missing.")

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "Invalid detection index timestamp."
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            "Detection index timestamp lacks timezone."
        )

    return parsed.astimezone(timezone.utc)


def _identity(payload: Any) -> tuple[str, datetime]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid detection document index.")

    job_id = payload.get("latest_detection_job_id")

    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError(
            "Detection index job identity missing."
        )

    return job_id, _timestamp(payload.get("detected_at"))


def write_shared_detection_index(
    *,
    container: Any,
    blob_path: str,
    payload: dict[str, Any],
    storage_account: str,
    container_name: str,
    max_attempts: int = 5,
) -> dict[str, Any]:
    """
    Protect a shared detection-document index.

    Existing versions are updated using ETag compare-and-swap.
    Older publications cannot replace newer indexes.
    """
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("Invalid index retry budget.")

    candidate_job, candidate_time = _identity(payload)

    data = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    blob = container.get_blob_client(blob_path)

    content_settings = ContentSettings(
        content_type="application/json; charset=utf-8"
    )

    def receipt(skipped=False):
        return {
            "storage_account": storage_account,
            "container": container_name,
            "blob_path": blob_path,
            "bytes": len(data),
            "skipped": skipped,
        }

    for _ in range(max_attempts):
        try:
            properties = blob.get_blob_properties()
        except ResourceNotFoundError:
            try:
                blob.upload_blob(
                    data,
                    overwrite=False,
                    content_settings=content_settings,
                )
                return receipt()
            except ResourceExistsError:
                continue

        etag = properties.etag

        # Read the current version. If it changes between
        # this read and the write, the ETag condition fails.
        try:
            current_bytes = blob.download_blob().readall()
        except ResourceNotFoundError:
            continue

        try:
            current = json.loads(
                current_bytes.decode("utf-8")
            )
        except (ValueError, UnicodeError) as exc:
            raise ValueError(
                "Existing detection index is invalid."
            ) from exc

        current_job, current_time = _identity(current)

        if current_job == candidate_job:
            if current_bytes == data:
                return receipt(skipped=True)

            raise RuntimeError(
                "Same-job shared index conflict."
            )

        if current_time > candidate_time:
            return receipt(skipped=True)

        if current_time == candidate_time:
            raise RuntimeError(
                "Different detection jobs have equal "
                "index timestamps; ordering is ambiguous."
            )

        try:
            blob.upload_blob(
                data,
                overwrite=True,
                etag=etag,
                match_condition=MatchConditions.IfNotModified,
                content_settings=content_settings,
            )
            return receipt()
        except (
            ResourceModifiedError,
            ResourceExistsError,
            ResourceNotFoundError,
        ):
            # Another publisher changed the destination.
            # Re-read the new version and compare again.
            continue

    raise RuntimeError(
        "Shared detection index update contention; "
        "retry required."
    )