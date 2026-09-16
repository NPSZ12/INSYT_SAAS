from __future__ import annotations

import json
import os
import threading

from pathlib import Path
from typing import Any
from uuid import uuid4


try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from azure.identity import DefaultAzureCredential

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    BlobLeaseClient,
)
from azure.core.exceptions import (
    ResourceExistsError,
    HttpResponseError,
)

from apc.azure_blob_adapter import (
    azure_upload_report_files,
    azure_upload_review_outputs,
    azure_update_processed_hash_index,
    azure_archive_processing_uploads,
    azure_upload_processing_set_manifests,
    azure_upload_xl_files_outputs,
    azure_upload_json_structured_outputs,
)

from apc.azure_job_runner import run_azure_processing_job
from apc.detection_job_runner import run_data_element_detection_job
from apc.azure_layout import AzureRoutingConfig

from apc.config import DEFAULT_SETTINGS
from apc.db import LedgerDB
from apc.reports import export_job_report, job_report_data
from apc.util import utc_now


def _processing_account() -> str:
    return os.getenv("INSYT_PROCESSING_STORAGE_ACCOUNT", "insytprodstorage")


def _processing_container() -> str:
    return os.getenv("INSYT_PROCESSING_CONTAINER", "insyt-processing")


def _review_account() -> str:
    return os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")


def _review_container(workspace: str | None = None) -> str:
    workspace_key = str(workspace or "capture").strip().lower()

    workspace_env_name = f"INSYT_REVIEW_CONTAINER_{workspace_key.upper()}"

    return (
        os.getenv(workspace_env_name)
        or os.getenv("INSYT_REVIEW_CONTAINER")
        or f"insyt-{workspace_key}"
    )


def _blob_service() -> BlobServiceClient:
    processing_account = _processing_account()

    processing_conn = os.getenv("INSYT_PROCESSING_STORAGE_CONNECTION_STRING")
    if processing_conn:
        return BlobServiceClient.from_connection_string(processing_conn)

    credential = DefaultAzureCredential()
    return BlobServiceClient(
        account_url=f"https://{processing_account}.blob.core.windows.net",
        credential=credential,
    )


def _container_client():
    return _blob_service().get_container_client(_processing_container())


def _read_json_blob(blob_path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = _container_client().download_blob(blob_path).readall()
        return json.loads(data.decode("utf-8"))
    except Exception:
        if default is not None:
            return default
        raise


def _write_json_blob(blob_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    blob_client = _container_client().get_blob_client(blob_path)

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )

    return {
        "status": "uploaded",
        "storage_account": _processing_account(),
        "container": _processing_container(),
        "blob_path": blob_path,
        "bytes": len(data),
    }

def _send_detection_queue_message(
    payload: dict[str, Any],
) -> dict[str, Any]:
    from azure.storage.queue import QueueClient

    queue_name = os.getenv(
        "APC_DETECTION_QUEUE_NAME",
        "apc-detection-jobs",
    )

    processing_account = _processing_account()

    queue_conn = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if queue_conn:
        queue = QueueClient.from_connection_string(
            queue_conn,
            queue_name=queue_name,
        )
    else:
        queue = QueueClient(
            account_url=(
                f"https://{processing_account}"
                ".queue.core.windows.net"
            ),
            queue_name=queue_name,
            credential=DefaultAzureCredential(),
        )

    try:
        queue.create_queue()
    except Exception:
        pass

    result = queue.send_message(
        json.dumps(
            payload,
            default=str,
        )
    )

    return {
        "status": "queued",
        "queue_name": queue_name,
        "message_id": result.id,
        "inserted_on": str(
            result.inserted_on
        ),
        "expires_on": str(
            result.expires_on
        ),
    }

def _send_ocr_queue_message(
    payload: dict[str, Any],
) -> dict[str, Any]:
    from azure.storage.queue import QueueClient

    queue_name = os.getenv(
        "APC_OCR_QUEUE_NAME",
        "apc-ocr-set-jobs",
    )

    processing_account = _processing_account()

    queue_conn = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if queue_conn:
        queue = QueueClient.from_connection_string(
            queue_conn,
            queue_name=queue_name,
        )
    else:
        queue = QueueClient(
            account_url=(
                f"https://{processing_account}"
                ".queue.core.windows.net"
            ),
            queue_name=queue_name,
            credential=DefaultAzureCredential(),
        )

    try:
        queue.create_queue()
    except Exception:
        pass

    result = queue.send_message(
        json.dumps(
            payload,
            default=str,
        )
    )

    return {
        "status": "queued",
        "queue_name": queue_name,
        "message_id": result.id,
        "inserted_on": str(result.inserted_on),
        "expires_on": str(result.expires_on),
    }

def _upload_processing_file_blob(
    *,
    local_path: str,
    blob_path: str,
) -> dict[str, Any]:
    source = Path(local_path)

    if not source.exists():
        raise FileNotFoundError(
            f"OCR source file does not exist: {source}"
        )

    if not source.is_file():
        raise RuntimeError(
            f"OCR source path is not a file: {source}"
        )

    blob_client = (
        _container_client()
        .get_blob_client(blob_path)
    )

    with source.open("rb") as handle:
        blob_client.upload_blob(
            handle,
            overwrite=True,
            content_settings=ContentSettings(
                content_type="application/octet-stream"
            ),
        )

    return {
        "status": "uploaded",
        "storage_account": _processing_account(),
        "container": _processing_container(),
        "blob_path": blob_path,
        "bytes": source.stat().st_size,
    }

def _hard_cancel_blob_path(
    *,
    client: str,
    workspace: str,
    project: str,
    job_id: str,
) -> str:
    return (
        f"{client}/{workspace}/{project}/"
        "processing_center/"
        f"hard_cancelled_jobs/{job_id}.json"
    )


def _hard_cancelled(
    *,
    client: str,
    workspace: str,
    project: str,
    job_id: str,
) -> bool:
    if not (
        client
        and workspace
        and project
        and job_id
    ):
        return False

    blob_path = _hard_cancel_blob_path(
        client=client,
        workspace=workspace,
        project=project,
        job_id=job_id,
    )

    try:
        payload = _read_json_blob(
            blob_path,
            default={},
        )

        return bool(
            payload.get("hard_cancel")
            or payload.get("status") == "purged"
        )

    except Exception:
        return False
    

def _cancel_requested(cancel_blob_path: str | None) -> bool:
    if not cancel_blob_path:
        return False

    try:
        cancel = _read_json_blob(cancel_blob_path, default={})
        return bool(cancel)
    except Exception:
        return False

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
        "progress_pct": progress_pct,
        "message": message,
    }

    if extra:
        current_file = (
            extra.get("current_file")
            or extra.get("current_file_name")
            or extra.get("latest_file_name")
        )

        current_step = (
            extra.get("current_step")
            or extra.get("step")
            or message
        )

        if current_file:
            event["current_file"] = current_file

        if current_step:
            event["current_step"] = current_step

    return event

