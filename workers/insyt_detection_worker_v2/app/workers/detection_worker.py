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

    if payload.get("job_type") == "detection_checkpoint_smoke":
        if (
            os.getenv(
                "INSYT_DETECTION_CHECKPOINT_SMOKE_ENABLED",
                "",
            ).strip().lower()
            != "true"
        ):
            raise ValueError(
                "Detection checkpoint smoke mode is disabled."
            )

        from apc.detection_azure_smoke import (
            run_checkpoint_smoke,
        )

        run_checkpoint_smoke(
            container_client=_container_client(),
            smoke_id=payload.get("smoke_id"),
        )
        return

    (
        detection_job_id,
        workspace,
        client,
        project,
        status_blob_path,
    ) = _validate_payload(
        payload
    )

    is_continuation = (
        payload.get("detection_continuation") is True
    )
    db: LedgerDB | None = None

    try:
        if not is_continuation:
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

        if not is_continuation:
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

        # Opt-in worksheet checkpoints. This does not
        # enable bounded continuation by itself.
        worksheet_executor_factory = None

        if (
            os.getenv(
                "INSYT_DETECTION_WORKSHEET_CHECKPOINTS_ENABLED",
                "",
            ).strip().lower()
            == "true"
        ):
            from apc.detection_checkpoint_store import (
                DetectionCheckpointStore,
            )
            from apc.worksheet_executor_factory import (
                make_worksheet_executor_factory,
            )

            if workspace not in {"capture", "discovery"}:
                raise ValueError(
                    "Unsupported checkpoint workspace."
                )

            project_key = project.replace(" ", "_")

            checkpoint_store = DetectionCheckpointStore(
                _container_client(),
                project_prefix=(
                    f"{client}/{workspace}/{project_key}"
                ),
            )

            claim_store = None

            if (
                os.getenv(
                    "INSYT_DETECTION_WORK_CLAIMS_ENABLED",
                    "",
                ).strip().lower()
                == "true"
            ):
                from apc.detection_work_claim import (
                    DetectionWorkClaimStore,
                )

                claim_store = DetectionWorkClaimStore(
                    checkpoint_store.container,
                    project_prefix=checkpoint_store.project_prefix,
                )

            worksheet_executor_factory = (
                make_worksheet_executor_factory(
                    store=checkpoint_store,
                    detection_job_id=detection_job_id,
                    claim_store=claim_store,
                )
            )

        # Opt-in bounded detection. Default remains
        # the existing unbounded Capture/Discovery path.
        bounded_enabled = (
            os.getenv(
                "INSYT_DETECTION_BOUNDED_ENABLED",
                "",
            ).strip().lower()
            == "true"
        )

        max_chunks = None

        if bounded_enabled:
            checkpoints_enabled = (
                os.getenv(
                    "INSYT_DETECTION_WORKSHEET_CHECKPOINTS_ENABLED",
                    "",
                ).strip().lower()
                == "true"
            )

            claims_enabled = (
                os.getenv(
                    "INSYT_DETECTION_WORK_CLAIMS_ENABLED",
                    "",
                ).strip().lower()
                == "true"
            )

            if not checkpoints_enabled or not claims_enabled:
                raise RuntimeError(
                    "Bounded detection requires enabled "
                    "worksheet checkpoints and work claims."
                )

            if worksheet_executor_factory is None:
                raise RuntimeError(
                    "Bounded detection executor unavailable."
                )

            raw_budget = os.getenv(
                "INSYT_DETECTION_MAX_CHUNKS_PER_INVOCATION",
                "1",
            ).strip()

            try:
                max_chunks = int(raw_budget)
            except ValueError as exc:
                raise ValueError(
                    "Invalid bounded detection chunk budget."
                ) from exc

            if not 1 <= max_chunks <= 10:
                raise ValueError(
                    "Bounded detection chunk budget "
                    "must be between 1 and 10."
                )

        result = run_data_element_detection_job(
            db=db,
            payload=payload,
            max_chunks_per_document=max_chunks,
            publication_claim_store=(
                claim_store if bounded_enabled else None
            ),
            worksheet_executor_factory=(
                worksheet_executor_factory
            ),
        )

        if not isinstance(result, dict):
            result = {}

        runner_status = str(
            result.get("status")
            or ""
        ).strip().lower()

        # Bounded jobs resume through the existing
        # Detection V2 queue, not final publication.
        if runner_status == "continuation_required":
            if result.get("checkpoint_verified") is not True:
                raise RuntimeError(
                    "Continuation lacks verified checkpoint state."
                )

            completed = result.get("completed_units")
            total = result.get("total_units")

            if (
                type(completed) is not int
                or type(total) is not int
                or total < 1
                or not 0 <= completed < total
            ):
                raise RuntimeError(
                    "Invalid bounded detection progress."
                )

            from apc.detection_continuation_queue import (
                enqueue_detection_continuation,
            )

            # Send before acknowledging this invocation.
            # Failures propagate to the existing worker
            # failure/retry path.
            enqueue_detection_continuation(payload)

            progress = min(
                90,
                15 + int(75 * completed / total),
            )

            _update_status(
                status_blob_path=status_blob_path,
                status="running",
                stage="processing_detection",
                progress_pct=progress,
                message=(
                    "Detection checkpoints saved; "
                    "remaining work queued."
                ),
                extra={
                    "current_step": (
                        "Continuing bounded detection."
                    ),
                    "completed_units": completed,
                    "total_units": total,
                    "detection_job_id": detection_job_id,
                },
            )

            return

        # Never publish a nonterminal detection result.
        if runner_status not in {
            "completed",
            "completed_with_exceptions",
        }:
            raise RuntimeError(
                "Detection runner did not return a "
                f"terminal result: {runner_status!r}"
            )
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
