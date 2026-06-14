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

    current.update(
        {
            "status": status,
            "stage": stage,
            "progress_pct": progress_pct,
            "message": message,
            "updated_at": utc_now(),
        }
    )

    if status == "running" and not current.get("started_at"):
        current["started_at"] = utc_now()

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
                "worker_started_at": utc_now(),
                "request_blob_path": request_blob_path,
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
            message="APC processing started. Downloading uploads, expanding containers, hashing, duplicate checking, OCR pricing, and promoting outputs.",
        )

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
            output_root=os.getenv("APC_OUTPUT_ROOT", "/tmp/apc_worker_review_output"),
            export_dir=os.getenv("APC_EXPORT_DIR", "/tmp/apc_worker_reports"),
            clean_staging=bool(payload.get("clean_staging", False)),
            upload_status=False,
        )

        result_dict = result.to_dict()

        _cancel_if_requested(
            cancel_blob_path=cancel_blob_path,
            status_blob_path=status_blob_path,
            stage="post_processing",
        )

        _update_status(
            status_blob_path=status_blob_path,
            status="running",
            stage="finalizing",
            progress_pct=95,
            message="APC job finalizing status.",
        )

        final_status = {
            **_read_json_blob(status_blob_path, default={}),
            **result_dict,
            "job_id": job_id,
            "status": result_dict.get("status", "completed"),
            "stage": "completed",
            "progress_pct": 100,
            "message": result_dict.get("message", "APC job completed."),
            "completed_at": utc_now(),
            "updated_at": utc_now(),
            "cancel_requested": False,
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
            progress_pct=0,
            message=message,
            extra={
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
            progress_pct=0,
            message=message,
            extra={
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