def _job_lease_blob_path(
    *,
    client: str,
    workspace: str,
    project: str,
    job_id: str,
) -> str:
    return (
        f"{client}/{workspace}/{project}/"
        f"processing_center/job_leases/{job_id}.lock"
    )


def _acquire_job_lease(
    *,
    client: str,
    workspace: str,
    project: str,
    job_id: str,
) -> tuple[BlobLeaseClient | None, str]:
    blob_path = _job_lease_blob_path(
        client=client,
        workspace=workspace,
        project=project,
        job_id=job_id,
    )

    blob_client = (
        _container_client()
        .get_blob_client(blob_path)
    )

    try:
        blob_client.upload_blob(
            b"",
            overwrite=False,
            content_settings=ContentSettings(
                content_type="application/octet-stream"
            ),
        )
    except ResourceExistsError:
        pass

    try:
        lease = blob_client.acquire_lease(
            lease_duration=60,
        )
    except HttpResponseError as exc:
        if getattr(exc, "status_code", None) == 409:
            return None, blob_path
        raise

    return lease, blob_path


def _renew_job_lease(
    lease: BlobLeaseClient,
) -> bool:
    try:
        lease.renew()
        return True
    except Exception:
        return False


def _release_job_lease(
    lease: BlobLeaseClient | None,
) -> None:
    if lease is None:
        return

    try:
        lease.release()
    except Exception:
        pass


def _update_status(
    *,
    status_blob_path: str,
    status: str,
    stage: str,
    progress_pct: int,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _read_json_blob(status_blob_path, default={})

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
            "current_step": (extra or {}).get("current_step", message),
            "progress_pct": progress_pct,
            "message": message,
            "updated_at": now,
            "last_updated_at": now,
            "events": [*existing_events, event],
        }
    )

    if status == "running" and not current.get("started_at"):
        current["started_at"] = now

    if status in {"completed", "failed", "cancelled"}:
        current.setdefault(f"{status}_at", now)

    if extra:
        current.update(extra)

    _write_json_blob(status_blob_path, current)

    return current


def _cancel_if_requested(
    *,
    cancel_blob_path: str | None,
    status_blob_path: str,
    stage: str,
) -> None:
    if not _cancel_requested(cancel_blob_path):
        return

    _update_status(
        status_blob_path=status_blob_path,
        status="cancelled",
        stage=stage,
        progress_pct=0,
        message="APC job cancelled before next processing checkpoint.",
        extra={
            "cancelled_at": utc_now(),
            "cancel_requested": True,
        },
    )

    raise RuntimeError("APC job cancelled by user request.")


def _routing_from_payload(payload: dict[str, Any]) -> AzureRoutingConfig:
    workspace = str(payload.get("workspace") or "capture").strip().lower()

    routing = AzureRoutingConfig.from_args(
        workspace=workspace,
        client=payload["client"],
        project=payload["project"],
        processing_account=_processing_account(),
        review_account=_review_account(),
        processing_container=_processing_container(),
        review_container=_review_container(workspace),
        azure_write=bool(payload.get("azure_write", True)),
        allow_same_account=False,
    )

    return routing


