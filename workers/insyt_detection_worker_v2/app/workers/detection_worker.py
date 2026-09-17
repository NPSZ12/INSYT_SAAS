from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from apc.db import LedgerDB
from apc.detection_job_runner import run_data_element_detection_job
from apc.util import utc_now


def _processing_account() -> str:
    return (
        os.getenv(
            "INSYT_PROCESSING_STORAGE_ACCOUNT",
            "insytprodstorage",
        )
        or "insytprodstorage"
    ).strip()


def _processing_container() -> str:
    return (
        os.getenv(
            "INSYT_PROCESSING_CONTAINER",
            "insyt-processing",
        )
        or "insyt-processing"
    ).strip()


def _blob_service() -> BlobServiceClient:
    connection_string = (
        os.getenv(
            "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
        )
        or ""
    ).strip()

    if connection_string:
        return BlobServiceClient.from_connection_string(
            connection_string
        )

    account = _processing_account()

    return BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )


def _container_client():
    return _blob_service().get_container_client(
        _processing_container()
    )


def _read_json_blob(
    blob_path: str,
    *,
    default: Any = None,
) -> Any:
    if not blob_path:
        return default

    try:
        blob = _container_client().get_blob_client(
            blob_path
        )

        raw = blob.download_blob().readall()

        if not raw:
            return default

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:
        if default is not None:
            return default
        raise


def _write_json_blob(
    blob_path: str,
    payload: dict[str, Any],
) -> None:
    if not blob_path:
        raise ValueError(
            "Detection worker received an empty blob path."
        )

    data = json.dumps(
        payload,
        indent=2,
        default=str,
    ).encode("utf-8")

    blob = _container_client().get_blob_client(
        blob_path
    )

    blob.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(
            content_type="application/json"
        ),
    )


def _status_event(
    *,
    status: str,
    stage: str,
    progress_pct: int,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "at": utc_now(),
        "status": status,
        "stage": stage,
        "progress_pct": int(progress_pct),
        "message": message,
    }

    if extra:
        current_step = (
            extra.get("current_step")
            or extra.get("step")
            or message
        )

        if current_step:
            event["current_step"] = current_step

    return event


