from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from apc.azure_blob_adapter import (
    azure_upload_report_files,
    azure_upload_review_outputs,
    azure_update_processed_hash_index,
    azure_archive_processing_uploads,
)
from apc.azure_job_runner import run_azure_processing_job
from apc.azure_layout import AzureRoutingConfig
from apc.config import DEFAULT_SETTINGS
from apc.db import LedgerDB
from apc.reports import export_job_report, job_report_data
from apc.util import utc_now


def _processing_account() -> str:
    return os.getenv("INSYT_PROCESSING_STORAGE_ACCOUNT", "insytprodstorage")


def _processing_container() -> str:
    return os.getenv("INSYT_PROCESSING_CONTAINER", "insyt-capture")


def _review_account() -> str:
    return os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")


def _review_container() -> str:
    return os.getenv("INSYT_REVIEW_CONTAINER", "insyt-capture")


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
            "events": [*existing_events, event][-25:],
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
    return AzureRoutingConfig.from_args(
        workspace=payload["workspace"],
        client=payload["client"],
        project=payload["project"],
        processing_account=_processing_account(),
        review_account=_review_account(),
        processing_container=_processing_container(),
        review_container=_review_container(),
        azure_write=bool(payload.get("azure_write", True)),
        allow_same_account=False,
    )


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

def process_job_message(message_content: str):
    payload = json.loads(message_content)

    job_id = payload["job_id"]
    status_blob_path = payload["status_blob_path"]
    cancel_blob_path = payload.get("cancel_blob_path")
    request_blob_path = payload.get("request_blob_path")

    routing = _routing_from_payload(payload)

    db = LedgerDB(_db_path(job_id))

    try:
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

        result = run_azure_processing_job(
            db=db,
            routing=routing,
            matter_id=payload["matter_id"],
            doc_prefix=payload.get("doc_prefix", "INSYT"),
            enable_ocr_dry_run=bool(payload.get("enable_ocr_dry_run", True)),
            enable_live_ocr=bool(payload.get("enable_live_ocr", False)),
            azure_write=bool(payload.get("azure_write", True)),
            overwrite=bool(payload.get("overwrite", True)),
            staging_root=os.getenv("APC_STAGING_ROOT", "/tmp/apc_worker_runs"),
            output_root=os.getenv(
                "APC_OUTPUT_ROOT",
                "/tmp/apc_worker_review_output",
            ),
            export_dir=export_dir,
            clean_staging=bool(payload.get("clean_staging", False)),
            upload_status=False,
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
            "events": [*final_status_events, completed_event][-25:],
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