def _db_path(job_id: str) -> str:
    root = Path(os.getenv("APC_WORKER_DB_ROOT", "/tmp/apc_worker_db"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / f"{job_id}.db")

def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _summarize_result_for_status(result_dict: dict[str, Any]) -> dict[str, Any]:
    report = (
        result_dict.get("report")
        or result_dict.get("summary")
        or result_dict.get("job_report")
        or {}
    )

    report_job = report.get("job") or {}
    report_ocr = report.get("ocr") or {}
    report_cost = report.get("cost") or {}

    review_upload = result_dict.get("review_upload") or {}
    report_upload = result_dict.get("report_upload") or {}
    hash_index_upload = result_dict.get("hash_index_upload") or {}
    archive_upload = result_dict.get("archive_upload") or {}

    downloads = result_dict.get("downloads") or []
    warnings = result_dict.get("warnings") or []

    review_uploads = review_upload.get("uploads") or []
    uploaded_reports = report_upload.get("uploaded_reports") or []

    source_file_count = (
        report_job.get("source_file_count")
        or result_dict.get("source_file_count")
        or _count_list(downloads)
    )

    expanded_file_count = (
        report_job.get("expanded_file_count")
        or result_dict.get("expanded_file_count")
        or source_file_count
    )

    unique_doc_count = (
        report_job.get("unique_doc_count")
        or result_dict.get("unique_doc_count")
        or review_upload.get("planned_docs")
        or hash_index_upload.get("added_count")
        or 0
    )

    duplicate_doc_count = (
        report_job.get("duplicate_doc_count")
        or result_dict.get("duplicate_doc_count")
        or 0
    )

    ocr_page_count = (
        report_job.get("ocr_page_count")
        or report_ocr.get("estimated_pages")
        or report_ocr.get("pages")
        or result_dict.get("ocr_page_count")
        or 0
    )

    estimated_azure_cost_usd = (
        report_job.get("estimated_azure_cost_usd")
        or report_cost.get("total_estimated_azure_cost_usd")
        or result_dict.get("estimated_azure_cost_usd")
        or 0
    )

    return {
        "apc_job_id": (
            result_dict.get("job_id")
            or (result_dict.get("routing") or {}).get("job_id")
            or (result_dict.get("review_upload") or {}).get("job_id")
            or (result_dict.get("report_upload") or {}).get("job_id")
        ),
        "source_file_count": source_file_count,
        "expanded_file_count": expanded_file_count,
        "unique_doc_count": unique_doc_count,
        "duplicate_doc_count": duplicate_doc_count,
        "ocr_page_count": ocr_page_count,
        "ocr_candidate_files": report_ocr.get("candidate_files") or 0,
        "ocr_estimated_pages": report_ocr.get("estimated_pages") or ocr_page_count,
        "ocr_estimated_cost_usd": report_ocr.get("estimated_cost_usd") or 0,
        "estimated_azure_cost_usd": estimated_azure_cost_usd,
        "native_text_upload_count": _count_list(review_uploads),
        "report_upload_count": _count_list(uploaded_reports),
        "warning_count": _count_list(warnings),
        "archive_upload_count": archive_upload.get("archived_count") or 0,
        "latest_file_name": (
            downloads[-1].get("file_name")
            if downloads and isinstance(downloads[-1], dict)
            else ""
        ),
    }

def _process_data_element_detection_message(
    payload: dict[str, Any],
) -> None:
    detection_job_id = str(
        payload.get("detection_job_id") or ""
    ).strip()

    workspace = str(
        payload.get("workspace") or "capture"
    ).strip().lower()

    client = str(
        payload.get("client") or ""
    ).strip()

    project = str(
        payload.get("project") or ""
    ).strip()

    status_blob_path = str(
        payload.get("status_blob_path") or ""
    ).strip()

    if not detection_job_id:
        raise ValueError(
            "Detection queue message missing detection_job_id"
        )

    if not client:
        raise ValueError(
            "Detection queue message missing client"
        )

    if not project:
        raise ValueError(
            "Detection queue message missing project"
        )

    if not status_blob_path:
        raise ValueError(
            "Detection queue message missing status_blob_path"
        )

    db = LedgerDB(_db_path(detection_job_id))

    try:
        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="starting",
            progress_pct=5,
            message="Data Element Detection worker accepted job.",
            extra={
                "current_step": (
                    "Worker accepted queued Data Element Detection job."
                ),
                "worker_started_at": utc_now(),
                "job_type": "data_element_detection",
                "detection_job_id": detection_job_id,
                "source_job_id": payload.get("source_job_id"),
                "client": client,
                "project": project,
                "workspace": workspace,
            },
        )

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="preparing_detection",
            progress_pct=15,
            message=(
                "Preparing staged text for Data Element Detection."
            ),
            extra={
                "current_step": (
                    "Downloading ingestion-complete staged text."
                ),
            },
        )

        result = run_data_element_detection_job(
            db=db,
            payload=payload,
        )

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
                    "Writing detection totals and entity counts."
                ),
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
                    0,
                ),
                "entity_type_counts": result.get(
                    "entity_type_counts",
                    [],
                ),
            },
        )

        existing_status = _read_json_blob(
            status_blob_path,
            default={},
        )

        existing_events = (
            existing_status.get("events") or []
        )

        if not isinstance(existing_events, list):
            existing_events = []

        completed_event = _status_event(
            status="completed",
            stage="completed",
            progress_pct=100,
            message="Data Element Detection completed.",
            extra={
                "current_step": (
                    "Detection completed and impact assessment is ready."
                ),
            },
        )

        final_status = {
            **existing_status,
            **result,
            "job_type": "data_element_detection",
            "detection_job_id": detection_job_id,
            "source_job_id": payload.get("source_job_id"),
            "workspace": workspace,
            "client": client,
            "project": project,
            "status": "completed",
            "stage": "completed",
            "current_stage": "completed",
            "current_step": (
                "Detection completed and impact assessment is ready."
            ),
            "progress_pct": 100,
            "message": "Data Element Detection completed.",
            "completed_at": utc_now(),
            "updated_at": utc_now(),
            "last_updated_at": utc_now(),
            "events": [
                *existing_events,
                completed_event,
            ],
        }

        _write_json_blob(
            status_blob_path,
            final_status,
        )

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"

        _update_status(
            status_blob_path=status_blob_path,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=(
                f"Data Element Detection worker failed: {message}"
            ),
            extra={
                "current_step": (
                    "Data Element Detection worker failed."
                ),
                "failed_at": utc_now(),
                "error": message,
                "job_type": "data_element_detection",
                "detection_job_id": detection_job_id,
            },
        )

        raise

    finally:
        db.close()