def _update_status(
    *,
    status_blob_path: str,
    status: str,
    stage: str,
    progress_pct: int,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _read_json_blob(
        status_blob_path,
        default={},
    )

    if not isinstance(current, dict):
        current = {}

    now = utc_now()

    existing_events = current.get("events") or []

    if not isinstance(existing_events, list):
        existing_events = []

    event = _status_event(
        status=status,
        stage=stage,
        progress_pct=progress_pct,
        message=message,
        extra=extra,
    )

    current.update(
        {
            "status": status,
            "stage": stage,
            "current_stage": stage,
            "current_step": (
                (extra or {}).get(
                    "current_step",
                    message,
                )
            ),
            "progress_pct": int(progress_pct),
            "message": message,
            "updated_at": now,
            "last_updated_at": now,
            "events": [
                *existing_events,
                event,
            ],
        }
    )

    if (
        status == "running"
        and not current.get("started_at")
    ):
        current["started_at"] = now

    if status in {
        "completed",
        "completed_with_exceptions",
        "failed",
        "cancelled",
    }:
        current.setdefault(
            f"{status}_at",
            now,
        )

    if extra:
        current.update(extra)

    _write_json_blob(
        status_blob_path,
        current,
    )

    return current


def _db_path(
    detection_job_id: str,
) -> str:
    root = Path(
        os.getenv(
            "DETECTION_WORKER_DB_ROOT",
            "/tmp/insyt_detection_worker_v2",
        )
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return str(
        root / f"{detection_job_id}.db"
    )


def _validate_payload(
    payload: dict[str, Any],
) -> tuple[
    str,
    str,
    str,
    str,
    str,
]:
    job_type = str(
        payload.get("job_type") or ""
    ).strip().lower()

    if job_type != "data_element_detection":
        raise ValueError(
            "Detection Worker V2 only accepts "
            "job_type=data_element_detection."
        )

    detection_job_id = str(
        payload.get("detection_job_id")
        or ""
    ).strip()

    workspace = str(
        payload.get("workspace")
        or "capture"
    ).strip().lower()

    client = str(
        payload.get("client")
        or ""
    ).strip()

    project = str(
        payload.get("project")
        or ""
    ).strip()

    status_blob_path = str(
        payload.get("status_blob_path")
        or ""
    ).strip()

    if not detection_job_id:
        raise ValueError(
            "Detection queue message missing "
            "detection_job_id."
        )

    if not client:
        raise ValueError(
            "Detection queue message missing client."
        )

    if not project:
        raise ValueError(
            "Detection queue message missing project."
        )

    if not status_blob_path:
        raise ValueError(
            "Detection queue message missing "
            "status_blob_path."
        )

    return (
        detection_job_id,
        workspace,
        client,
        project,
        status_blob_path,
    )


def process_detection_message(
    message_content: str,
) -> None:
    payload = json.loads(
        message_content
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "Detection queue message must contain "
            "a JSON object."
        )

    (
        detection_job_id,
        workspace,
        client,
        project,
        status_blob_path,
    ) = _validate_payload(
        payload
    )

    db: LedgerDB | None = None

    try:
        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="starting",
            progress_pct=5,
            message=(
                "Data Element Detection Worker V2 "
                "accepted job."
            ),
            extra={
                "current_step": (
                    "Detection Worker V2 accepted "
                    "queued Data Element Detection job."
                ),
                "worker_started_at": utc_now(),
                "worker_version": "v2",
                "job_type": "data_element_detection",
                "detection_job_id": detection_job_id,
                "source_job_id": payload.get(
                    "source_job_id"
                ),
                "source_ocr_set_id": payload.get(
                    "source_ocr_set_id"
                ),
                "client": client,
                "project": project,
                "workspace": workspace,
            },
        )

        db = LedgerDB(
            _db_path(
                detection_job_id
            )
        )

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="preparing_detection",
            progress_pct=15,
            message=(
                "Preparing staged text for "
                "Data Element Detection."
            ),
            extra={
                "current_step": (
                    "Loading detection population "
                    "and staged text."
                ),
            },
        )

        result = run_data_element_detection_job(
            db=db,
            payload=payload,
        )

        if not isinstance(result, dict):
            result = {}

        runner_status = str(
            result.get("status")
            or ""
        ).strip().lower()

        documents_exception = int(
            result.get(
                "documents_exception",
                0,
            )
            or 0
        )

        if (
            runner_status == "completed_with_exceptions"
            or documents_exception > 0
        ):
            final_status = "completed_with_exceptions"
            final_message = (
                "Data Element Detection completed "
                "with document exceptions."
            )
        else:
            final_status = "completed"
            final_message = (
                "Data Element Detection completed."
            )

        summary = {
            "detection_run_id": result.get(
                "detection_run_id"
            ),
            "documents_total": result.get(
                "documents_total",
                0,
            ),
            "documents_scanned": result.get(
                "documents_scanned",
                0,
            ),
            "documents_with_hits": result.get(
                "documents_with_hits",
                0,
            ),
            "documents_no_hits": result.get(
                "documents_no_hits",
                0,
            ),
            "documents_nfr": result.get(
                "documents_nfr",
                0,
            ),
            "documents_exception": result.get(
                "documents_exception",
                0,
            ),
            "entity_hit_count": result.get(
                "entity_hit_count",
                result.get(
                    "total_entity_hits",
                    0,
                ),
            ),
        }

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="finalizing_detection",
            progress_pct=95,
            message=(
                "Data Element Detection completed. "
                "Preparing impact assessment."
            ),
            extra={
                "current_step": (
                    "Writing detection totals "
                    "and entity counts."
                ),
                **summary,
            },
        )

        _update_status(
            status_blob_path=status_blob_path,
            status=final_status,
            stage=final_status,
            progress_pct=100,
            message=final_message,
            extra={
                "current_step": (
                    "Detection processing completed."
                ),
                "worker_version": "v2",
                "worker_completed_at": utc_now(),
                **summary,
            },
        )

    except Exception as exc:
        try:
            _update_status(
                status_blob_path=status_blob_path,
                status="failed",
                stage="failed",
                progress_pct=0,
                message=(
                    "Data Element Detection "
                    "Worker V2 failed."
                ),
                extra={
                    "current_step": (
                        "Detection Worker V2 failed."
                    ),
                    "worker_version": "v2",
                    "failed_at": utc_now(),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "job_type": (
                        "data_element_detection"
                    ),
                    "detection_job_id": (
                        detection_job_id
                    ),
                },
            )
        finally:
            raise

    finally:
        if db is not None:
            db.close()