def process_job_message(message_content: str):
    payload = json.loads(message_content)

    job_type = str(
        payload.get("job_type") or "initial_ingestion"
    ).strip().lower()

    if job_type == "data_element_detection":
        source_job_id = str(
            payload.get("source_job_id") or ""
        ).strip()

        detection_workspace = str(
            payload.get("workspace") or "capture"
        ).strip()

        detection_client = str(
            payload.get("client") or ""
        ).strip()

        detection_project = str(
            payload.get("project") or ""
        ).strip()

        if (
            source_job_id
            and _hard_cancelled(
                client=detection_client,
                workspace=detection_workspace,
                project=detection_project,
                job_id=source_job_id,
            )
        ):
            print(
                "Ignoring Detection job for "
                "permanently purged APC job "
                f"{source_job_id}."
            )
            return

        _process_data_element_detection_message(
            payload
        )
        return

    job_id = payload.get("job_id")
    workspace = payload.get("workspace", "capture")
    client = payload.get("client")
    project = payload.get("project")

    if not job_id:
        raise ValueError("APC queue message missing job_id")

    if not client:
        raise ValueError("APC queue message missing client")

    if not project:
        raise ValueError("APC queue message missing project")

    #
    # Permanent hard-cancel barrier.
    #
    # A queue message may be redelivered after its visibility
    # timeout. A purged job must return normally so run_once()
    # acknowledges/deletes that stale queue message.
    #
    if _hard_cancelled(
        client=str(client),
        workspace=str(workspace),
        project=str(project),
        job_id=str(job_id),
    ):
        print(
            "Ignoring permanently purged APC job "
            f"{job_id}."
        )
        return


    job_lease, lease_blob_path = (
        _acquire_job_lease(
            client=str(client),
            workspace=str(workspace),
            project=str(project),
            job_id=str(job_id),
        )
    )

    if job_lease is None:
        print(
            "Ignoring duplicate APC delivery for active job "
            f"{job_id}."
        )
        return
    
    lease_stop = threading.Event()


    def lease_heartbeat() -> None:
        while not lease_stop.wait(20):
            renewed = _renew_job_lease(
                job_lease
            )

            if not renewed:
                print(
                    "APC job lease renewal failed for "
                    f"{job_id}."
                )
                return


    lease_thread = threading.Thread(
        target=lease_heartbeat,
        daemon=True,
    )

    lease_thread.start()
    
    db = None
    
    try:

        request_blob_path = payload.get(
            "request_blob_path",
            f"{client}/{workspace}/{project}/processing_center/jobs/{job_id}/request.json",
        )

        status_blob_path = payload.get(
            "status_blob_path",
            f"{client}/{workspace}/{project}/processing_center/jobs/{job_id}/status.json",
        )
        cancel_blob_path = payload.get("cancel_blob_path")

        routing = _routing_from_payload(payload)

        import apc.azure_layout as azure_layout_module

        routing_debug = {
            "azure_layout_file": getattr(azure_layout_module, "__file__", ""),
            "routing_prefix": routing.prefix,
            "routing_processing_uploads": routing.processing_paths().get("uploads", ""),
            "routing_processing_jobs": routing.processing_paths().get("jobs", ""),
            "routing_review_native": routing.review_paths().get("native", ""),
            "routing_review_text": routing.review_paths().get("text", ""),
            "routing_review_reports": routing.review_paths().get("reports", ""),
        }
    
        db = LedgerDB(
            _db_path(job_id)
        )
        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="starting",
            progress_pct=5,
            message="APC worker accepted job.",
            extra={
                "current_step": "Worker accepted queued APC job.",
                "worker_started_at": utc_now(),
                "request_blob_path": request_blob_path,

                "client": payload.get("client", ""),
                "project": payload.get("project", ""),
                "workspace": payload.get("workspace", ""),
                "matter_id": payload.get("matter_id", ""),

                # Routing debug fields — these tell us exactly where the worker is looking.
                "routing_prefix": routing.prefix,
                "uploads_prefix": routing.processing_paths().get("uploads", ""),
                "work_prefix": routing.processing_paths().get("work", ""),
                "temp_prefix": routing.processing_paths().get("temp", ""),
                "jobs_prefix": routing.processing_paths().get("jobs", ""),
                "telemetry_prefix": routing.processing_paths().get("telemetry", ""),
                "internal_reports_prefix": routing.processing_paths().get(
                    "internal_reports",
                    "",
                ),

                # Review output prefixes — these tell us where Native/Text outputs will land.
                "review_native_prefix": routing.review_paths().get("native", ""),
                "review_text_prefix": routing.review_paths().get("text", ""),
                "review_preview_prefix": routing.review_paths().get("preview", ""),
                "review_metadata_prefix": routing.review_paths().get("metadata", ""),
                "review_reports_prefix": routing.review_paths().get("reports", ""),

                # Storage accounts/containers used by the worker.
                "processing_account": routing.processing_account,
                "processing_container": routing.processing_container,
                "review_account": routing.review_account,
                "review_container": routing.review_container,
            },
        )

        _cancel_if_requested(
            cancel_blob_path=cancel_blob_path,
            status_blob_path=status_blob_path,
            stage="starting",
        )

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="processing",
            progress_pct=15,
            message=(
                "APC processing started. Downloading uploads, expanding "
                "containers, hashing, duplicate checking, OCR pricing, "
                "and staging review outputs."
            ),
            extra={
                "current_step": (
                    "Downloading uploads, expanding containers, hashing, "
                    "checking duplicates, quoting OCR, and staging review outputs."
                ),
            },
        )

        export_dir = os.getenv("APC_EXPORT_DIR", "/tmp/apc_worker_reports")

        def cancellation_checkpoint(
            stage: str = "processing",
        ) -> None:
            if _hard_cancelled(
                client=str(client),
                workspace=str(workspace),
                project=str(project),
                job_id=str(job_id),
            ):
                raise RuntimeError(
                    "APC job hard-cancelled and purged."
                )

            _cancel_if_requested(
                cancel_blob_path=cancel_blob_path,
                status_blob_path=status_blob_path,
                stage=stage,
            )

        def structured_fast_lane(
            *,
            db: LedgerDB,
            job_id: str,
            matter_id: str,
            workspace: str,
        ) -> None:
            cancellation_checkpoint(
                "structured_fast_lane"
            )

            #
            # Persist canonical Processing Set membership
            # after Doc ID assignment.
            #
            # This creates the durable:
            #
            #   Processing Set -> file_id -> Doc ID
            #
            # bridge required by AI Extraction.
            #
            processing_set_manifest_upload = (
                azure_upload_processing_set_manifests(
                    db=db,
                    routing=routing,
                    job_id=job_id,
                    overwrite=True,
                )
            )

            #
            # Existing XL workflow.
            #
            # Keep this branch unchanged.
            #
            xl_upload = (
                azure_upload_xl_files_outputs(
                    db=db,
                    routing=routing,
                    job_id=job_id,
                    azure_write=True,
                    overwrite=True,
                )
            )

            xl_uploaded_rows = (
                xl_upload.get(
                    "uploaded"
                )
                or []
            )

            xl_detection_docs = [
                row
                for row in xl_uploaded_rows
                if (
                    isinstance(
                        row,
                        dict,
                    )
                    and bool(
                        row.get(
                            "is_workbook_child"
                        )
                    )
                    and str(
                        row.get(
                            "text_staged_blob_path"
                        )
                        or ""
                    ).strip()
                )
            ]


            #
            # JSON structured workflow.
            #
            # This is intentionally separate
            # from the existing XL/CSV path.
            #
            json_upload = (
                azure_upload_json_structured_outputs(
                    db=db,
                    routing=routing,
                    job_id=job_id,
                    azure_write=True,
                    overwrite=True,
                )
            )

            json_uploaded_rows = (
                json_upload.get(
                    "uploaded"
                )
                or []
            )

            json_detection_docs = [
                row
                for row in json_uploaded_rows
                if (
                    isinstance(
                        row,
                        dict,
                    )
                    and str(
                        row.get(
                            "source_format"
                        )
                        or ""
                    )
                    .strip()
                    .lower()
                    == "json"
                    and str(
                        row.get(
                            "text_staged_blob_path"
                        )
                        or ""
                    ).strip()
                )
            ]


            if (
                not xl_detection_docs
                and not json_detection_docs
            ):
                _update_status(
                    status_blob_path=(
                        status_blob_path
                    ),
                    status="running",
                    stage=(
                        "structured_fast_lane"
                    ),
                    progress_pct=60,
                    message=(
                        "Structured fast lane "
                        "completed; no structured "
                        "documents required Detection."
                    ),
                    extra={
                        "current_step": (
                            "No workbook worksheet "
                            "children or JSON "
                            "structured documents "
                            "were queued for Detection."
                        ),

                        "xl_fast_lane_uploaded_count":
                            len(
                                xl_uploaded_rows
                            ),

                        "xl_detection_queued_count":
                            0,

                        "json_fast_lane_uploaded_count":
                            len(
                                json_uploaded_rows
                            ),

                        "json_detection_queued_count":
                            0,
                    },
                )
                return


            detection_job_id = (
                f"DET-"
                f"{uuid4().hex[:16].upper()}"
            )

            detection_base = (
                f"{routing.prefix}/"
                "processing_center/"
                "detection/jobs/"
                f"{detection_job_id}"
            )

            detection_request_blob_path = (
                f"{detection_base}/"
                "request.json"
            )

            detection_status_blob_path = (
                f"{detection_base}/"
                "status.json"
            )

            requested_at = utc_now()

            documents: list[
                dict[str, Any]
            ] = []


            #
            # Existing XL Detection documents.
            #
            for row in xl_detection_docs:
                documents.append(
                    {
                        "doc_id": str(
                            row.get(
                                "doc_id"
                            )
                            or ""
                        ),

                        "file_id": (
                            row.get(
                                "file_id"
                            )
                        ),

                        "text_staged_blob_path": (
                            row.get(
                                "text_staged_blob_path"
                            )
                        ),

                        "native_staged_blob_path": (
                            row.get(
                                "native_staged_blob_path"
                            )
                        ),

                        "source_type":
                            "worksheet_csv",

                        "detection_mode":
                            "worksheet_triage",

                        "is_workbook_sheet":
                            True,

                        "parent_file_id": (
                            row.get(
                                "parent_file_id"
                            )
                        ),

                        "original_workbook_file_id":
                            row.get(
                                "parent_file_id"
                            ),
                    }
                )


            #
            # JSON Detection documents.
            #
            for row in json_detection_docs:
                documents.append(
                    {
                        "doc_id": str(
                            row.get(
                                "doc_id"
                            )
                            or ""
                        ),

                        "file_id": (
                            row.get(
                                "file_id"
                            )
                        ),

                        "text_staged_blob_path": (
                            row.get(
                                "text_staged_blob_path"
                            )
                        ),

                        "native_staged_blob_path": (
                            row.get(
                                "native_staged_blob_path"
                            )
                        ),

                        "source_type":
                            "json_structured",

                        "detection_mode":
                            "structured_json",

                        "is_workbook_sheet":
                            False,

                        "source_family": (
                            row.get(
                                "source_family"
                            )
                        ),

                        "source_format": (
                            row.get(
                                "source_format"
                            )
                        ),

                        "source_profile": (
                            row.get(
                                "source_profile"
                            )
                        ),

                        "original_json_filename": (
                            row.get(
                                "original_json_filename"
                            )
                        ),

                        "json_package_id": (
                            row.get(
                                "package_id"
                            )
                        ),

                        "json_package_count": (
                            row.get(
                                "package_count"
                            )
                        ),

                        "json_record_count": (
                            row.get(
                                "record_count"
                            )
                        ),

                        "normalized_source_format": (
                            row.get(
                                "normalized_format"
                            )
                        ),

                        "normalized_source_filename": (
                            row.get(
                                "normalized_filename"
                            )
                        ),
                    }
                )


            if (
                xl_detection_docs
                and json_detection_docs
            ):
                request_detection_mode = (
                    "structured_mixed"
                )

            elif json_detection_docs:
                request_detection_mode = (
                    "structured_json"
                )

            else:
                request_detection_mode = (
                    "worksheet_triage"
                )


            request_payload = {
                "job_type":
                    "data_element_detection",

                "detection_job_id":
                    detection_job_id,

                "workspace":
                    workspace,

                "client":
                    payload.get(
                        "client"
                    ),

                "project":
                    payload.get(
                        "project"
                    ),

                "source_job_id":
                    job_id,

                "doc_ids": [
                    str(
                        document.get(
                            "doc_id"
                        )
                        or ""
                    )
                    for document
                    in documents
                ],

                "detection_mode":
                    request_detection_mode,

                "documents":
                    documents,

                "protocol_name":
                    payload.get(
                        "protocol_name"
                    ),

                "protocol_version":
                    payload.get(
                        "protocol_version"
                    ),

                "include_phi":
                    bool(
                        payload.get(
                            "include_phi",
                            True,
                        )
                    ),

                "requested_by": (
                    payload.get(
                        "requested_by"
                    )
                    or "APC Worker"
                ),

                "requested_at":
                    requested_at,

                "request_blob_path":
                    detection_request_blob_path,

                "status_blob_path":
                    detection_status_blob_path,
            }


            detection_status_payload = {
                "job_type":
                    "data_element_detection",

                "detection_job_id":
                    detection_job_id,

                "workspace":
                    workspace,

                "client":
                    payload.get(
                        "client"
                    ),

                "project":
                    payload.get(
                        "project"
                    ),

                "source_job_id":
                    job_id,

                "status":
                    "queued",

                "stage":
                    "queued",

                "progress_pct":
                    0,

                "selected_doc_count":
                    len(
                        documents
                    ),

                "documents_scanned":
                    0,

                "documents_with_hits":
                    0,

                "documents_no_hits":
                    0,

                "documents_nfr":
                    0,

                "documents_exception":
                    0,

                "entity_hit_count":
                    0,

                "message": (
                    "Structured-data "
                    "Detection job queued."
                ),

                "requested_at":
                    requested_at,

                "created_at":
                    utc_now(),

                "updated_at":
                    utc_now(),

                "request_blob_path":
                    detection_request_blob_path,

                "status_blob_path":
                    detection_status_blob_path,
            }


            _write_json_blob(
                detection_request_blob_path,
                request_payload,
            )

            _write_json_blob(
                detection_status_blob_path,
                detection_status_payload,
            )

            queue_result = (
                _send_detection_queue_message(
                    request_payload
                )
            )


            _update_status(
                status_blob_path=(
                    status_blob_path
                ),
                status="running",
                stage=(
                    "structured_fast_lane"
                ),
                progress_pct=60,
                message=(
                    "Structured population "
                    "released to Data Element "
                    "Detection."
                ),
                extra={
                    "current_step": (
                        f"Queued "
                        f"{len(documents):,} "
                        "structured document(s) "
                        "for Detection while "
                        "OCR continues."
                    ),

                    "xl_fast_lane_uploaded_count":
                        len(
                            xl_uploaded_rows
                        ),

                    "xl_detection_queued_count":
                        len(
                            xl_detection_docs
                        ),

                    "json_fast_lane_uploaded_count":
                        len(
                            json_uploaded_rows
                        ),

                    "json_detection_queued_count":
                        len(
                            json_detection_docs
                        ),

                    "structured_detection_job_id":
                        detection_job_id,

                    "structured_detection_queue": (
                        queue_result.get(
                            "queue_name"
                        )
                    ),
                },
            )

        def ocr_dispatch(
            *,
            db: LedgerDB,
            job_id: str,
            matter_id: str,
            workspace: str,
        ) -> None:
            cancellation_checkpoint(
                "ocr_dispatch"
            )

            max_docs_per_set = max(
                1,
                int(
                    os.getenv(
                        "APC_OCR_SET_SIZE",
                        "50",
                    )
                ),
            )

            max_pages_per_set = max(
                1,
                int(
                    os.getenv(
                        "APC_OCR_MAX_PAGES_PER_SET",
                        "250",
                    )
                ),
            )

            ocr_base = (
                f"{routing.prefix}/"
                "processing_center/"
                f"jobs/{job_id}/ocr"
            )

            manifest_blob_path = (
                f"{ocr_base}/manifest.json"
            )

            #
            # Idempotency barrier.
            #
            # If this ingestion job was redelivered after OCR sets were
            # successfully dispatched, do not dispatch the same OCR
            # population again.
            #
            existing_manifest = _read_json_blob(
                manifest_blob_path,
                default={},
            )

            if (
                str(
                    existing_manifest.get("status")
                    or ""
                ).lower()
                == "dispatched"
                and int(
                    existing_manifest.get("set_count")
                    or 0
                )
                > 0
            ):
                _update_status(
                    status_blob_path=status_blob_path,
                    status="running",
                    stage="ocr_dispatch",
                    progress_pct=70,
                    message=(
                        "OCR work was already dispatched; "
                        "duplicate dispatch skipped."
                    ),
                    extra={
                        "current_step": (
                            "Existing durable OCR manifest found. "
                            "No duplicate OCR sets were queued."
                        ),
                        "ocr_set_count": int(
                            existing_manifest.get(
                                "set_count"
                            )
                            or 0
                        ),
                        "ocr_document_count": int(
                            existing_manifest.get(
                                "document_count"
                            )
                            or 0
                        ),
                        "ocr_estimated_pages": int(
                            existing_manifest.get(
                                "estimated_pages"
                            )
                            or 0
                        ),
                    },
                )
                return

            rows = db.query(
                """
                SELECT
                    fpm.*,
                    psf.set_id AS processing_set_id,
                    psf.ordinal AS processing_set_ordinal,
                    ps.set_number AS processing_set_number
                FROM processing_set_file psf
                JOIN processing_set ps
                  ON ps.set_id=psf.set_id
                 AND ps.job_id=psf.job_id
                JOIN file_processing_metrics fpm
                  ON fpm.file_id=psf.file_id
                 AND fpm.job_id=psf.job_id
                WHERE psf.job_id=?
                  AND psf.membership_role='primary'
                  AND coalesce(fpm.is_container,0)=0
                  AND coalesce(fpm.is_denisted,0)=0
                  AND coalesce(fpm.is_duplicate,0)=0
                  AND coalesce(fpm.requires_ocr,0)=1
                ORDER BY
                    ps.set_number,
                    psf.ordinal,
                    fpm.normalized_path,
                    fpm.file_id
                """,
                (job_id,),
            )

            if not rows:
                empty_manifest = {
                    "job_type": "ocr_dispatch",
                    "source_job_id": job_id,
                    "workspace": workspace,
                    "client": str(client),
                    "project": str(project),
                    "status": "not_required",
                    "set_count": 0,
                    "document_count": 0,
                    "estimated_pages": 0,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }

                _write_json_blob(
                    manifest_blob_path,
                    empty_manifest,
                )

                _update_status(
                    status_blob_path=status_blob_path,
                    status="running",
                    stage="ocr_dispatch",
                    progress_pct=70,
                    message="No documents require OCR.",
                    extra={
                        "current_step": (
                            "OCR preflight found no documents "
                            "requiring asynchronous OCR."
                        ),
                        "ocr_set_count": 0,
                        "ocr_document_count": 0,
                        "ocr_estimated_pages": 0,
                    },
                )
                return

            def row_value(
                row: Any,
                *names: str,
            ) -> Any:
                for name in names:
                    try:
                        value = row[name]
                    except Exception:
                        value = None

                    if value not in (
                        None,
                        "",
                    ):
                        return value

                return None

            documents: list[dict[str, Any]] = []

            for row in rows:
                cancellation_checkpoint(
                    "ocr_dispatch"
                )

                doc_id = str(
                    row_value(
                        row,
                        "doc_id",
                        "assigned_doc_id",
                    )
                    or ""
                ).strip()

                file_id = row_value(
                    row,
                    "file_id",
                    "id",
                )

                source_path = str(
                    row_value(
                        row,
                        "source_path",
                        "original_path",
                        "file_path",
                        "path",
                        "normalized_path",
                    )
                    or ""
                ).strip()

                if not doc_id:
                    raise RuntimeError(
                        "OCR dispatch encountered an "
                        "OCR-required document without a Doc ID."
                    )

                if not source_path:
                    raise RuntimeError(
                        f"{doc_id}: OCR-required document "
                        "has no source path."
                    )

                source = Path(source_path)

                if not source.exists():
                    raise RuntimeError(
                        f"{doc_id}: OCR source file does not "
                        f"exist: {source_path}"
                    )

                estimated_pages = int(
                    row_value(
                        row,
                        "ocr_page_count",
                        "page_count",
                    )
                    or 1
                )

                estimated_pages = max(
                    1,
                    estimated_pages,
                )

                suffix = source.suffix.lower()

                if not suffix:
                    suffix = ".bin"

                native_blob_path = (
                    f"{ocr_base}/source/"
                    f"{doc_id}{suffix}"
                )

                _upload_processing_file_blob(
                    local_path=source_path,
                    blob_path=native_blob_path,
                )

                documents.append(
                    {
                        "doc_id": doc_id,
                        "file_id": file_id,
                        "processing_set_id": row_value(
                            row,
                            "processing_set_id",
                        ),
                        "processing_set_number": row_value(
                            row,
                            "processing_set_number",
                        ),
                        "processing_set_ordinal": row_value(
                            row,
                            "processing_set_ordinal",
                        ),
                        "estimated_ocr_pages":
                            estimated_pages,
                        "native_blob_path":
                            native_blob_path,
                        "source_file_name":
                            source.name,
                        "source_extension":
                            suffix,
                    }
                )

            #
            # Build bounded OCR work sets.
            #
            # A set closes when adding the next document would exceed
            # either the configured document limit or page-weight limit.
            #
            ocr_sets: list[list[dict[str, Any]]] = []

            current_set: list[dict[str, Any]] = []
            current_pages = 0

            for document in documents:
                document_pages = max(
                    1,
                    int(
                        document.get(
                            "estimated_ocr_pages"
                        )
                        or 1
                    ),
                )

                exceeds_doc_limit = (
                    len(current_set)
                    >= max_docs_per_set
                )

                exceeds_page_limit = (
                    bool(current_set)
                    and (
                        current_pages
                        + document_pages
                        > max_pages_per_set
                    )
                )

                if (
                    exceeds_doc_limit
                    or exceeds_page_limit
                ):
                    ocr_sets.append(
                        current_set
                    )

                    current_set = []
                    current_pages = 0

                current_set.append(
                    document
                )

                current_pages += (
                    document_pages
                )

            if current_set:
                ocr_sets.append(
                    current_set
                )

            dispatch_sets: list[
                dict[str, Any]
            ] = []

            total_estimated_pages = sum(
                int(
                    document.get(
                        "estimated_ocr_pages"
                    )
                    or 1
                )
                for document in documents
            )

            #
            # Persist the top-level manifest before queueing.
            #
            # Individual set records are added after each queue operation.
            #
            manifest_payload = {
                "job_type": "ocr_dispatch",
                "source_job_id": job_id,
                "matter_id": matter_id,
                "workspace": workspace,
                "client": str(client),
                "project": str(project),
                "status": "dispatching",
                "queue_name": os.getenv(
                    "APC_OCR_QUEUE_NAME",
                    "apc-ocr-set-jobs",
                ),
                "configured_max_docs_per_set":
                    max_docs_per_set,
                "configured_max_pages_per_set":
                    max_pages_per_set,
                "document_count":
                    len(documents),
                "estimated_pages":
                    total_estimated_pages,
                "set_count":
                    len(ocr_sets),
                "sets": [],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }

            _write_json_blob(
                manifest_blob_path,
                manifest_payload,
            )

            for index, set_documents in enumerate(
                ocr_sets,
                start=1,
            ):
                cancellation_checkpoint(
                    "ocr_dispatch"
                )

                #
                # Deterministic set IDs are intentional.
                # If the parent message is ever redelivered,
                # the same set number maps to the same durable path.
                #
                ocr_set_id = (
                    f"OCRSET-{index:06d}"
                )

                set_base = (
                    f"{ocr_base}/sets/"
                    f"{ocr_set_id}"
                )

                request_blob_path = (
                    f"{set_base}/request.json"
                )

                set_status_blob_path = (
                    f"{set_base}/status.json"
                )

                set_estimated_pages = sum(
                    int(
                        document.get(
                            "estimated_ocr_pages"
                        )
                        or 1
                    )
                    for document
                    in set_documents
                )

                requested_at = utc_now()

                request_payload = {
                    "job_type": "ocr_set",
                    "ocr_set_id": ocr_set_id,
                    "source_job_id": job_id,
                    "matter_id": matter_id,
                    "workspace": workspace,
                    "client": str(client),
                    "project": str(project),
                    "processing_account":
                        _processing_account(),
                    "processing_container":
                        _processing_container(),
                    "document_count":
                        len(set_documents),
                    "estimated_pages":
                        set_estimated_pages,
                    "documents":
                        set_documents,
                    "protocol_name":
                        payload.get(
                            "protocol_name"
                        ),
                    "protocol_version":
                        payload.get(
                            "protocol_version"
                        ),
                    "include_phi":
                        bool(
                            payload.get(
                                "include_phi",
                                True,
                            )
                        ),
                    "requested_by": (
                        payload.get(
                            "requested_by"
                        )
                        or "APC Worker"
                    ),
                    "requested_at":
                        requested_at,
                    "request_blob_path":
                        request_blob_path,
                    "status_blob_path":
                        set_status_blob_path,
                }

                set_status_payload = {
                    "job_type": "ocr_set",
                    "ocr_set_id": ocr_set_id,
                    "source_job_id": job_id,
                    "workspace": workspace,
                    "client": str(client),
                    "project": str(project),
                    "status": "queued",
                    "stage": "queued",
                    "progress_pct": 0,
                    "document_count":
                        len(set_documents),
                    "estimated_pages":
                        set_estimated_pages,
                    "documents_completed": 0,
                    "documents_failed": 0,
                    "pages_completed": 0,
                    "message":
                        "OCR set queued.",
                    "requested_at":
                        requested_at,
                    "created_at":
                        utc_now(),
                    "updated_at":
                        utc_now(),
                    "request_blob_path":
                        request_blob_path,
                    "status_blob_path":
                        set_status_blob_path,
                }

                #
                # Persist BOTH blobs before the queue message.
                #
                _write_json_blob(
                    request_blob_path,
                    request_payload,
                )

                _write_json_blob(
                    set_status_blob_path,
                    set_status_payload,
                )

                queue_result = (
                    _send_ocr_queue_message(
                        request_payload
                    )
                )

                dispatch_sets.append(
                    {
                        "ocr_set_id":
                            ocr_set_id,
                        "document_count":
                            len(
                                set_documents
                            ),
                        "estimated_pages":
                            set_estimated_pages,
                        "request_blob_path":
                            request_blob_path,
                        "status_blob_path":
                            set_status_blob_path,
                        "queue_name":
                            queue_result.get(
                                "queue_name"
                            ),
                        "queue_message_id":
                            queue_result.get(
                                "message_id"
                            ),
                    }
                )

            manifest_payload.update(
                {
                    "status":
                        "dispatched",
                    "sets":
                        dispatch_sets,
                    "dispatched_at":
                        utc_now(),
                    "updated_at":
                        utc_now(),
                }
            )

            _write_json_blob(
                manifest_blob_path,
                manifest_payload,
            )

            _update_status(
                status_blob_path=status_blob_path,
                status="running",
                stage="ocr_dispatch",
                progress_pct=70,
                message=(
                    f"Queued {len(documents):,} "
                    "OCR-required document(s) in "
                    f"{len(ocr_sets):,} OCR set(s)."
                ),
                extra={
                    "current_step": (
                        f"OCR dispatch completed: "
                        f"{len(ocr_sets):,} set(s), "
                        f"{len(documents):,} document(s), "
                        f"{total_estimated_pages:,} "
                        "estimated page(s)."
                    ),
                    "ocr_dispatch_status":
                        "dispatched",
                    "ocr_set_count":
                        len(ocr_sets),
                    "ocr_document_count":
                        len(documents),
                    "ocr_estimated_pages":
                        total_estimated_pages,
                    "ocr_manifest_blob_path":
                        manifest_blob_path,
                    "ocr_queue_name":
                        os.getenv(
                            "APC_OCR_QUEUE_NAME",
                            "apc-ocr-set-jobs",
                        ),
                },
            )

        def ingestion_progress(progress: dict[str, Any]) -> None:
            stage_name = str(
                progress.get("stage")
                or progress.get("current_stage")
                or "processing"
            )

            cancellation_checkpoint(
                stage_name
            )

            stage_processed = int(
                progress.get("stage_processed_files") or 0
            )

            stage_total = int(
                progress.get("stage_total_files") or 0
            )

            if stage_total > 0:
                stage_ratio = min(
                    max(stage_processed / stage_total, 0),
                    1,
                )
            else:
                stage_ratio = 0

            #
            # Keep overall processing within 15%-89%.
            # The remaining worker lifecycle owns 90%-100%.
            #
            progress_pct = min(
                89,
                max(
                    15,
                    int(15 + (stage_ratio * 74)),
                ),
            )

            _update_status(
                status_blob_path=status_blob_path,
                status="running",
                stage=stage_name,
                progress_pct=progress_pct,
                message=str(
                    progress.get("current_step")
                    or "APC processing in progress."
                ),
                extra=progress,
            )

        selected_uploads = [
            str(name or "").strip()
            for name in (
                payload.get(
                    "selected_uploads"
                )
                or []
            )
            if str(name or "").strip()
        ]

        if not selected_uploads:
            raise RuntimeError(
                "Tracked APC job has no selected_uploads manifest. "
                "Refusing to process every pending upload."
            )

        result = run_azure_processing_job(
            db=db,
            routing=routing,
            matter_id=payload["matter_id"],
            doc_prefix=payload.get("doc_prefix", "INSYT"),
            enable_ocr_dry_run=bool(payload.get("enable_ocr_dry_run", True)),
            enable_live_ocr=bool(payload.get("enable_live_ocr", False)),
            azure_write=bool(payload.get("azure_write", True)),
            processing_set_size=int(
                payload.get("processing_set_size") or 500
            ),
            overwrite=bool(payload.get("overwrite", True)),
            staging_root=os.getenv("APC_STAGING_ROOT", "/tmp/apc_worker_runs"),
            output_root=os.getenv(
                "APC_OUTPUT_ROOT",
                "/tmp/apc_worker_review_output",
            ),
            export_dir=export_dir,
            clean_staging=bool(payload.get("clean_staging", False)),
            upload_status=False,
            progress_callback=ingestion_progress,
            cancellation_callback=cancellation_checkpoint,
            after_ocr_preflight_callback=structured_fast_lane,
            ocr_dispatch_callback=ocr_dispatch,
            selected_uploads=selected_uploads,
        )

        if hasattr(result, "to_dict"):
            result_dict = result.to_dict()
        elif isinstance(result, dict):
            result_dict = result
        else:
            result_dict = {"result": str(result)}

        result_summary = _summarize_result_for_status(result_dict)

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="post_processing",
            progress_pct=90,
            message="APC processing completed. Preparing reports and final status.",
            extra={
                "current_step": "Processing completed; preparing reports and status.",
                **result_summary,
            },
        )

        _cancel_if_requested(
            cancel_blob_path=cancel_blob_path,
            status_blob_path=status_blob_path,
            stage="post_processing",
        )

        archive_upload = None

        _cancel_if_requested(
            cancel_blob_path=cancel_blob_path,
            status_blob_path=status_blob_path,
            stage="before_archiving_uploads",
        )

        if bool(payload.get("auto_archive_uploads", True)):
            _update_status(
                status_blob_path=status_blob_path,
                status="running",
                stage="archiving_uploads",
                progress_pct=96,
                message="Archiving processed upload files.",
                extra={
                    "current_step": "Archiving processed upload files.",
                    **_summarize_result_for_status(result_dict),
                },
            )

            archive_upload = azure_archive_processing_uploads(
                routing=routing,
                job_id=str(result_dict.get("job_id") or job_id),
                uploads=result_dict.get("downloads") or [],
                delete_original=True,
                export_dir=export_dir,
            )

            result_dict["archive_upload"] = archive_upload

        _cancel_if_requested(
            cancel_blob_path=cancel_blob_path,
            status_blob_path=status_blob_path,
            stage="archiving_uploads",
        )

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="finalizing",
            progress_pct=98,
            message="APC job finalizing status.",
            extra={
                "current_step": "Writing final tracked job status.",
                **_summarize_result_for_status(result_dict),
            },
        )

        final_status_existing = _read_json_blob(status_blob_path, default={})
        final_status_events = final_status_existing.get("events") or []

        if not isinstance(final_status_events, list):
            final_status_events = []

        completed_event = _status_event(
            status=result_dict.get("status", "completed"),
            stage="completed",
            progress_pct=100,
            message=result_dict.get("message", "APC job completed."),
            extra={
                "current_step": "APC job completed.",
                **_summarize_result_for_status(result_dict),
            },
        )

        final_status = {
            **final_status_existing,
            **result_dict,
            **_summarize_result_for_status(result_dict),
            "azure_layout_file": final_status_existing.get("azure_layout_file"),
            "routing_debug": final_status_existing.get("routing_debug"),
            "job_id": job_id,
            "status": result_dict.get("status", "completed"),
            "stage": "completed",
            "current_stage": "completed",
            "current_step": "APC job completed.",
            "progress_pct": 100,
            "message": result_dict.get("message", "APC job completed."),
            "completed_at": utc_now(),
            "updated_at": utc_now(),
            "last_updated_at": utc_now(),
            "cancel_requested": False,
            "events": [*final_status_events, completed_event],
        }

        _write_json_blob(status_blob_path, final_status)
        

    except RuntimeError as exc:
        message = str(exc)

        if "cancelled" in message.lower():
            return

        _update_status(
            status_blob_path=status_blob_path,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=message,
            extra={
                "current_step": "APC worker failed.",
                "failed_at": utc_now(),
                "error": message,
            },
        )
        raise

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"

        _update_status(
            status_blob_path=status_blob_path,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=f"APC worker failed: {message}",
            extra={
                "current_step": "APC worker failed.",
                "failed_at": utc_now(),
                "error": message,
            },
        )
        raise

    finally:
        lease_stop.set()

        try:
            lease_thread.join(timeout=5)
        except Exception:
            pass

        try:
            _release_job_lease(
                job_lease
            )
        except Exception as exc:
            print(
                "Failed to release APC job lease: "
                f"{type(exc).__name__}: {exc}"
            )

        if db is not None:
            db.close()


def run_once():
    from azure.storage.queue import QueueClient

    queue_name = os.getenv("APC_PROCESSING_QUEUE_NAME", "apc-processing-jobs")
    processing_account = _processing_account()

    queue_conn = os.getenv("INSYT_PROCESSING_STORAGE_CONNECTION_STRING")

    if queue_conn:
        queue_client = QueueClient.from_connection_string(
            queue_conn,
            queue_name=queue_name,
        )
    else:
        queue_client = QueueClient(
            account_url=f"https://{processing_account}.queue.core.windows.net",
            queue_name=queue_name,
            credential=DefaultAzureCredential(),
        )

    messages = queue_client.receive_messages(
        messages_per_page=1,
        visibility_timeout=1800,
    )

    processed_any = False

    for message in messages:
        processed_any = True

        print(f"Processing APC queue message: {message.id}")

        try:
            process_job_message(message.content)
            queue_client.delete_message(message)
            print("APC queue message processed and deleted.")
        except Exception as exc:
            print(f"APC worker failed: {type(exc).__name__}: {exc}")
            raise

    if not processed_any:
        print("No APC processing jobs found.")


if __name__ == "__main__":
    run_once()
