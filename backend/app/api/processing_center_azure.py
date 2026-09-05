"""INSYT FastAPI router wrapper for Azure Processing Center v1.0.

Copy this file into the INSYT backend at:
    app/api/processing_center_azure.py

Then include it in the main FastAPI app/router registry:
    from app.api.processing_center_azure import router as processing_center_azure_router
    app.include_router(processing_center_azure_router)

Environment expected in production:
    APC_API_ALLOW_AZURE_WRITE=true
    APC_API_ALLOW_LIVE_OCR=false
    APC_DB_PATH=/tmp/apc.api.db or Postgres-backed adapter later

    INSYT_PROCESSING_STORAGE_ACCOUNT=insytprodstorage
    INSYT_PROCESSING_CONTAINER=insyt-processing

    INSYT_REVIEW_STORAGE_ACCOUNT=insytreviewstorage
    INSYT_REVIEW_CONTAINER_CAPTURE=insyt-capture
    INSYT_REVIEW_CONTAINER_SUMMARIES=insyt-summaries
    INSYT_REVIEW_CONTAINER_DISCOVERY=insyt-discovery
    INSYT_LIVE_SOURCE_STORAGE_ACCOUNT=insytintakestorage
    INSYT_LIVE_SOURCE_CONTAINER_CAPTURE=insyt-capture
    INSYT_LIVE_SOURCE_CONTAINER_SUMMARIES=insyt-summaries
    INSYT_LIVE_SOURCE_CONTAINER_DISCOVERY=insyt-discovery
"""

from __future__ import annotations

import os
import csv
import io
from pathlib import PurePosixPath
from typing import Any, Literal

import json
from datetime import datetime, timezone
from uuid import uuid4

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models.user import User
from app.services.security import require_admin
from app.services.azure_pricing import (
    calculate_document_intelligence_read_quote,
    lookup_document_intelligence_read_price,
)
from apc.azure_blob_adapter import azure_list_uploads, read_processing_job_status
from apc.azure_job_runner import run_azure_processing_job
from apc.azure_layout import AzureRoutingConfig
from apc.db import LedgerDB
from apc.reports import job_report_data
from app.services.storage_paths import (
    build_project_base_path,
    build_project_path,
    build_project_prefix,
)
from app.services.summary_outline_service import build_summary_extract_payload

router = APIRouter(prefix="/api", tags=["processing-center-azure"])


class AzureRunStartRequest(BaseModel):
    client: str = Field(..., description="INSYT client folder/id")
    project: str = Field(..., description="INSYT project folder/id")
    matter_id: str = Field(..., description="Matter/job label")
    doc_prefix: str = "INSYT"
    enable_ocr_dry_run: bool = True
    enable_live_ocr: bool = False
    azure_write: bool = False
    overwrite: bool = False
    clean_staging: bool = False
    auto_archive_uploads: bool = True

class RemoveProcessingUploadsRequest(BaseModel):
    client: str
    project: str
    blob_names: list[str] = []
    clear_all: bool = False
    reason: str = "removed_from_processing"

class AzureRunResponse(BaseModel):
    job_id: str | None
    status: str
    message: str | None = None
    routing: dict[str, Any] | None = None
    downloads: list[dict[str, Any]] = []
    review_upload: dict[str, Any] | None = None
    report_upload: dict[str, Any] | None = None
    status_upload: dict[str, Any] | None = None
    hash_index_upload: dict[str, Any] | None = None
    archive_uploads: dict[str, Any] | None = None
    warnings: list[str] = []

class PromoteStagedResultsRequest(BaseModel):
    client: str
    project: str
    job_id: str
    doc_ids: list[str] = []
    promote_all: bool = False
    overwrite: bool = False

class PromoteReviewPopulationRequest(BaseModel):
    """
    Project-wide Promotion Center request for ordinary
    responsive documents destined for INSYT Review.

    The frontend supplies only Doc IDs. The backend resolves
    each document back to its originating APC source job.
    """

    client: str
    project: str
    doc_ids: list[str] = []
    overwrite: bool = False

class SendCyber2PopulationRequest(BaseModel):
    """
    Project-wide Promotion Center request for responsive
    spreadsheet / CSV documents routed to Cyber².

    Cyber² Intake references the existing staged CSV.
    It does not copy the source CSV.
    """

    client: str
    project: str
    doc_ids: list[str] = []

class StartDataElementDetectionRequest(BaseModel):
    client: str
    project: str
    source_job_id: str
    doc_ids: list[str] = []
    detect_all_ready: bool = False
    protocol_name: str | None = None
    protocol_version: str | None = None
    include_phi: bool = True

    #
    # auto:
    #   normal docs -> full
    #   workbook-sheet CSVs -> worksheet_triage
    #
    # full:
    #   force existing exhaustive document detection
    #
    #
    # worksheet_triage:
    #   scan worksheet to EOF and retain the first
    #   validated occurrence of each entity type/subtype
    #
    #
    # iar_full:
    #   exhaustive worksheet scan for client-facing counts
    #
    detection_mode: Literal[
        "auto",
        "full",
        "worksheet_triage",
        "iar_full",
    ] = "auto"

def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _db_path() -> str:
    return os.getenv("APC_DB_PATH", "./apc.api.db")


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

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _queue_name() -> str:
    return os.getenv("APC_PROCESSING_QUEUE_NAME", "apc-processing-jobs")


def _new_job_id() -> str:
    return f"JOB-{uuid4().hex[:16].upper()}"

def _clean_path_segment(value: str | None) -> str:
    return str(value or "").strip().strip("/").replace("\\", "/")


def _storage_project_key(value: str | None) -> str:
    return _clean_path_segment(value).replace(" ", "_")


def _project_base_path(
    workspace: str,
    client: str,
    project: str,
) -> str:
    return build_project_base_path(
        client=_clean_path_segment(client),
        workspace=_clean_path_segment(workspace).lower() or "capture",
        project=_storage_project_key(project),
    )

def _cyber2_intake_document_path(
    *,
    workspace: str,
    client: str,
    project: str,
    doc_id: str,
) -> str:
    return (
        f"{_project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )}/cyber2/intake/documents/{doc_id}.json"
    )

def _job_base_path(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> str:
    return (
        f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
        f"processing_center/jobs/{job_id}"
    )


def _job_status_path(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> str:
    return f"{_job_base_path(workspace=workspace, client=client, project=project, job_id=job_id)}/status.json"


def _job_request_path(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> str:
    return f"{_job_base_path(workspace=workspace, client=client, project=project, job_id=job_id)}/request.json"


def _job_cancel_path(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> str:
    return f"{_job_base_path(workspace=workspace, client=client, project=project, job_id=job_id)}/cancel_request.json"


def _processing_container_client():
    blob_service = _processing_blob_service()
    return blob_service.get_container_client(_processing_container())


def _write_processing_json_blob(
    *,
    blob_path: str,
    payload: dict[str, Any],
    overwrite: bool = True,
) -> dict[str, Any]:
    container_client = _processing_container_client()
    blob_client = container_client.get_blob_client(blob_path)

    data = json.dumps(payload, indent=2, default=str).encode("utf-8")

    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=ContentSettings(content_type="application/json"),
    )

    return {
        "status": "uploaded",
        "storage_account": _processing_account(),
        "container": _processing_container(),
        "blob_path": blob_path,
        "bytes": len(data),
    }


def _read_processing_json_blob(blob_path: str) -> dict[str, Any]:
    container_client = _processing_container_client()
    blob_client = container_client.get_blob_client(blob_path)

    data = blob_client.download_blob().readall()

    return json.loads(data.decode("utf-8"))


def _queue_client() -> QueueClient:
    processing_account = _processing_account()

    if processing_account != "insytprodstorage":
        raise HTTPException(
            status_code=400,
            detail="Queue refused: processing account must be insytprodstorage.",
        )

    try:
        credential = DefaultAzureCredential()

        return QueueClient(
            account_url=f"https://{processing_account}.queue.core.windows.net",
            queue_name=_queue_name(),
            credential=credential,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to create APC queue client: {exc}",
        ) from exc


def _send_apc_queue_message(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        queue = _queue_client()

        try:
            queue.create_queue()
        except Exception:
            # Queue may already exist, or creation may be blocked while send is allowed.
            # Sending below will confirm whether the queue is usable.
            pass

        result = queue.send_message(json.dumps(payload, default=str))

        return {
            "status": "queued",
            "queue_name": _queue_name(),
            "message_id": result.id,
            "inserted_on": str(result.inserted_on),
            "expires_on": str(result.expires_on),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to enqueue APC processing job: {exc}",
        ) from exc

def _routing(
    *,
    workspace: Literal["capture", "discovery", "summaries"],
    client: str,
    project: str,
    azure_write: bool = False,
) -> AzureRoutingConfig:
    return AzureRoutingConfig.from_args(
        workspace=workspace,
        client=client,
        project=project,
        processing_account=_processing_account(),
        review_account=_review_account(),
        processing_container=_processing_container(),
        review_container=_review_container(workspace),
        azure_write=azure_write,
        allow_same_account=False,
    )


def _safe_blob_filename(filename: str | None) -> str:
    clean = (filename or "upload.bin").replace("\\", "/")
    name = PurePosixPath(clean).name.strip()
    return name or "upload.bin"


def _processing_blob_service() -> BlobServiceClient:
    processing_account = _processing_account()

    if processing_account != "insytprodstorage":
        raise HTTPException(
            status_code=400,
            detail=(
                "Processing upload refused: processing account must be "
                "insytprodstorage."
            ),
        )

    credential = DefaultAzureCredential()

    return BlobServiceClient(
        account_url=f"https://{processing_account}.blob.core.windows.net",
        credential=credential,
    )

def _archive_uploads_for_job(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> dict[str, Any]:
    processing_account = _processing_account()
    processing_container = _processing_container()

    blob_service = _processing_blob_service()
    container_client = blob_service.get_container_client(processing_container)

    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    uploads_prefix = f"{base_path}/processing_center/uploads/"
    archive_prefix = f"{base_path}/processing_center/archive/{job_id}/uploads/"

    archived: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    blobs = list(container_client.list_blobs(name_starts_with=uploads_prefix))

    for blob in blobs:
        source_name = blob.name

        if source_name.endswith("/"):
            continue

        relative_name = source_name[len(uploads_prefix):]
        archive_name = f"{archive_prefix}{relative_name}"

        source_blob = container_client.get_blob_client(source_name)
        archive_blob = container_client.get_blob_client(archive_name)

        try:
            source_url = source_blob.url

            archive_blob.start_copy_from_url(source_url)

            props = archive_blob.get_blob_properties()
            copy_status = props.copy.status if props.copy else None

            if copy_status not in {"success", None}:
                raise RuntimeError(f"Archive copy did not complete: {copy_status}")

            source_blob.delete_blob()

            archived.append(
                {
                    "source_path": source_name,
                    "archive_path": archive_name,
                    "size": getattr(blob, "size", None),
                    "status": "archived",
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "source_path": source_name,
                    "archive_path": archive_name,
                    "error": str(exc),
                }
            )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "job_id": job_id,
        "storage_account": processing_account,
        "container": processing_container,
        "uploads_prefix": uploads_prefix,
        "archive_prefix": archive_prefix,
        "archived_count": len(archived),
        "error_count": len(errors),
        "archived": archived,
        "errors": errors,
    }
    
def _remove_processing_uploads(
    *,
    workspace: str,
    client: str,
    project: str,
    blob_names: list[str],
    clear_all: bool = False,
    reason: str = "removed_from_processing",
) -> dict[str, Any]:
    from datetime import datetime, timezone

    processing_account = _processing_account()
    processing_container = _processing_container()

    blob_service = _processing_blob_service()
    container_client = blob_service.get_container_client(processing_container)

    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    uploads_prefix = f"{base_path}/processing_center/uploads/"

    removed_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    removed_prefix = (
        f"{base_path}/processing_center/removed/{removed_at}/uploads/"
    )

    selected_names = {
        str(name or "").strip()
        for name in blob_names
        if str(name or "").strip()
    }

    if clear_all:
        blobs = [
            blob
            for blob in container_client.list_blobs(
                name_starts_with=uploads_prefix
            )
            if not str(blob.name).endswith("/")
            and not str(blob.name).endswith("/.keep")
        ]
    else:
        blobs = []

        for name in selected_names:
            if not name.startswith(uploads_prefix):
                raise HTTPException(
                    status_code=400,
                    detail=f"Upload path is outside processing uploads: {name}",
                )

            try:
                props = (
                    container_client
                    .get_blob_client(name)
                    .get_blob_properties()
                )

                blobs.append(
                    type(
                        "BlobRef",
                        (),
                        {
                            "name": name,
                            "size": getattr(props, "size", 0),
                        },
                    )()
                )

            except Exception as exc:
                raise HTTPException(
                    status_code=404,
                    detail=f"Upload blob not found: {name}",
                ) from exc

    removed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for blob in blobs:
        source_name = str(blob.name)

        if source_name.endswith("/") or source_name.endswith("/.keep"):
            continue

        relative_name = source_name[len(uploads_prefix):]
        removed_name = f"{removed_prefix}{relative_name}"

        source_blob = container_client.get_blob_client(source_name)
        removed_blob = container_client.get_blob_client(removed_name)

        try:
            removed_blob.start_copy_from_url(source_blob.url)

            props = removed_blob.get_blob_properties()
            copy_status = props.copy.status if props.copy else None

            if copy_status not in {"success", None}:
                raise RuntimeError(
                    f"Removal copy did not complete: {copy_status}"
                )

            source_blob.delete_blob()

            removed.append(
                {
                    "source_path": source_name,
                    "removed_path": removed_name,
                    "size": getattr(blob, "size", None),
                    "status": "removed",
                }
            )

        except Exception as exc:
            errors.append(
                {
                    "source_path": source_name,
                    "removed_path": removed_name,
                    "error": str(exc),
                }
            )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "reason": reason,
        "clear_all": clear_all,
        "storage_account": processing_account,
        "container": processing_container,
        "uploads_prefix": uploads_prefix,
        "removed_prefix": removed_prefix,
        "removed_count": len(removed),
        "error_count": len(errors),
        "removed": removed,
        "errors": errors,
    }
    
def _list_processing_job_history(
    *,
    workspace: str,
    client: str,
    project: str,
) -> dict[str, Any]:
    processing_account = _processing_account()
    processing_container = _processing_container()

    blob_service = _processing_blob_service()
    container_client = blob_service.get_container_client(processing_container)

    jobs_prefix = (
        f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
        f"processing_center/jobs/"
    )

    jobs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    blobs = list(container_client.list_blobs(name_starts_with=jobs_prefix))

    status_blobs = [
        blob for blob in blobs
        if blob.name.endswith("/status.json")
    ]

    for blob in status_blobs:
        try:
            blob_client = container_client.get_blob_client(blob.name)

            raw = (
                blob_client.download_blob()
                .readall()
                .decode("utf-8")
            )

            import json

            status = json.loads(raw)

            job_id = (
                status.get("job_id")
                or blob.name.replace(jobs_prefix, "").split("/")[0]
            )

            apc_job_id = (
                status.get("apc_job_id")
                or (status.get("routing") or {}).get("job_id")
                or (status.get("review_upload") or {}).get("job_id")
                or (status.get("report_upload") or {}).get("job_id")
            )

            worker_report = None

            if apc_job_id:
                review_container = _review_container(workspace)

                summary_blob_path = (
                    f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
                    f"processing_center/reports/{apc_job_id}/{apc_job_id}.summary.json"
                )

                worker_report = _read_review_json_blob(
                    container_name=review_container,
                    blob_path=summary_blob_path,
                )

            report = (
                worker_report
                or status.get("report")
                or status.get("summary")
                or status.get("job_report")
                or {}
            )

            report_job = report.get("job") or {}
            report_ocr = report.get("ocr") or {}
            report_cost = report.get("cost") or {}
            review_upload = status.get("review_upload") or {}
            report_upload = status.get("report_upload") or {}
            hash_index_upload = status.get("hash_index_upload") or {}
            archive_upload = status.get("archive_upload") or {}

            downloads = status.get("downloads") or []
            uploaded_native_text = review_upload.get("uploads") or []
            uploaded_reports = report_upload.get("uploaded_reports") or []
            warnings = status.get("warnings") or []

            source_file_count = (
                report_job.get("source_file_count")
                if report_job.get("source_file_count") is not None
                else len(downloads)
            )

            expanded_file_count = (
                report_job.get("expanded_file_count")
                if report_job.get("expanded_file_count") is not None
                else source_file_count
            )

            unique_doc_count = (
                report_job.get("unique_doc_count")
                if report_job.get("unique_doc_count") is not None
                else (
                    review_upload.get("planned_docs")
                    or hash_index_upload.get("added_count")
                    or 0
                )
            )

            duplicate_doc_count = (
                report_job.get("duplicate_doc_count")
                if report_job.get("duplicate_doc_count") is not None
                else 0
            )

            ocr_page_count = (
                report_job.get("ocr_page_count")
                if report_job.get("ocr_page_count") is not None
                else (
                    report_ocr.get("estimated_pages")
                    or report_ocr.get("pages")
                    or 0
                )
            )

            ocr_estimated_cost_usd = (
                report_ocr.get("estimated_cost_usd")
                if report_ocr.get("estimated_cost_usd") is not None
                else 0
            )

            estimated_azure_cost_usd = (
                report_job.get("estimated_azure_cost_usd")
                if report_job.get("estimated_azure_cost_usd") is not None
                else (
                    report_cost.get("total_estimated_azure_cost_usd")
                    or 0
                )
            )

            jobs.append(
                {
                    "job_id": job_id,
                    "apc_job_id": apc_job_id,
                    "status": status.get("status"),
                    "message": status.get("message"),
                    "matter_id": status.get("matter_id"),
                    "workspace": status.get("workspace") or workspace,
                    "client": status.get("client_id") or status.get("client") or client,
                    "project": status.get("project_id") or status.get("project") or project,
                    "generated_at": (
                        report.get("generated_at")
                        or status.get("generated_at")
                    ),
                    "created_at": (
                        report_job.get("created_at")
                        or status.get("created_at")
                    ),
                    "completed_at": (
                        report_job.get("completed_at")
                        or status.get("completed_at")
                    ),
                    "source_file_count": source_file_count,
                    "expanded_file_count": expanded_file_count,
                    "unique_doc_count": unique_doc_count,
                    "duplicate_doc_count": duplicate_doc_count,
                    "ocr_page_count": ocr_page_count,
                    "ocr_candidate_files": report_ocr.get("candidate_files") or 0,
                    "ocr_candidate_bytes": report_ocr.get("candidate_bytes") or 0,
                    "ocr_candidate_gb": report_ocr.get("candidate_gb") or 0,
                    "ocr_estimated_pages": report_ocr.get("estimated_pages") or ocr_page_count,
                    "ocr_estimated_cost_usd": ocr_estimated_cost_usd,
                    "ocr_cost_pct_of_total": report_ocr.get("cost_pct_of_total"),
                    "ocr_reason_counts": report_ocr.get("reason_counts") or {},
                    "non_ocr_estimated_cost_usd": (
                        report_cost.get("non_ocr_estimated_cost_usd") or 0
                    ),
                    "estimated_azure_cost_usd": estimated_azure_cost_usd,
                    "downloaded_count": len(downloads),
                    "native_text_upload_count": len(uploaded_native_text),
                    "report_upload_count": len(uploaded_reports),
                    "warning_count": len(warnings),
                    "hash_index_added_count": hash_index_upload.get("added_count") or 0,
                    "archive_upload_count": archive_upload.get("archived_count") or 0,
                    "report_file_count": len(status.get("report_files") or {}),
                    "promoted_doc_count": (
                        (report.get("review_promotion") or {}).get("promoted_docs")
                        or review_upload.get("planned_docs")
                        or 0
                    ),
                    "history_metrics_source": (
                        "worker_report_summary"
                        if worker_report
                        else "tracked_status_wrapper"
                    ),
                    "actual_azure_cost_status": status.get(
                        "actual_azure_cost_status",
                        "pending_cost_management_ingestion",
                    ),
                    "actual_azure_cost_usd": status.get("actual_azure_cost_usd"),
                    "status_blob_path": blob.name,
                    "last_modified": (
                        blob.last_modified.isoformat()
                        if getattr(blob, "last_modified", None)
                        else None
                    ),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "status_blob_path": blob.name,
                    "error": str(exc),
                }
            )

    jobs.sort(
        key=lambda item: (
            item.get("completed_at")
            or item.get("generated_at")
            or item.get("last_modified")
            or ""
        ),
        reverse=True,
    )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "storage_account": processing_account,
        "container": processing_container,
        "jobs_prefix": jobs_prefix,
        "job_count": len(jobs),
        "error_count": len(errors),
        "jobs": jobs,
        "errors": errors,
    }

@router.get("/{workspace}/processing-center/settings")
def processing_center_settings(
    workspace: Literal["capture", "discovery", "summaries"],
) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "db_path": _db_path(),
        "allow_azure_write": _bool_env("APC_API_ALLOW_AZURE_WRITE", False),
        "allow_live_ocr": _bool_env("APC_API_ALLOW_LIVE_OCR", False),
        "processing_account": _processing_account(),
        "review_account": _review_account(),
        "processing_container": _processing_container(),
        "review_container": _review_container(workspace),
        "live_source_account": _live_source_account(),
        "live_source_container": _live_source_container(workspace),
    }

@router.get("/{workspace}/processing-center/pricing/ocr-read")
def get_processing_center_ocr_read_pricing(
    workspace: Literal["capture", "discovery", "summaries"],
    pages: int = Query(1, ge=0),
    region: str = Query("centralus"),
    currency: str = Query("USD"),
) -> dict[str, Any]:
    try:
        price = lookup_document_intelligence_read_price(
            arm_region_name=region,
            currency_code=currency,
        )

        quote = calculate_document_intelligence_read_quote(
            pages=pages,
            arm_region_name=region,
            currency_code=currency,
        )

        return {
            "workspace": workspace,
            "region": region,
            "currency": currency,
            "pricing_basis": "azure_retail_prices_api",
            "price": price,
            "quote": quote,
            "actual_cost_status": "pending_azure_cost_management_ingestion",
            "actual_cost_usd": None,
        }

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/{workspace}/processing-center/uploads")
def list_processing_uploads(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    try:
        processing_account = _processing_account()
        processing_container = _processing_container()

        blob_service = _processing_blob_service()
        container_client = blob_service.get_container_client(processing_container)

        uploads_prefix = (
            f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
            f"processing_center/uploads/"
        )

        uploads: list[dict[str, Any]] = []

        for blob in container_client.list_blobs(name_starts_with=uploads_prefix):
            blob_name = str(blob.name or "")

            if blob_name.endswith("/"):
                continue

            file_name = blob_name.rsplit("/", 1)[-1]

            if not file_name or file_name == ".keep":
                continue

            uploads.append(
                {
                    "name": file_name,
                    "blob_name": blob_name,
                    "size": int(getattr(blob, "size", 0) or 0),
                    "last_modified": (
                        blob.last_modified.isoformat()
                        if getattr(blob, "last_modified", None)
                        else None
                    ),
                    "content_type": getattr(
                        getattr(blob, "content_settings", None),
                        "content_type",
                        None,
                    ),
                }
            )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,
            "project_storage_key": _storage_project_key(project),
            "project_base_path": _project_base_path(
                workspace=workspace,
                client=client,
                project=project,
            ),
            "apc_path_version": "project-storage-key-v2",
            "storage_account": processing_account,
            "container": processing_container,
            "uploads_prefix": uploads_prefix,
            "uploads": uploads,
            "upload_count": len(uploads),
        }

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{workspace}/processing-center/uploads/upload")
async def upload_to_azure_processing_center(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Form(...),
    project_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    processing_account = _processing_account()
    processing_container = _processing_container()

    if processing_account != "insytprodstorage":
        raise HTTPException(
            status_code=400,
            detail=(
                "Processing upload refused: processing account must be "
                "insytprodstorage."
            ),
        )

    safe_filename = _safe_blob_filename(file.filename)

    blob_path = (
        f"{_project_base_path(workspace=workspace, client=client, project=project_id)}/"
        f"processing_center/uploads/{safe_filename}"
    )

    try:
        content = await file.read()

        blob_service = _processing_blob_service()
        container_client = blob_service.get_container_client(processing_container)
        blob_client = container_client.get_blob_client(blob_path)

        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=file.content_type or "application/octet-stream"
            ),
        )

        return {
            "workspace": workspace,
            "client": client,
            "project": project_id,
            "storage_account": processing_account,
            "container": processing_container,
            "blob_path": blob_path,
            "file_name": safe_filename,
            "size": len(content),
            "content_type": file.content_type or "application/octet-stream",
            "status": "uploaded",
            "message": (
                f"{safe_filename} uploaded to Azure Processing Center."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await file.close()

@router.post("/{workspace}/processing-center/uploads/remove")
def remove_processing_uploads(
    workspace: Literal["capture", "discovery", "summaries"],
    request: RemoveProcessingUploadsRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    if not request.clear_all and not request.blob_names:
        raise HTTPException(
            status_code=400,
            detail="Select at least one upload or set clear_all=true.",
        )

    try:
        return _remove_processing_uploads(
            workspace=workspace,
            client=request.client,
            project=request.project,
            blob_names=request.blob_names,
            clear_all=request.clear_all,
            reason=request.reason,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{workspace}/processing-center/uploads/archive")
def archive_processing_uploads(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
    job_id: str = Query(...),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    if not job_id.strip():
        raise HTTPException(status_code=400, detail="job_id is required.")

    try:
        return _archive_uploads_for_job(
            workspace=workspace,
            client=client,
            project=project,
            job_id=job_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/{workspace}/processing-center/tracked-jobs/start")
def start_tracked_azure_processing_job(
    workspace: Literal["capture", "discovery", "summaries"],
    request: AzureRunStartRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    allow_write = _bool_env("APC_API_ALLOW_AZURE_WRITE", False)
    allow_live_ocr = _bool_env("APC_API_ALLOW_LIVE_OCR", False)

    if request.azure_write and not allow_write:
        raise HTTPException(
            status_code=403,
            detail="Azure writes are disabled for this API.",
        )

    if request.enable_live_ocr and not allow_live_ocr:
        raise HTTPException(
            status_code=403,
            detail="Live OCR is disabled for this API.",
        )

    job_id = _new_job_id()

    request_payload = {
        "job_id": job_id,
        "workspace": workspace,
        "client": request.client,
        "project": request.project,
        "matter_id": request.matter_id,
        "doc_prefix": request.doc_prefix,
        "enable_ocr_dry_run": request.enable_ocr_dry_run,
        "enable_live_ocr": request.enable_live_ocr,
        "azure_write": request.azure_write,
        "overwrite": request.overwrite,
        "clean_staging": request.clean_staging,
        "auto_archive_uploads": request.auto_archive_uploads,
        "requested_by": getattr(admin, "username", None)
        or getattr(admin, "email", None)
        or "INSYT Admin",
        "requested_at": _utc_now(),
    }

    request_blob_path = _job_request_path(
        workspace=workspace,
        client=request.client,
        project=request.project,
        job_id=job_id,
    )

    status_blob_path = _job_status_path(
        workspace=workspace,
        client=request.client,
        project=request.project,
        job_id=job_id,
    )

    status_payload = {
        "job_id": job_id,
        "workspace": workspace,
        "client": request.client,
        "project": request.project,
        "matter_id": request.matter_id,
        "status": "queued",
        "stage": "queued",
        "progress_pct": 0,
        "message": "APC job queued.",
        "requested_by": request_payload["requested_by"],
        "requested_at": request_payload["requested_at"],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "request_blob_path": request_blob_path,
        "status_blob_path": status_blob_path,
        "cancel_requested": False,
    }

    request_upload = _write_processing_json_blob(
        blob_path=request_blob_path,
        payload=request_payload,
        overwrite=True,
    )

    status_upload = _write_processing_json_blob(
        blob_path=status_blob_path,
        payload=status_payload,
        overwrite=True,
    )

    queue_payload = {
        **request_payload,
        "request_blob_path": request_blob_path,
        "status_blob_path": status_blob_path,
        "cancel_blob_path": _job_cancel_path(
            workspace=workspace,
            client=request.client,
            project=request.project,
            job_id=job_id,
        ),
    }

    queue_result = _send_apc_queue_message(queue_payload)

    return {
        **status_payload,
        "request_upload": request_upload,
        "status_upload": status_upload,
        "queue": queue_result,
    }

@router.get("/{workspace}/processing-center/tracked-jobs/{job_id}/status")
def get_tracked_azure_processing_job_status(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    status_blob_path = _job_status_path(
        workspace=workspace,
        client=client,
        project=project,
        job_id=job_id,
    )

    try:
        return _read_processing_json_blob(status_blob_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/{workspace}/processing-center/tracked-jobs/{job_id}/cancel")
def cancel_tracked_azure_processing_job(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str = Query(...),
    project: str = Query(...),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    cancel_blob_path = _job_cancel_path(
        workspace=workspace,
        client=client,
        project=project,
        job_id=job_id,
    )

    cancel_payload = {
        "job_id": job_id,
        "workspace": workspace,
        "client": client,
        "project": project,
        "status": "cancel_requested",
        "requested_by": getattr(admin, "username", None)
        or getattr(admin, "email", None)
        or "INSYT Admin",
        "requested_at": _utc_now(),
        "message": "Cancellation requested. Worker will stop at the next safe checkpoint.",
    }

    cancel_upload = _write_processing_json_blob(
        blob_path=cancel_blob_path,
        payload=cancel_payload,
        overwrite=True,
    )

    status_blob_path = _job_status_path(
        workspace=workspace,
        client=client,
        project=project,
        job_id=job_id,
    )

    try:
        status_payload = _read_processing_json_blob(status_blob_path)
        status_payload["cancel_requested"] = True
        status_payload["cancel_requested_at"] = cancel_payload["requested_at"]
        status_payload["message"] = cancel_payload["message"]
        status_payload["updated_at"] = _utc_now()

        _write_processing_json_blob(
            blob_path=status_blob_path,
            payload=status_payload,
            overwrite=True,
        )
    except Exception:
        status_payload = cancel_payload

    return {
        "status": "cancel_requested",
        "cancel_upload": cancel_upload,
        "job_status": status_payload,
    }


@router.post(
    "/{workspace}/processing-center/azure-run/start",
    response_model=AzureRunResponse,
)
def start_azure_processing(
    workspace: Literal["capture", "discovery", "summaries"],
    request: AzureRunStartRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    allow_write = _bool_env("APC_API_ALLOW_AZURE_WRITE", False)
    allow_live_ocr = _bool_env("APC_API_ALLOW_LIVE_OCR", False)

    if request.azure_write and not allow_write:
        raise HTTPException(
            status_code=403,
            detail="Azure writes are disabled for this API.",
        )

    if request.enable_live_ocr and not allow_live_ocr:
        raise HTTPException(
            status_code=403,
            detail="Live OCR is disabled for this API.",
        )

    routing = _routing(
        workspace=workspace,
        client=request.client,
        project=request.project,
        azure_write=request.azure_write,
    )

    db = LedgerDB(_db_path())

    try:
        db.init_schema()

        result = run_azure_processing_job(
            db=db,
            routing=routing,
            matter_id=request.matter_id,
            doc_prefix=request.doc_prefix,
            enable_ocr_dry_run=request.enable_ocr_dry_run,
            enable_live_ocr=request.enable_live_ocr,
            azure_write=request.azure_write,
            overwrite=request.overwrite,
            staging_root=os.getenv("APC_STAGING_ROOT", ".apc_api_runs"),
            output_root=os.getenv("APC_OUTPUT_ROOT", ".apc_api_review_output"),
            export_dir=os.getenv("APC_EXPORT_DIR", "reports"),
            clean_staging=request.clean_staging,
            upload_status=True,
        )

        result_dict = result.to_dict()
        result_dict["archive_uploads"] = None

        if (
            request.auto_archive_uploads
            and request.azure_write
            and result_dict.get("status") == "completed"
            and result_dict.get("job_id")
        ):
            result_dict["archive_uploads"] = _archive_uploads_for_job(
                workspace=workspace,
                client=request.client,
                project=request.project,
                job_id=str(result_dict["job_id"]),
            )

        return result_dict
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        db.close()


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _get_nested_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is not None and value != "":
            return _safe_number(value, default=default)

    return default


def _get_nested_int(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is not None and value != "":
            return _safe_int(value, default=default)

    return default

def _load_worker_report_summary_for_history(
    *,
    workspace: str,
    client: str,
    project: str,
    job: dict[str, Any],
) -> dict[str, Any] | None:
    """Load worker-generated APC summary JSON for a history row.

    Some history rows are thin wrappers and only include status_blob_path.
    When that happens, load the full tracked status first so we can recover
    apc_job_id / routing.job_id and then read the actual worker report.
    """

    expanded_job = dict(job)

    apc_job_id = (
        expanded_job.get("apc_job_id")
        or (expanded_job.get("routing") or {}).get("job_id")
        or (expanded_job.get("review_upload") or {}).get("job_id")
        or (expanded_job.get("report_upload") or {}).get("job_id")
    )

    status_blob_path = expanded_job.get("status_blob_path")

    if not apc_job_id and status_blob_path:
        try:
            tracked_status = _read_processing_json_blob(status_blob_path)

            if isinstance(tracked_status, dict):
                expanded_job.update(tracked_status)

                apc_job_id = (
                    expanded_job.get("apc_job_id")
                    or (expanded_job.get("routing") or {}).get("job_id")
                    or (expanded_job.get("review_upload") or {}).get("job_id")
                    or (expanded_job.get("report_upload") or {}).get("job_id")
                )
        except Exception:
            apc_job_id = None

    if not apc_job_id:
        return None

    review_container = _review_container(workspace)

    summary_blob_path = (
        f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
        f"processing_center/reports/{apc_job_id}/{apc_job_id}.summary.json"
    )

    return _read_review_json_blob(
        container_name=review_container,
        blob_path=summary_blob_path,
    )

def _normalize_processing_history_job(
    job: dict[str, Any],
    *,
    workspace: str,
    client: str,
    project: str,
) -> dict[str, Any]:
    """Flatten tracked APC worker status into the fields the UI expects.

    Prefer the worker-uploaded report summary when available because it contains
    the completed APC engine metrics. Fall back to tracked status wrapper fields.
    """

    worker_summary = _load_worker_report_summary_for_history(
        workspace=workspace,
        client=client,
        project=project,
        job=job,
    )

    summary = (
        worker_summary
        or job.get("summary")
        or job.get("report")
        or job.get("job_report")
        or {}
    )

    job_summary = summary.get("job") or {}
    ocr_summary = summary.get("ocr") or {}
    cost_summary = summary.get("cost") or {}
    review_promotion = summary.get("review_promotion") or {}

    review_upload = job.get("review_upload") or {}
    report_upload = job.get("report_upload") or {}
    hash_index_upload = job.get("hash_index_upload") or {}
    archive_upload = job.get("archive_upload") or {}

    downloads = job.get("downloads") or []
    warnings = job.get("warnings") or []
    report_files = job.get("report_files") or {}

    native_text_uploads = review_upload.get("uploads") or []
    uploaded_reports = report_upload.get("uploaded_reports") or []

    source_file_count = _get_nested_int(
        job_summary.get("source_file_count"),
        summary.get("source_file_count"),
        job.get("source_file_count"),
        len(downloads),
    )

    expanded_file_count = _get_nested_int(
        job_summary.get("expanded_file_count"),
        summary.get("expanded_file_count"),
        job.get("expanded_file_count"),
        source_file_count,
    )

    unique_doc_count = _get_nested_int(
        job_summary.get("unique_doc_count"),
        summary.get("unique_doc_count"),
        job.get("unique_doc_count"),
        review_upload.get("planned_docs"),
        hash_index_upload.get("added_count"),
        0,
    )

    duplicate_doc_count = _get_nested_int(
        job_summary.get("duplicate_doc_count"),
        summary.get("duplicate_doc_count"),
        job.get("duplicate_doc_count"),
        0,
    )

    ocr_page_count = _get_nested_int(
        job_summary.get("ocr_page_count"),
        ocr_summary.get("estimated_pages"),
        ocr_summary.get("pages"),
        summary.get("ocr_page_count"),
        summary.get("ocr_estimated_pages"),
        job.get("ocr_page_count"),
        0,
    )

    ocr_estimated_cost_usd = _get_nested_number(
        ocr_summary.get("estimated_cost_usd"),
        summary.get("ocr_estimated_cost_usd"),
        summary.get("ocr_estimated_cost"),
        job.get("ocr_estimated_cost_usd"),
        0,
    )

    estimated_azure_cost_usd = _get_nested_number(
        job_summary.get("estimated_azure_cost_usd"),
        cost_summary.get("total_estimated_azure_cost_usd"),
        summary.get("estimated_azure_cost_usd"),
        summary.get("total_estimated_azure_cost"),
        job.get("estimated_azure_cost_usd"),
        0,
    )

    non_ocr_estimated_cost_usd = _get_nested_number(
        cost_summary.get("non_ocr_estimated_cost_usd"),
        summary.get("non_ocr_estimated_cost_usd"),
        job.get("non_ocr_estimated_cost_usd"),
        0,
    )

    ocr_candidate_files = _get_nested_int(
        ocr_summary.get("candidate_files"),
        job.get("ocr_candidate_files"),
        0,
    )

    ocr_candidate_bytes = _get_nested_int(
        ocr_summary.get("candidate_bytes"),
        job.get("ocr_candidate_bytes"),
        0,
    )

    ocr_candidate_gb = _get_nested_number(
        ocr_summary.get("candidate_gb"),
        job.get("ocr_candidate_gb"),
        0,
    )

    promoted_docs = _get_nested_int(
        review_promotion.get("promoted_docs"),
        review_upload.get("planned_docs"),
        0,
    )

    apc_job_id = (
        job.get("apc_job_id")
        or (job.get("routing") or {}).get("job_id")
        or (job.get("review_upload") or {}).get("job_id")
        or (job.get("report_upload") or {}).get("job_id")
    )

    normalized = {
        **job,
        "apc_job_id": apc_job_id,
        "source_file_count": source_file_count,
        "expanded_file_count": expanded_file_count,
        "unique_doc_count": unique_doc_count,
        "duplicate_doc_count": duplicate_doc_count,
        "ocr_page_count": ocr_page_count,
        "ocr_candidate_files": ocr_candidate_files,
        "ocr_candidate_bytes": ocr_candidate_bytes,
        "ocr_candidate_gb": ocr_candidate_gb,
        "ocr_estimated_pages": ocr_page_count,
        "ocr_estimated_cost_usd": ocr_estimated_cost_usd,
        "non_ocr_estimated_cost_usd": non_ocr_estimated_cost_usd,
        "estimated_azure_cost_usd": estimated_azure_cost_usd,
        "downloaded_count": len(downloads),
        "native_text_upload_count": len(native_text_uploads),
        "report_upload_count": len(uploaded_reports),
        "warning_count": len(warnings),
        "hash_index_added_count": _safe_int(hash_index_upload.get("added_count")),
        "archive_upload_count": _safe_int(archive_upload.get("archived_count")),
        "report_file_count": len(report_files),
        "promoted_doc_count": promoted_docs,
        "history_metrics_source": (
            "worker_report_summary" if worker_summary else "tracked_status_wrapper"
        ),
        "actual_azure_cost_status": job.get(
            "actual_azure_cost_status",
            "pending_cost_management_ingestion",
        ),
        "actual_azure_cost_usd": job.get("actual_azure_cost_usd"),
    }

    return normalized


@router.get("/{workspace}/processing-center/job-history")
def get_processing_job_history(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    try:
        history = _list_processing_job_history(
            workspace=workspace,
            client=client,
            project=project,
        )

        jobs = history.get("jobs") or []

        normalized_jobs = [
            _normalize_processing_history_job(
                job,
                workspace=workspace,
                client=client,
                project=project,
            )
            for job in jobs
            if isinstance(job, dict)
        ]

        return {
            **history,
            "jobs": normalized_jobs,
            "cost_basis": {
                "estimated_azure_cost_usd": "estimate_only_not_actual_billed_cost",
                "ocr_estimated_cost_usd": "estimate_only_not_actual_billed_cost",
                "actual_azure_cost_usd": "pending_azure_cost_management_ingestion",
            },
        }

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    
@router.get("/{workspace}/processing-center/jobs/{job_id}")
def get_processing_job(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str = Query(...),
    project: str = Query(...),
    source: Literal["db", "azure"] = Query("db"),
) -> dict[str, Any]:
    routing = _routing(workspace=workspace, client=client, project=project)

    if source == "azure":
        try:
            return read_processing_job_status(routing, job_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    db = LedgerDB(_db_path())

    try:
        db.init_schema()

        row = db.query_one(
            "SELECT * FROM processing_job WHERE job_id=?",
            (job_id,),
        )

        if not row:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")

        return dict(row)
    finally:
        db.close()

def _get_review_blob_service_client() -> BlobServiceClient:
    review_account = os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")
    connection_string = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING", "")

    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    return BlobServiceClient(
        account_url=f"https://{review_account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )

def _live_source_account() -> str:
    return (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_ACCOUNT")
        or os.getenv("INSYT_FILES_STORAGE_ACCOUNT")
        or os.getenv("CDS_INTAKE_STORAGE_ACCOUNT")
        or "insytintakestorage"
    )


def _live_source_container(workspace: str) -> str:
    workspace_key = str(workspace or "capture").strip().lower()

    workspace_env_name = f"INSYT_LIVE_SOURCE_CONTAINER_{workspace_key.upper()}"

    return (
        os.getenv(workspace_env_name)
        or os.getenv("INSYT_FILES_CONTAINER_" + workspace_key.upper())
        or os.getenv("CDS_INTAKE_CONTAINER_" + workspace_key.upper())
        or os.getenv("INSYT_LIVE_SOURCE_CONTAINER")
        or os.getenv("INSYT_FILES_CONTAINER")
        or os.getenv("CDS_INTAKE_CONTAINER")
        or f"insyt-{workspace_key}"
    )


def _get_live_source_blob_service_client() -> BlobServiceClient:
    connection_string = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("INSYT_FILES_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_INTAKE_STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_CDS_INTAKE_STORAGE_CONNECTION_STRING")
        or ""
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    live_account = _live_source_account()

    return BlobServiceClient(
        account_url=f"https://{live_account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )


def _live_source_blob_exists(
    *,
    workspace: str,
    blob_path: str,
) -> bool:
    try:
        blob_service = _get_live_source_blob_service_client()
        blob_client = blob_service.get_blob_client(
            container=_live_source_container(workspace),
            blob=blob_path,
        )

        return bool(blob_client.exists())

    except Exception:
        return False


def _write_live_source_blob_bytes(
    *,
    workspace: str,
    blob_path: str,
    data: bytes,
    overwrite: bool = False,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    blob_service = _get_live_source_blob_service_client()
    container_name = _live_source_container(workspace)

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_path,
    )

    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=ContentSettings(content_type=content_type),
    )

    return {
        "status": "uploaded",
        "storage_account": _live_source_account(),
        "container": container_name,
        "blob_path": blob_path,
        "bytes": len(data),
        "content_type": content_type,
    }

def _build_summary_extract_blob_path_from_text_path(text_blob_path: str) -> str:
    """
    Converts:
      source/text/INSYT000000001.txt

    Into:
      source/summary_extracts/INSYT000000001.json
    """

    extract_blob_path = str(text_blob_path or "").replace(
        "/source/text/",
        "/source/summary_extracts/",
    )

    if extract_blob_path.endswith(".txt"):
        extract_blob_path = extract_blob_path[:-4] + ".json"
    elif not extract_blob_path.endswith(".json"):
        extract_blob_path = f"{extract_blob_path}.json"

    return extract_blob_path


def _write_live_source_json_blob(
    *,
    workspace: str,
    blob_path: str,
    payload: dict[str, Any],
    overwrite: bool = True,
) -> dict[str, Any]:
    data = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return _write_live_source_blob_bytes(
        workspace=workspace,
        blob_path=blob_path,
        data=data,
        overwrite=overwrite,
        content_type="application/json; charset=utf-8",
    )


def _create_live_summary_extract_from_text(
    *,
    workspace: str,
    doc_id: str,
    native_dest: str,
    text_dest: str,
    native_source: str,
    text_bytes: bytes,
    overwrite: bool = True,
) -> dict[str, Any] | None:
    """
    Summaries-only post-promotion step.

    Uses the Processing Center staged/promoted text, which may include OCR,
    to create:
      source/summary_extracts/{doc_id}.json

    Does not modify the native PDF.
    """

    if workspace != "summaries":
        return None

    text = (text_bytes or b"").decode("utf-8", errors="replace")

    summary_extract_dest = _build_summary_extract_blob_path_from_text_path(
        text_dest,
    )

    payload = build_summary_extract_payload(
        text=text,
        doc_id=doc_id,
        source_pdf_name=str(native_source or native_dest or "").rsplit("/", 1)[-1],
        native_pdf_path=native_dest,
        text_path=text_dest,
        workspace=workspace,
    )

    upload = _write_live_source_json_blob(
        workspace=workspace,
        blob_path=summary_extract_dest,
        payload=payload,
        overwrite=overwrite,
    )

    return {
        "summary_extract_destination": summary_extract_dest,
        "summary_extract_upload": upload,
        "summary_extract_created": True,
        "summary_extract_section_count": payload.get("section_count", 0),
    }


def _read_review_json_blob(
    *,
    container_name: str,
    blob_path: str,
) -> dict[str, Any] | None:
    try:
        blob_service = _get_review_blob_service_client()
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_path,
        )

        if not blob_client.exists():
            return None

        raw = blob_client.download_blob().readall()
        return json.loads(raw.decode("utf-8"))

    except Exception:
        return None


def _read_review_text_blob(
    *,
    container_name: str,
    blob_path: str,
) -> str | None:
    try:
        blob_service = _get_review_blob_service_client()
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_path,
        )

        if not blob_client.exists():
            return None

        raw = blob_client.download_blob().readall()
        return raw.decode("utf-8", errors="replace")

    except Exception:
        return None

def _read_review_blob_bytes(
    *,
    container_name: str,
    blob_path: str,
) -> bytes | None:
    try:
        blob_service = _get_review_blob_service_client()
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_path,
        )

        if not blob_client.exists():
            return None

        return blob_client.download_blob().readall()

    except Exception:
        return None

def _review_blob_exists(
    *,
    container_name: str,
    blob_path: str,
) -> bool:
    try:
        blob_service = _get_review_blob_service_client()
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_path,
        )

        return bool(blob_client.exists())

    except Exception:
        return False

def _write_review_blob_bytes(
    *,
    container_name: str,
    blob_path: str,
    data: bytes,
    overwrite: bool = False,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    blob_service = _get_review_blob_service_client()
    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_path,
    )

    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=ContentSettings(content_type=content_type),
    )

    return {
        "status": "uploaded",
        "blob_path": blob_path,
        "bytes": len(data),
        "content_type": content_type,
    }


def _list_review_blobs(
    *,
    container_name: str,
    prefix: str,
) -> list[dict[str, Any]]:
    blob_service = _get_review_blob_service_client()
    container_client = blob_service.get_container_client(container_name)

    rows: list[dict[str, Any]] = []

    for blob in container_client.list_blobs(name_starts_with=prefix):
        if str(blob.name).endswith("/"):
            continue

        rows.append(
            {
                "name": blob.name,
                "size": int(getattr(blob, "size", 0) or 0),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if getattr(blob, "last_modified", None)
                    else None
                ),
            }
        )

    return rows


def _load_worker_report_for_job(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> dict[str, Any] | None:
    review_container = _review_container(workspace)

    summary_blob_path = (
        f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
        f"processing_center/reports/{job_id}/{job_id}.summary.json"
    )

    return _read_review_json_blob(
        container_name=review_container,
        blob_path=summary_blob_path,
    )


def _build_staged_results_payload(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> dict[str, Any]:
    review_container = _review_container(workspace)
    review_account = os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")

    staged_prefix = (
        f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
        f"processing_center/staged/{job_id}"
    )

    native_prefix = f"{staged_prefix}/native/"
    text_prefix = f"{staged_prefix}/text/"

    native_blobs = _list_review_blobs(
        container_name=review_container,
        prefix=native_prefix,
    )

    text_blobs = _list_review_blobs(
        container_name=review_container,
        prefix=text_prefix,
    )

    text_by_doc_id: dict[str, dict[str, Any]] = {}
    for blob in text_blobs:
        name = str(blob.get("name") or "")
        filename = name.rsplit("/", 1)[-1]
        doc_id = filename.rsplit(".", 1)[0]
        if doc_id:
            text_by_doc_id[doc_id] = blob

    report = _load_worker_report_for_job(
        workspace=workspace,
        client=client,
        project=project,
        job_id=job_id,
    ) or {}

    files = report.get("files") or []
    file_by_doc_id: dict[str, dict[str, Any]] = {
        str(item.get("doc_id")): item
        for item in files
        if isinstance(item, dict) and item.get("doc_id")
    }

    docs: list[dict[str, Any]] = []

    for native_blob in native_blobs:
        native_path = str(native_blob.get("name") or "")
        native_filename = native_path.rsplit("/", 1)[-1]

        if "." in native_filename:
            doc_id = native_filename.rsplit(".", 1)[0]
            extension = native_filename.rsplit(".", 1)[-1]
        else:
            doc_id = native_filename
            extension = ""

        text_blob = text_by_doc_id.get(doc_id)
        report_file = file_by_doc_id.get(doc_id) or {}
        
        workbook_sheet = (
            report_file.get("workbook_sheet")
            or {}
        )

        if not isinstance(
            workbook_sheet,
            dict,
        ):
            workbook_sheet = {}

        source_type = str(
            workbook_sheet.get(
                "source_type"
            )
            or report_file.get(
                "source_type"
            )
            or ""
        ).strip()

        is_workbook_sheet = bool(
            source_type
            == "workbook_sheet"
            or workbook_sheet.get(
                "derived_from"
            )
            == "workbook_sheet"
        )

        final_native_blob_path = (
            f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
            f"source/native/{native_filename}"
        )

        final_text_blob_path = (
            f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
            f"source/text/{doc_id}.txt"
        )
        
        final_summary_extract_blob_path = (
            f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
            f"source/summary_extracts/{doc_id}.json"
        )

        final_native_exists = _live_source_blob_exists(
            workspace=workspace,
            blob_path=final_native_blob_path,
        )

        final_text_exists = _live_source_blob_exists(
            workspace=workspace,
            blob_path=final_text_blob_path,
        )
        
        final_summary_extract_exists = (
            _live_source_blob_exists(
                workspace=workspace,
                blob_path=final_summary_extract_blob_path,
            )
            if workspace == "summaries"
            else False
        )

        already_promoted = final_native_exists and final_text_exists
        ready_to_promote = bool(text_blob) and not already_promoted

        docs.append(
            {
                "doc_id": doc_id,
                "original_filename": (
                    report_file.get("normalized_path")
                    or report_file.get("original_filename")
                    or native_filename
                ),
                "extension": extension,
                "source_bytes": report_file.get("source_bytes")
                or native_blob.get("size")
                or 0,
                "page_count": report_file.get("page_count") or 0,
                "requires_ocr": bool(report_file.get("requires_ocr") or False),
                "is_duplicate": bool(report_file.get("is_duplicate") or False),
                "is_denisted": bool(report_file.get("is_denisted") or False),
                "family_id": report_file.get("family_id"),
                "file_id": (
                    report_file.get(
                        "file_id"
                    )
                ),
                "parent_file_id": (
                    report_file.get(
                        "parent_file_id"
                    )
                ),
                "source_container_file_id": (
                    report_file.get(
                        "source_container_file_id"
                    )
                ),

                "source_type": (
                    "workbook_sheet"
                    if is_workbook_sheet
                    else "document"
                ),

                "is_workbook_sheet": (
                    is_workbook_sheet
                ),

                "workbook_sheet": (
                    workbook_sheet
                ),

                "original_workbook_file_id": (
                    workbook_sheet.get(
                        "original_workbook_file_id"
                    )
                ),

                "original_workbook_name": (
                    workbook_sheet.get(
                        "original_workbook_name"
                    )
                ),

                "original_workbook_path": (
                    workbook_sheet.get(
                        "original_workbook_path"
                    )
                ),

                "sheet_name": (
                    workbook_sheet.get(
                        "sheet_name"
                    )
                ),

                "sheet_index": (
                    workbook_sheet.get(
                        "sheet_index"
                    )
                ),

                "sheet_visibility": (
                    workbook_sheet.get(
                        "sheet_visibility"
                    )
                ),

                "sheet_nonblank_row_count": (
                    workbook_sheet.get(
                        "sheet_nonblank_row_count"
                    )
                ),

                "sheet_column_count": (
                    workbook_sheet.get(
                        "sheet_column_count"
                    )
                ),

                "triage_status": (
                    workbook_sheet.get(
                        "triage_status"
                    )
                    or (
                        "pending"
                        if is_workbook_sheet
                        else None
                    )
                ),

                "triage_detection_mode": (
                    workbook_sheet.get(
                        "triage_detection_mode"
                    )
                    or (
                        "first_reportable_hit"
                        if is_workbook_sheet
                        else None
                    )
                ),

                "entity_counts_complete": (
                    False
                    if is_workbook_sheet
                    else None
                ),
                "native_staged_blob_path": native_path,
                "text_staged_blob_path": text_blob.get("name") if text_blob else None,
                "native_staged_bytes": native_blob.get("size") or 0,
                "text_staged_bytes": text_blob.get("size") if text_blob else 0,
                "final_native_blob_path": final_native_blob_path,
                "final_text_blob_path": final_text_blob_path,
                "final_summary_extract_blob_path": (
                    final_summary_extract_blob_path
                    if workspace == "summaries"
                    else None
                ),
                "final_native_exists": final_native_exists,
                "final_text_exists": final_text_exists,
                "final_summary_extract_exists": final_summary_extract_exists,
                "promotion_status": "Promoted" if already_promoted else "",
                "promotion_result": "already_promoted" if already_promoted else "",
                "ready_to_promote": ready_to_promote,
            }
        )

    docs.sort(key=lambda item: item.get("doc_id") or "")

    summary = report.get("job") or {}
    ocr = report.get("ocr") or {}
    cost = report.get("cost") or {}

    ready_to_promote_count = sum(
        1 for item in docs if item.get("ready_to_promote")
    )

    promoted_count = sum(
        1
        for item in docs
        if item.get("promotion_status") == "Promoted"
    )

    promotion_status = (
        "Promoted"
        if promoted_count > 0 and ready_to_promote_count == 0
        else ""
    )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "job_id": job_id,
        "storage_account": review_account,
        "container": review_container,
        "staged_storage_account": review_account,
        "staged_container": review_container,
        "live_source_storage_account": _live_source_account(),
        "live_source_container": _live_source_container(workspace),
        "staged_prefix": staged_prefix,
        "native_prefix": native_prefix,
        "text_prefix": text_prefix,
        "doc_count": len(docs),
        "ready_to_promote_count": ready_to_promote_count,
        "promoted_count": promoted_count,
        "promotion_status": promotion_status,
        "docs": docs,
        "summary": {
            "source_file_count": summary.get("source_file_count", len(docs)),
            "expanded_file_count": summary.get("expanded_file_count"),
            "unique_doc_count": summary.get("unique_doc_count", len(docs)),
            "duplicate_doc_count": summary.get("duplicate_doc_count"),
            "ocr_page_count": summary.get("ocr_page_count"),
            "ocr_estimated_cost_usd": ocr.get("estimated_cost_usd"),
            "estimated_azure_cost_usd": summary.get(
                "estimated_azure_cost_usd",
                cost.get("total_estimated_azure_cost_usd"),
            ),
        },
    }

@router.get("/{workspace}/processing-center/staged-results")
def list_processing_center_staged_results(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    try:
        history = _list_processing_job_history(
            workspace=workspace,
            client=client,
            project=project,
        )

        staged_jobs: list[dict[str, Any]] = []

        for job in history.get("jobs") or []:
            if not isinstance(job, dict):
                continue

            apc_job_id = job.get("apc_job_id")
            if not apc_job_id:
                continue

            staged = _build_staged_results_payload(
                workspace=workspace,
                client=client,
                project=project,
                job_id=str(apc_job_id),
            )

            if staged.get("doc_count", 0) > 0:
                staged_jobs.append(
                    {
                        "job_id": apc_job_id,
                        "tracked_job_id": job.get("job_id"),
                        "status": job.get("status"),
                        "promotion_status": staged.get("promotion_status", ""),
                        "completed_at": job.get("completed_at") or job.get("last_modified"),
                        "doc_count": staged.get("doc_count", 0),
                        "ready_to_promote_count": staged.get("ready_to_promote_count", 0),
                        "promoted_count": staged.get("promoted_count", 0),
                        "summary": staged.get("summary"),
                    }
                )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,
            "jobs": staged_jobs,
            "job_count": len(staged_jobs),
        }

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{workspace}/processing-center/staged-results/{job_id}")
def get_processing_center_staged_results(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    try:
        return _build_staged_results_payload(
            workspace=workspace,
            client=client,
            project=project,
            job_id=job_id,
        )

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/{workspace}/processing-center/data-element-detection/ready")
def list_data_element_detection_ready(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    """
    Return documents that completed Initial Ingestion and have staged text
    available for Data Element Detection.

    This does not run detection. It is the staging population shown in the
    Processing Center - Data Element Detection page.
    """

    try:
        history = _list_processing_job_history(
            workspace=workspace,
            client=client,
            project=project,
        )

        jobs: list[dict[str, Any]] = []
        docs: list[dict[str, Any]] = []

        for job in history.get("jobs") or []:
            if not isinstance(job, dict):
                continue

            apc_job_id = job.get("apc_job_id")

            if not apc_job_id:
                continue

            staged = _build_staged_results_payload(
                workspace=workspace,
                client=client,
                project=project,
                job_id=str(apc_job_id),
            )

            staged_docs = staged.get("docs") or []

            job_ready_docs: list[dict[str, Any]] = []

            for doc in staged_docs:
                if not isinstance(doc, dict):
                    continue

                doc_id = str(doc.get("doc_id") or "").strip()
                text_blob_path = doc.get("text_staged_blob_path")

                if not doc_id or not text_blob_path:
                    continue

                detection_ready = bool(
                    text_blob_path
                    and not doc.get("is_duplicate")
                    and not doc.get("is_denisted")
                    and not doc.get("requires_ocr")
                    and str(
                        doc.get("promotion_status") or ""
                    ).strip().lower() != "promoted"
                )

                if not detection_ready:
                    continue

                row = {
                    "doc_id": doc_id,
                    "source_job_id": str(apc_job_id),
                    "tracked_job_id": job.get("job_id"),
                    "original_filename": doc.get("original_filename"),
                    "extension": doc.get("extension"),
                    "source_bytes": doc.get("source_bytes") or 0,
                    "page_count": doc.get("page_count") or 0,
                    "source_type": (
                        doc.get(
                            "source_type"
                        )
                        or "document"
                    ),
                    "is_workbook_sheet": bool(
                        doc.get(
                            "is_workbook_sheet"
                        )
                    ),
                    "original_workbook_name": (
                        doc.get(
                            "original_workbook_name"
                        )
                    ),
                    "sheet_name": (
                        doc.get(
                            "sheet_name"
                        )
                    ),
                    "sheet_index": (
                        doc.get(
                            "sheet_index"
                        )
                    ),
                    "sheet_visibility": (
                        doc.get(
                            "sheet_visibility"
                        )
                    ),
                    "recommended_detection_mode": (
                        "worksheet_triage"
                        if doc.get(
                            "is_workbook_sheet"
                        )
                        else "full"
                    ),
                    "native_staged_blob_path": doc.get(
                        "native_staged_blob_path"
                    ),
                    "text_staged_blob_path": text_blob_path,
                    "text_staged_bytes": doc.get(
                        "text_staged_bytes"
                    ) or 0,
                    "promotion_status": doc.get(
                        "promotion_status"
                    ) or "",
                    "detection_status": "READY",
                }

                docs.append(row)
                job_ready_docs.append(row)

            if job_ready_docs:
                jobs.append(
                    {
                        "source_job_id": str(apc_job_id),
                        "tracked_job_id": job.get("job_id"),
                        "completed_at": (
                            job.get("completed_at")
                            or job.get("last_modified")
                        ),
                        "ready_count": len(job_ready_docs),
                    }
                )

        docs.sort(
            key=lambda item: (
                item.get("source_job_id") or "",
                item.get("doc_id") or "",
            )
        )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,
            "detection_ready_count": len(docs),
            "job_count": len(jobs),
            "jobs": jobs,
            "docs": docs,
            "storage_account": _review_account(),
            "container": _review_container(workspace),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

@router.post("/{workspace}/processing-center/data-element-detection/start")
def start_data_element_detection(
    workspace: Literal["capture", "discovery", "summaries"],
    request: StartDataElementDetectionRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Queue a Data Element Detection run for staged, ingestion-complete docs.
    """

    try:
        staged = _build_staged_results_payload(
            workspace=workspace,
            client=request.client,
            project=request.project,
            job_id=request.source_job_id,
        )

        ready_docs = []

        for doc in staged.get("docs") or []:
            if not isinstance(doc, dict):
                continue

            doc_id = str(doc.get("doc_id") or "").strip()
            text_blob_path = doc.get("text_staged_blob_path")

            if not doc_id or not text_blob_path:
                continue

            if doc.get("is_duplicate"):
                continue

            if doc.get("is_denisted"):
                continue

            if doc.get("requires_ocr"):
                continue

            if str(
                doc.get("promotion_status") or ""
            ).strip().lower() == "promoted":
                continue

            ready_docs.append(doc)

        if request.detect_all_ready:
            selected_docs = ready_docs
        else:
            requested_doc_ids = {
                str(doc_id).strip()
                for doc_id in request.doc_ids
                if str(doc_id).strip()
            }

            selected_docs = [
                doc
                for doc in ready_docs
                if str(doc.get("doc_id") or "") in requested_doc_ids
            ]

        if not selected_docs:
            raise HTTPException(
                status_code=400,
                detail="No detection-ready documents selected.",
            )

        detection_job_id = f"DET-{uuid4().hex[:16].upper()}"

        base_path = _project_base_path(
            workspace=workspace,
            client=request.client,
            project=request.project,
        )

        request_blob_path = (
            f"{base_path}/processing_center/detection/jobs/"
            f"{detection_job_id}/request.json"
        )

        status_blob_path = (
            f"{base_path}/processing_center/detection/jobs/"
            f"{detection_job_id}/status.json"
        )

        requested_by = (
            getattr(admin, "username", None)
            or getattr(admin, "email", None)
            or "INSYT Admin"
        )
        
        def resolve_detection_mode(
            doc: dict[str, Any],
        ) -> str:
            requested_mode = str(
                request.detection_mode
                or "auto"
            ).strip().lower()

            if requested_mode != "auto":
                return requested_mode

            if bool(
                doc.get(
                    "is_workbook_sheet"
                )
            ):
                return "worksheet_triage"

            return "full"

        request_payload = {
            "job_type": "data_element_detection",
            "detection_job_id": detection_job_id,
            "workspace": workspace,
            "client": request.client,
            "project": request.project,
            "source_job_id": request.source_job_id,
            "doc_ids": [
                str(doc.get("doc_id"))
                for doc in selected_docs
            ],
            "detection_mode": (
                request.detection_mode
            ),
            "documents": [
                {
                    "doc_id": str(
                        doc.get(
                            "doc_id"
                        )
                        or ""
                    ),

                    "file_id": (
                        doc.get(
                            "file_id"
                        )
                    ),

                    "text_staged_blob_path": (
                        doc.get(
                            "text_staged_blob_path"
                        )
                    ),

                    "native_staged_blob_path": (
                        doc.get(
                            "native_staged_blob_path"
                        )
                    ),

                    "page_count": (
                        doc.get(
                            "page_count"
                        )
                        or 0
                    ),

                    "source_bytes": (
                        doc.get(
                            "source_bytes"
                        )
                        or 0
                    ),

                    "source_type": (
                        doc.get(
                            "source_type"
                        )
                        or "document"
                    ),

                    "detection_mode": (
                        resolve_detection_mode(
                            doc
                        )
                    ),

                    "is_workbook_sheet": bool(
                        doc.get(
                            "is_workbook_sheet"
                        )
                    ),

                    "parent_file_id": (
                        doc.get(
                            "parent_file_id"
                        )
                    ),

                    "source_container_file_id": (
                        doc.get(
                            "source_container_file_id"
                        )
                    ),

                    "original_workbook_file_id": (
                        doc.get(
                            "original_workbook_file_id"
                        )
                    ),

                    "original_workbook_name": (
                        doc.get(
                            "original_workbook_name"
                        )
                    ),

                    "original_workbook_path": (
                        doc.get(
                            "original_workbook_path"
                        )
                    ),

                    "sheet_name": (
                        doc.get(
                            "sheet_name"
                        )
                    ),

                    "sheet_index": (
                        doc.get(
                            "sheet_index"
                        )
                    ),

                    "sheet_visibility": (
                        doc.get(
                            "sheet_visibility"
                        )
                    ),

                    "sheet_nonblank_row_count": (
                        doc.get(
                            "sheet_nonblank_row_count"
                        )
                    ),

                    "sheet_column_count": (
                        doc.get(
                            "sheet_column_count"
                        )
                    ),

                    "triage_detection_mode": (
                        doc.get(
                            "triage_detection_mode"
                        )
                    ),
                }
                for doc in selected_docs
            ],
            "protocol_name": request.protocol_name,
            "protocol_version": request.protocol_version,
            "include_phi": request.include_phi,
            "requested_by": requested_by,
            "requested_at": _utc_now(),
            "request_blob_path": request_blob_path,
            "status_blob_path": status_blob_path,
        }

        status_payload = {
            "job_type": "data_element_detection",
            "detection_job_id": detection_job_id,
            "workspace": workspace,
            "client": request.client,
            "project": request.project,
            "source_job_id": request.source_job_id,
            "status": "queued",
            "stage": "queued",
            "progress_pct": 0,
            "selected_doc_count": len(selected_docs),
            "documents_scanned": 0,
            "documents_with_hits": 0,
            "documents_no_hits": 0,
            "documents_nfr": 0,
            "documents_exception": 0,
            "entity_hit_count": 0,
            "message": "Data Element Detection job queued.",
            "requested_by": requested_by,
            "requested_at": request_payload["requested_at"],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "request_blob_path": request_blob_path,
            "status_blob_path": status_blob_path,
        }

        request_upload = _write_processing_json_blob(
            blob_path=request_blob_path,
            payload=request_payload,
            overwrite=True,
        )

        status_upload = _write_processing_json_blob(
            blob_path=status_blob_path,
            payload=status_payload,
            overwrite=True,
        )

        queue_payload = {
            **request_payload,
            "status_blob_path": status_blob_path,
        }

        queue_result = _send_apc_queue_message(queue_payload)

        return {
            **status_payload,
            "request_upload": request_upload,
            "status_upload": status_upload,
            "queue": queue_result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

@router.get(
    "/{workspace}/processing-center/data-element-detection/{detection_job_id}/status"
)
def get_data_element_detection_status(
    workspace: Literal["capture", "discovery", "summaries"],
    detection_job_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    status_blob_path = (
        f"{base_path}/processing_center/detection/jobs/"
        f"{detection_job_id}/status.json"
    )

    try:
        return _read_processing_json_blob(
            status_blob_path
        )
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

def _build_detection_impact_assessment(
    *,
    documents: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    hit_doc_ids = {
        str(row.get("doc_id") or "").strip()
        for row in documents
        if str(row.get("classification") or "").strip().upper() == "HIT"
        and str(row.get("doc_id") or "").strip()
    }

    entity_docs_by_type: dict[str, set[str]] = {}
    hit_counts_by_type: dict[str, int] = {}

    docs_with_non_person_elements: set[str] = set()

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        doc_id = str(
            entity.get("doc_id")
            or entity.get("document_id")
            or ""
        ).strip()

        entity_type = str(
            entity.get("entity_type")
            or entity.get("category")
            or entity.get("type")
            or "Unknown"
        ).strip() or "Unknown"

        entity_docs_by_type.setdefault(
            entity_type,
            set(),
        )

        if doc_id:
            entity_docs_by_type[entity_type].add(doc_id)

        hit_counts_by_type[entity_type] = (
            hit_counts_by_type.get(entity_type, 0) + 1
        )

        if (
            doc_id
            and entity_type.casefold() != "person"
        ):
            docs_with_non_person_elements.add(doc_id)

    #
    # Rough Name Count:
    #
    # Count distinct normalized Person values where that same document
    # contains at least one additional non-Person detected element.
    #
    # This is intentionally an estimate and is not identity resolution.
    #
    distinct_names_with_elements: set[str] = set()

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        entity_type = str(
            entity.get("entity_type")
            or entity.get("category")
            or ""
        ).strip()

        if entity_type.casefold() != "person":
            continue

        doc_id = str(
            entity.get("doc_id")
            or entity.get("document_id")
            or ""
        ).strip()

        if doc_id not in docs_with_non_person_elements:
            continue

        detected_value = str(
            entity.get("detected_value")
            or entity.get("text")
            or entity.get("normalized_value")
            or ""
        ).strip()

        normalized_name = " ".join(
            detected_value.split()
        ).casefold()

        if normalized_name:
            distinct_names_with_elements.add(
                normalized_name
            )

    element_breakdown = [
        {
            "entity_type": entity_type,
            "document_count": len(
                entity_docs_by_type.get(
                    entity_type,
                    set(),
                )
            ),
            "hit_count": int(
                hit_counts_by_type.get(
                    entity_type,
                    0,
                )
            ),
        }
        for entity_type in hit_counts_by_type
    ]

    element_breakdown.sort(
        key=lambda row: (
            -int(row.get("document_count") or 0),
            -int(row.get("hit_count") or 0),
            str(row.get("entity_type") or ""),
        )
    )

    return {
        "documents_with_hits_only": len(hit_doc_ids),
        "rough_names_with_attached_elements": len(
            distinct_names_with_elements
        ),
        "total_elements_identified": len(entities),
        "rough_name_method": (
            "Distinct detected Person values appearing in "
            "documents containing at least one additional "
            "non-Person detected element."
        ),
        "element_breakdown": element_breakdown,
    }

@router.get(
    "/{workspace}/processing-center/data-element-detection/{detection_job_id}/summary"
)
def get_data_element_detection_summary(
    workspace: Literal["capture", "discovery", "summaries"],
    detection_job_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    summary_blob_path = (
        f"{base_path}/processing_center/detection/jobs/"
        f"{detection_job_id}/results/summary.json"
    )

    documents_blob_path = (
        f"{base_path}/processing_center/detection/jobs/"
        f"{detection_job_id}/results/documents.json"
    )

    entities_blob_path = (
        f"{base_path}/processing_center/detection/jobs/"
        f"{detection_job_id}/results/entities.json"
    )

    try:
        summary = _read_processing_json_blob(
            summary_blob_path
        )

        documents = _read_processing_json_blob(
            documents_blob_path
        )

        entities = _read_processing_json_blob(
            entities_blob_path
        )

        if not isinstance(documents, list):
            documents = []

        if not isinstance(entities, list):
            entities = []

        hit_docs = [
            row
            for row in documents
            if str(
                row.get("classification") or ""
            ).upper()
            == "HIT"
        ]

        no_hit_docs = [
            row
            for row in documents
            if str(
                row.get("classification") or ""
            ).upper()
            == "NO_HIT"
        ]

        nfr_docs = [
            row
            for row in documents
            if str(
                row.get("classification") or ""
            ).upper()
            == "NFR"
        ]

        exception_docs = [
            row
            for row in documents
            if str(
                row.get("classification") or ""
            ).upper()
            == "EXCEPTION"
        ]
        
        impact_assessment = (
            _build_detection_impact_assessment(
                documents=documents,
                entities=entities,
            )
        )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,
            "detection_job_id": detection_job_id,
            "summary": summary,
            "documents": documents,
            "entities": entities,
            "impact_assessment": impact_assessment,
            "populations": {
                "hits": hit_docs,
                "no_hits": no_hit_docs,
                "nfr": nfr_docs,
                "exceptions": exception_docs,
            },
            "counts": {
                "documents_total": (
                    summary.get(
                        "documents_total",
                        len(documents),
                    )
                ),
                "documents_scanned": (
                    summary.get(
                        "documents_scanned",
                        0,
                    )
                ),
                "documents_with_hits": (
                    summary.get(
                        "documents_with_hits",
                        len(hit_docs),
                    )
                ),
                "documents_no_hits": (
                    summary.get(
                        "documents_no_hits",
                        len(no_hit_docs),
                    )
                ),
                "documents_nfr": (
                    summary.get(
                        "documents_nfr",
                        len(nfr_docs),
                    )
                ),
                "documents_exception": (
                    summary.get(
                        "documents_exception",
                        len(exception_docs),
                    )
                ),
                "entity_hit_count": (
                    summary.get(
                        "entity_hit_count",
                        len(entities),
                    )
                ),
            },
            "entity_type_counts": (
                summary.get(
                    "entity_type_counts",
                    [],
                )
            ),
            "summary_blob_path": summary_blob_path,
            "documents_blob_path": documents_blob_path,
            "entities_blob_path": entities_blob_path,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

@router.get(
    "/{workspace}/processing-center/data-element-detection/"
    "{detection_job_id}/impact-assessment.csv"
)
def export_data_element_detection_impact_assessment(
    workspace: Literal["capture", "discovery", "summaries"],
    detection_job_id: str,
    client: str = Query(...),
    project: str = Query(...),
):
    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    result_prefix = (
        f"{base_path}/processing_center/detection/jobs/"
        f"{detection_job_id}/results"
    )

    summary_blob_path = (
        f"{result_prefix}/summary.json"
    )

    documents_blob_path = (
        f"{result_prefix}/documents.json"
    )

    entities_blob_path = (
        f"{result_prefix}/entities.json"
    )

    try:
        summary = _read_processing_json_blob(
            summary_blob_path
        )

        documents = _read_processing_json_blob(
            documents_blob_path
        )

        entities = _read_processing_json_blob(
            entities_blob_path
        )

        if not isinstance(summary, dict):
            summary = {}

        if not isinstance(documents, list):
            documents = []

        if not isinstance(entities, list):
            entities = []

        impact = _build_detection_impact_assessment(
            documents=documents,
            entities=entities,
        )

        output = io.StringIO(newline="")

        writer = csv.writer(output)

        writer.writerow(
            [
                "INSYT Data Element Detection "
                "Impact Assessment"
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Report Section",
                "Metric / Data Element",
                "Document Count",
                "Total Hits",
                "Value",
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Client",
                "",
                "",
                client,
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Project",
                "",
                "",
                project,
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Detection Job ID",
                "",
                "",
                detection_job_id,
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Detection Run ID",
                "",
                "",
                summary.get("detection_run_id") or "",
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Source Job ID",
                "",
                "",
                summary.get("source_job_id") or "",
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Protocol",
                "",
                "",
                summary.get("protocol_name") or "",
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Protocol Version",
                "",
                "",
                summary.get("protocol_version") or "",
            ]
        )

        writer.writerow(
            [
                "Metadata",
                "Completed Date",
                "",
                "",
                summary.get("completed_at") or "",
            ]
        )

        writer.writerow([])

        writer.writerow(
            [
                "Summary",
                "Document Count With Hits Only",
                impact[
                    "documents_with_hits_only"
                ],
                "",
                "",
            ]
        )

        writer.writerow(
            [
                "Summary",
                (
                    "Rough Count of Names With At Least "
                    "One Data Element Attached"
                ),
                "",
                "",
                impact[
                    "rough_names_with_attached_elements"
                ],
            ]
        )

        writer.writerow(
            [
                "Summary",
                "Total Elements Identified",
                "",
                impact[
                    "total_elements_identified"
                ],
                "",
            ]
        )

        writer.writerow(
            [
                "Summary",
                "Rough Name Count Method",
                "",
                "",
                impact["rough_name_method"],
            ]
        )

        writer.writerow([])

        for row in impact["element_breakdown"]:
            writer.writerow(
                [
                    "Element",
                    row.get("entity_type") or "Unknown",
                    row.get("document_count") or 0,
                    row.get("hit_count") or 0,
                    "",
                ]
            )

        csv_bytes = output.getvalue().encode(
            "utf-8-sig"
        )

        output.close()

        safe_project = (
            str(project or "project")
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        filename = (
            f"{safe_project}_"
            f"{detection_job_id}_"
            f"Impact_Assessment.csv"
        )

        return StreamingResponse(
            iter([csv_bytes]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                )
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to export Impact Assessment: "
                f"{exc}"
            ),
        ) from exc

@router.get(
    "/{workspace}/processing-center/data-element-detection/document-hits"
)
def get_data_element_detection_document_hits(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
    doc_id: str = Query(...),
) -> dict[str, Any]:
    """
    Return Data Element Detection hits for one document.

    Detection results remain stored separately from the source text.
    The frontend uses the returned character offsets to render highlights
    without altering the extracted/OCR text.
    """

    requested_doc_id = str(doc_id or "").strip()

    if not requested_doc_id:
        raise HTTPException(
            status_code=400,
            detail="doc_id is required.",
        )

    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )
    
    document_index_blob_path = (
        f"{base_path}/processing_center/detection/"
        f"documents/{requested_doc_id}.json"
    )

    try:
        document_index = _read_processing_json_blob(
            document_index_blob_path
        )

        if isinstance(document_index, dict):
            indexed_hits = document_index.get("hits") or []

            if not isinstance(indexed_hits, list):
                indexed_hits = []

            return {
                "workspace": workspace,
                "client": client,
                "project": project,
                "doc_id": requested_doc_id,
                "hit_count": len(indexed_hits),
                "detection_job_ids": [
                    document_index.get("latest_detection_job_id")
                ]
                if document_index.get("latest_detection_job_id")
                else [],
                "classification": (
                    document_index.get("classification")
                    or ""
                ),
                "entity_type_counts": (
                    document_index.get("entity_type_counts")
                    or {}
                ),
                "source": "document_index",
                "document_index_blob_path": (
                    document_index_blob_path
                ),
                "hits": indexed_hits,
            }

    except Exception:
        pass

    detection_jobs_prefix = (
        f"{base_path}/processing_center/detection/jobs/"
    )

    try:
        container_client = _processing_container_client()

        entity_result_blobs = [
            blob
            for blob in container_client.list_blobs(
                name_starts_with=detection_jobs_prefix
            )
            if str(blob.name).endswith("/results/entities.json")
        ]

        entity_result_blobs.sort(
            key=lambda blob: (
                getattr(blob, "last_modified", None)
                or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )

        hits: list[dict[str, Any]] = []
        detection_job_ids: list[str] = []

        for blob in entity_result_blobs:
            blob_path = str(blob.name)

            try:
                entities = _read_processing_json_blob(blob_path)
            except Exception:
                continue

            if not isinstance(entities, list):
                continue

            relative_path = blob_path[len(detection_jobs_prefix):]
            detection_job_id = relative_path.split("/", 1)[0]

            job_hits: list[dict[str, Any]] = []

            for entity in entities:
                if not isinstance(entity, dict):
                    continue

                entity_doc_id = str(
                    entity.get("doc_id")
                    or entity.get("document_id")
                    or ""
                ).strip()

                if entity_doc_id != requested_doc_id:
                    continue

                start_offset = entity.get("start_offset")

                if start_offset is None:
                    start_offset = entity.get("offset")

                length = entity.get("length")

                end_offset = entity.get("end_offset")

                try:
                    normalized_start = int(start_offset)
                except (TypeError, ValueError):
                    continue

                if end_offset is not None:
                    try:
                        normalized_end = int(end_offset)
                    except (TypeError, ValueError):
                        continue
                elif length is not None:
                    try:
                        normalized_end = normalized_start + int(length)
                    except (TypeError, ValueError):
                        continue
                else:
                    detected_value = str(
                        entity.get("detected_value")
                        or entity.get("text")
                        or ""
                    )

                    if not detected_value:
                        continue

                    normalized_end = (
                        normalized_start + len(detected_value)
                    )

                if normalized_start < 0:
                    continue

                if normalized_end <= normalized_start:
                    continue

                confidence_raw = (
                    entity.get("confidence")
                    if entity.get("confidence") is not None
                    else entity.get("confidence_score")
                )

                try:
                    confidence = (
                        float(confidence_raw)
                        if confidence_raw is not None
                        else None
                    )
                except (TypeError, ValueError):
                    confidence = None

                entity_type = str(
                    entity.get("entity_type")
                    or entity.get("category")
                    or entity.get("type")
                    or ""
                ).strip()

                entity_subtype = str(
                    entity.get("entity_subtype")
                    or entity.get("subcategory")
                    or ""
                ).strip()

                detected_value = str(
                    entity.get("detected_value")
                    or entity.get("text")
                    or ""
                )

                job_hits.append(
                    {
                        "entity_type": entity_type,
                        "entity_subtype": entity_subtype,
                        "detected_value": detected_value,
                        "confidence": confidence,
                        "start_offset": normalized_start,
                        "end_offset": normalized_end,
                        "protocol": (
                            entity.get("protocol")
                            or entity.get("protocol_name")
                            or ""
                        ),
                        "detector": (
                            entity.get("detector")
                            or entity.get("detector_name")
                            or "azure_language"
                        ),
                        "reportability": (
                            entity.get("reportability")
                            or "UNCLASSIFIED"
                        ),
                        "page_number": (
                            entity.get("page_number")
                            or entity.get("page")
                        ),
                        "detection_job_id": detection_job_id,
                    }
                )

            if job_hits:
                hits.extend(job_hits)

                if detection_job_id not in detection_job_ids:
                    detection_job_ids.append(detection_job_id)

        #
        # A document can appear in more than one detection run.
        # Deduplicate identical detections while preserving the most recent
        # detection result encountered first above.
        #
        deduplicated_hits: list[dict[str, Any]] = []
        seen_hits: set[tuple[Any, ...]] = set()

        for hit in hits:
            key = (
                hit.get("entity_type"),
                hit.get("entity_subtype"),
                hit.get("start_offset"),
                hit.get("end_offset"),
                hit.get("detected_value"),
            )

            if key in seen_hits:
                continue

            seen_hits.add(key)
            deduplicated_hits.append(hit)

        deduplicated_hits.sort(
            key=lambda hit: (
                int(hit.get("start_offset") or 0),
                int(hit.get("end_offset") or 0),
            )
        )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,
            "doc_id": requested_doc_id,
            "hit_count": len(deduplicated_hits),
            "detection_job_ids": detection_job_ids,
            "source": "historical_detection_scan",
            "document_index_blob_path": document_index_blob_path,
            "hits": deduplicated_hits,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to load document detection hits: {exc}",
        ) from exc

def _parse_json_object(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if not value:
        return {}

    try:
        parsed = json.loads(
            str(value)
        )

        return (
            parsed
            if isinstance(parsed, dict)
            else {}
        )

    except Exception:
        return {}


def _load_current_detection_document_indexes(
    *,
    workspace: str,
    client: str,
    project: str,
) -> list[dict[str, Any]]:
    """
    Load the current Detection state for every document in the project.

    Detection workers maintain one canonical document index per Doc ID:

        processing_center/detection/documents/{DOC_ID}.json

    Each index is overwritten by the document's latest Detection run, so
    this directory represents the project's current per-document Detection
    state across multiple Initial Ingestion and Detection jobs.

    This is the authoritative population source for Promotion.
    """

    base_path = _project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    document_index_prefix = (
        f"{base_path}/processing_center/"
        f"detection/documents/"
    )

    container_client = (
        _processing_container_client()
    )

    rows: list[dict[str, Any]] = []

    for blob in container_client.list_blobs(
        name_starts_with=document_index_prefix
    ):
        blob_path = str(
            blob.name or ""
        )

        if (
            not blob_path.endswith(".json")
            or blob_path.endswith("/")
        ):
            continue

        try:
            payload = (
                _read_processing_json_blob(
                    blob_path
                )
            )
        except Exception:
            continue

        if not isinstance(
            payload,
            dict,
        ):
            continue

        doc_id = str(
            payload.get("doc_id")
            or ""
        ).strip()

        if not doc_id:
            continue

        rows.append(
            {
                **payload,
                "document_index_blob_path": (
                    blob_path
                ),
                "document_index_last_modified": (
                    blob.last_modified.isoformat()
                    if getattr(
                        blob,
                        "last_modified",
                        None,
                    )
                    else None
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            str(
                row.get("source_job_id")
                or ""
            ),
            str(
                row.get("doc_id")
                or ""
            ),
        )
    )

    return rows


@router.get(
    "/{workspace}/processing-center/promotion"
)
def get_processing_center_promotion_population(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    """
    Build the current project-wide Promotion population.

    Promotion is based on the latest Detection state PER DOCUMENT,
    not merely the most recent Detection job.

    Routing:

      workbook-sheet / CSV HIT
          -> Cyber²

      ordinary document HIT
          -> Review

      NO_HIT
          -> retained / No Hits

      NFR
          -> NFR

      EXCEPTION / unknown
          -> Exceptions
    """

    try:
        document_indexes = (
            _load_current_detection_document_indexes(
                workspace=workspace,
                client=client,
                project=project,
            )
        )

        if not document_indexes:
            return {
                "workspace": workspace,
                "client": client,
                "project": project,
                "detection_job_id": None,
                "detection_job_ids": [],
                "source_job_id": None,
                "source_job_ids": [],
                "spreadsheet_hits": [],
                "review_hits": [],
                "no_hits": [],
                "nfr": [],
                "exceptions": [],
                "counts": {
                    "spreadsheet_hits": 0,
                    "review_hits": 0,
                    "no_hits": 0,
                    "nfr": 0,
                    "exceptions": 0,
                    "total": 0,
                },
            }

        source_job_ids = sorted(
            {
                str(
                    row.get(
                        "source_job_id"
                    )
                    or ""
                ).strip()
                for row in document_indexes
                if str(
                    row.get(
                        "source_job_id"
                    )
                    or ""
                ).strip()
            }
        )

        staged_by_doc_id: dict[
            str,
            dict[str, Any],
        ] = {}

        for source_job_id in source_job_ids:
            try:
                staged = (
                    _build_staged_results_payload(
                        workspace=workspace,
                        client=client,
                        project=project,
                        job_id=source_job_id,
                    )
                )
            except Exception:
                continue

            for staged_doc in (
                staged.get("docs")
                or []
            ):
                if not isinstance(
                    staged_doc,
                    dict,
                ):
                    continue

                doc_id = str(
                    staged_doc.get(
                        "doc_id"
                    )
                    or ""
                ).strip()

                if not doc_id:
                    continue

                staged_by_doc_id[
                    doc_id
                ] = staged_doc

        spreadsheet_hits: list[
            dict[str, Any]
        ] = []

        review_hits: list[
            dict[str, Any]
        ] = []

        no_hits: list[
            dict[str, Any]
        ] = []

        nfr: list[
            dict[str, Any]
        ] = []

        exceptions: list[
            dict[str, Any]
        ] = []

        detection_job_ids: set[str] = set()

        for document in document_indexes:
            doc_id = str(
                document.get(
                    "doc_id"
                )
                or ""
            ).strip()

            if not doc_id:
                continue

            staged_doc = (
                staged_by_doc_id.get(
                    doc_id
                )
                or {}
            )

            source_job_id = str(
                document.get(
                    "source_job_id"
                )
                or ""
            ).strip()

            detection_job_id = str(
                document.get(
                    "latest_detection_job_id"
                )
                or ""
            ).strip()

            if detection_job_id:
                detection_job_ids.add(
                    detection_job_id
                )

            classification = str(
                document.get(
                    "classification"
                )
                or ""
            ).strip().upper()

            source_type = str(
                document.get(
                    "source_type"
                )
                or staged_doc.get(
                    "source_type"
                )
                or "document"
            ).strip()

            is_workbook_sheet = bool(
                document.get(
                    "is_workbook_sheet"
                )
                or staged_doc.get(
                    "is_workbook_sheet"
                )
                or source_type
                == "workbook_sheet"
            )

            extension = str(
                staged_doc.get(
                    "extension"
                )
                or ""
            ).strip().lower()

            hits = (
                document.get("hits")
                or []
            )

            if not isinstance(
                hits,
                list,
            ):
                hits = []

            entity_types: set[str] = set()

            for hit in hits:
                if not isinstance(
                    hit,
                    dict,
                ):
                    continue

                entity_type = str(
                    hit.get(
                        "entity_type"
                    )
                    or "Unknown"
                ).strip()

                entity_subtype = str(
                    hit.get(
                        "entity_subtype"
                    )
                    or ""
                ).strip()

                display_type = (
                    f"{entity_type}:"
                    f"{entity_subtype}"
                    if entity_subtype
                    else entity_type
                )

                entity_types.add(
                    display_type
                )

            is_spreadsheet_data = bool(
                is_workbook_sheet
                or extension == "csv"
            )

            if (
                classification == "HIT"
                and is_spreadsheet_data
            ):
                destination = "cyber2"

            elif classification == "HIT":
                destination = "review"

            elif classification == "NO_HIT":
                destination = "no_hits"

            elif classification == "NFR":
                destination = "nfr"

            else:
                destination = "exception"
                
            cyber2_intake_path = None
            cyber2_intake_record = None

            if destination == "cyber2":
                cyber2_intake_path = (
                    _cyber2_intake_document_path(
                        workspace=workspace,
                        client=client,
                        project=project,
                        doc_id=doc_id,
                    )
                )

                try:
                    cyber2_intake_record = (
                        _read_processing_json_blob(
                            cyber2_intake_path
                        )
                    )
                except Exception:
                    cyber2_intake_record = None

            cyber2_sent = bool(
                isinstance(
                    cyber2_intake_record,
                    dict,
                )
            )

            row = {
                "doc_id": doc_id,

                "file_id": (
                    document.get(
                        "file_id"
                    )
                    or staged_doc.get(
                        "file_id"
                    )
                ),

                "source_job_id": (
                    source_job_id
                ),

                "detection_job_id": (
                    detection_job_id
                ),

                "detection_run_id": (
                    document.get(
                        "detection_run_id"
                    )
                ),

                "classification": (
                    classification
                ),

                "destination": (
                    destination
                ),

                "promotion_status": (
                    "Sent to Cyber²"
                    if (
                        destination == "cyber2"
                        and cyber2_sent
                    )
                    else (
                        staged_doc.get(
                            "promotion_status"
                        )
                        or ""
                    )
                ),

                "cyber2_sent": (
                    cyber2_sent
                ),

                "cyber2_intake_index_path": (
                    cyber2_intake_path
                    if destination == "cyber2"
                    else None
                ),

                "original_filename": (
                    staged_doc.get(
                        "original_filename"
                    )
                ),

                "extension": extension,

                "source_type": (
                    source_type
                ),

                "is_workbook_sheet": (
                    is_workbook_sheet
                ),

                "original_workbook_file_id": (
                    document.get(
                        "original_workbook_file_id"
                    )
                    or staged_doc.get(
                        "original_workbook_file_id"
                    )
                ),

                "original_workbook_name": (
                    document.get(
                        "original_workbook_name"
                    )
                    or staged_doc.get(
                        "original_workbook_name"
                    )
                ),

                "sheet_name": (
                    document.get(
                        "sheet_name"
                    )
                    or staged_doc.get(
                        "sheet_name"
                    )
                ),

                "sheet_index": (
                    document.get(
                        "sheet_index"
                    )
                    or staged_doc.get(
                        "sheet_index"
                    )
                ),

                "sheet_visibility": (
                    document.get(
                        "sheet_visibility"
                    )
                    or staged_doc.get(
                        "sheet_visibility"
                    )
                ),

                "native_staged_blob_path": (
                    staged_doc.get(
                        "native_staged_blob_path"
                    )
                ),

                "text_staged_blob_path": (
                    staged_doc.get(
                        "text_staged_blob_path"
                    )
                ),

                "final_native_blob_path": (
                    staged_doc.get(
                        "final_native_blob_path"
                    )
                ),

                "final_text_blob_path": (
                    staged_doc.get(
                        "final_text_blob_path"
                    )
                ),

                "entity_types": sorted(
                    entity_types
                ),

                "profiled_entity_count": (
                    document.get(
                        "profiled_entity_type_count"
                    )
                    if document.get(
                        "profiled_entity_type_count"
                    )
                    is not None
                    else len(hits)
                ),

                "detection_mode": (
                    document.get(
                        "detection_mode"
                    )
                ),

                "type_profile_complete": (
                    document.get(
                        "type_profile_complete"
                    )
                ),

                "entity_counts_complete": (
                    document.get(
                        "entity_counts_complete"
                    )
                ),

                "ready_for_promotion": (
                    classification
                    in {
                        "HIT",
                        "NO_HIT",
                    }
                    and not (
                        destination == "cyber2"
                        and cyber2_sent
                    )
                ),

                "document_index_blob_path": (
                    document.get(
                        "document_index_blob_path"
                    )
                ),

                "latest_detection_at": (
                    document.get(
                        "detected_at"
                    )
                    or document.get(
                        "document_index_last_modified"
                    )
                ),
            }

            if destination == "cyber2":
                spreadsheet_hits.append(
                    row
                )

            elif destination == "review":
                review_hits.append(
                    row
                )

            elif destination == "no_hits":
                no_hits.append(
                    row
                )

            elif destination == "nfr":
                nfr.append(
                    row
                )

            else:
                exceptions.append(
                    row
                )

        def sort_rows(
            rows: list[
                dict[str, Any]
            ],
        ) -> None:
            rows.sort(
                key=lambda item: (
                    str(
                        item.get(
                            "original_workbook_name"
                        )
                        or ""
                    ),
                    int(
                        item.get(
                            "sheet_index"
                        )
                        or 0
                    ),
                    str(
                        item.get(
                            "doc_id"
                        )
                        or ""
                    ),
                )
            )

        sort_rows(
            spreadsheet_hits
        )

        sort_rows(
            review_hits
        )

        sort_rows(
            no_hits
        )

        sort_rows(
            nfr
        )

        sort_rows(
            exceptions
        )

        detection_job_id_list = sorted(
            detection_job_ids
        )

        return {
            "workspace": workspace,
            "client": client,
            "project": project,

            "detection_job_id": (
                detection_job_id_list[-1]
                if detection_job_id_list
                else None
            ),

            "source_job_id": (
                source_job_ids[-1]
                if source_job_ids
                else None
            ),

            "detection_job_ids": (
                detection_job_id_list
            ),

            "source_job_ids": (
                source_job_ids
            ),

            "spreadsheet_hits": (
                spreadsheet_hits
            ),

            "review_hits": (
                review_hits
            ),

            "no_hits": (
                no_hits
            ),

            "nfr": nfr,

            "exceptions": (
                exceptions
            ),

            "counts": {
                "spreadsheet_hits": len(
                    spreadsheet_hits
                ),

                "review_hits": len(
                    review_hits
                ),

                "no_hits": len(
                    no_hits
                ),

                "nfr": len(
                    nfr
                ),

                "exceptions": len(
                    exceptions
                ),

                "total": (
                    len(
                        spreadsheet_hits
                    )
                    + len(
                        review_hits
                    )
                    + len(
                        no_hits
                    )
                    + len(
                        nfr
                    )
                    + len(
                        exceptions
                    )
                ),
            },

            "population_basis": (
                "latest_detection_state_per_doc_id"
            ),

            "document_index_count": (
                len(
                    document_indexes
                )
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to build current "
                "Promotion population: "
                f"{exc}"
            ),
        ) from exc
        

@router.post("/{workspace}/processing-center/promote")
def promote_processing_center_staged_results(
    workspace: Literal["capture", "discovery", "summaries"],
    request: PromoteStagedResultsRequest,
) -> dict[str, Any]:
    try:
        staged = _build_staged_results_payload(
            workspace=workspace,
            client=request.client,
            project=request.project,
            job_id=request.job_id,
        )

        docs = staged.get("docs") or []

        if request.promote_all:
            selected_docs = docs
        else:
            requested_doc_ids = {str(doc_id) for doc_id in request.doc_ids}
            selected_docs = [
                doc for doc in docs
                if str(doc.get("doc_id")) in requested_doc_ids
            ]

        if not selected_docs:
            raise HTTPException(
                status_code=400,
                detail="No staged documents selected for promotion.",
            )

        review_container = _review_container(workspace)

        promoted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for doc in selected_docs:
            doc_id = str(doc.get("doc_id") or "")
            native_source = doc.get("native_staged_blob_path")
            text_source = doc.get("text_staged_blob_path")

            native_dest = doc.get("final_native_blob_path")
            text_dest = doc.get("final_text_blob_path")

            if not native_source or not text_source or not native_dest or not text_dest:
                skipped.append(
                    {
                        "doc_id": doc_id,
                        "status": "skipped_missing_staged_pair",
                    }
                )
                continue

            native_bytes = _read_review_blob_bytes(
                container_name=review_container,
                blob_path=str(native_source),
            )
            text_bytes = _read_review_blob_bytes(
                container_name=review_container,
                blob_path=str(text_source),
            )

            if native_bytes is None or text_bytes is None:
                skipped.append(
                    {
                        "doc_id": doc_id,
                        "status": "skipped_missing_staged_blob",
                        "native_found": native_bytes is not None,
                        "text_found": text_bytes is not None,
                    }
                )
                continue

            native_dest_exists = _live_source_blob_exists(
                workspace=workspace,
                blob_path=str(native_dest),
            )

            text_dest_exists = _live_source_blob_exists(
                workspace=workspace,
                blob_path=str(text_dest),
            )

            if (native_dest_exists or text_dest_exists) and not request.overwrite:
                summary_extract_result = None

                if workspace == "summaries" and native_dest_exists and text_dest_exists:
                    try:
                        summary_extract_dest = (
                            doc.get("final_summary_extract_blob_path")
                            or _build_summary_extract_blob_path_from_text_path(str(text_dest))
                        )

                        summary_extract_exists = _live_source_blob_exists(
                            workspace=workspace,
                            blob_path=str(summary_extract_dest),
                        )

                        if not summary_extract_exists:
                            summary_extract_result = _create_live_summary_extract_from_text(
                                workspace=workspace,
                                doc_id=doc_id,
                                native_dest=str(native_dest),
                                text_dest=str(text_dest),
                                native_source=str(native_source),
                                text_bytes=text_bytes,
                                overwrite=True,
                            )
                        else:
                            summary_extract_result = {
                                "summary_extract_destination": summary_extract_dest,
                                "summary_extract_created": False,
                                "summary_extract_exists": True,
                            }

                    except Exception as summary_extract_exc:
                        summary_extract_result = {
                            "summary_extract_created": False,
                            "summary_extract_error": str(summary_extract_exc),
                        }

                skipped.append(
                    {
                        "doc_id": doc_id,
                        "status": (
                            "already_promoted"
                            if native_dest_exists and text_dest_exists
                            else "skipped_existing_destination"
                        ),
                        "native_destination_exists": native_dest_exists,
                        "text_destination_exists": text_dest_exists,
                        "native_destination": native_dest,
                        "text_destination": text_dest,
                        "summary_extract": summary_extract_result,
                        "message": (
                            "Final source file already exists. "
                            "Set overwrite=true to replace it."
                        ),
                    }
                )
                continue

            try:
                native_upload = _write_live_source_blob_bytes(
                    workspace=workspace,
                    blob_path=str(native_dest),
                    data=native_bytes,
                    overwrite=request.overwrite,
                    content_type="application/octet-stream",
                )

                text_upload = _write_live_source_blob_bytes(
                    workspace=workspace,
                    blob_path=str(text_dest),
                    data=text_bytes,
                    overwrite=request.overwrite,
                    content_type="text/plain; charset=utf-8",
                )

                summary_extract_result = None

                if workspace == "summaries":
                    try:
                        summary_extract_result = _create_live_summary_extract_from_text(
                            workspace=workspace,
                            doc_id=doc_id,
                            native_dest=str(native_dest),
                            text_dest=str(text_dest),
                            native_source=str(native_source),
                            text_bytes=text_bytes,
                            overwrite=True,
                        )
                    except Exception as summary_extract_exc:
                        summary_extract_result = {
                            "summary_extract_created": False,
                            "summary_extract_error": str(summary_extract_exc),
                        }

                promoted.append(
                    {
                        "doc_id": doc_id,
                        "status": "promoted",
                        "native": native_upload,
                        "text": text_upload,
                        "summary_extract": summary_extract_result,
                    }
                )

            except Exception as exc:
                skipped.append(
                    {
                        "doc_id": doc_id,
                        "status": "promotion_failed",
                        "native_destination": native_dest,
                        "text_destination": text_dest,
                        "error": str(exc),
                    }
                )
                continue

        post_promote_staged = _build_staged_results_payload(
            workspace=workspace,
            client=request.client,
            project=request.project,
            job_id=request.job_id,
        )

        return {
            "workspace": workspace,
            "client": request.client,
            "project": request.project,
            "job_id": request.job_id,
            "promote_all": request.promote_all,
            "requested_doc_ids": request.doc_ids,
            "promoted_count": len(promoted),
            "skipped_count": len(skipped),
            "promoted": promoted,
            "skipped": skipped,
            "ready_to_promote_count": post_promote_staged.get(
                "ready_to_promote_count",
                0,
            ),
            "promoted_total_count": post_promote_staged.get(
                "promoted_count",
                0,
            ),
            "promotion_status": post_promote_staged.get(
                "promotion_status",
                "",
            ),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post(
    "/{workspace}/processing-center/"
    "promotion/promote-review"
)
def promote_processing_center_review_population(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    request: PromoteReviewPopulationRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Promote selected project-wide Review HIT documents.

    The Promotion Center is cumulative across multiple APC
    Initial Ingestion / Detection jobs, while the underlying
    staged promotion engine operates one source APC job at a time.

    This endpoint bridges those two models:

      selected Doc IDs
          -> validate current project-wide Promotion state
          -> resolve source APC job per Doc ID
          -> group by source APC job
          -> promote each group
          -> return one consolidated response

    Spreadsheet / worksheet-derived HITs are explicitly refused
    here because their destination is Cyber², not Review.
    """

    requested_doc_ids = {
        str(doc_id or "").strip()
        for doc_id in (
            request.doc_ids
            or []
        )
        if str(doc_id or "").strip()
    }

    if not requested_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Select at least one Review HIT "
                "document for promotion."
            ),
        )

    #
    # Rebuild the authoritative current Promotion population.
    #
    current_population = (
        get_processing_center_promotion_population(
            workspace=workspace,
            client=request.client,
            project=request.project,
        )
    )

    review_hits = (
        current_population.get(
            "review_hits"
        )
        or []
    )

    if not isinstance(
        review_hits,
        list,
    ):
        review_hits = []

    review_by_doc_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for row in review_hits:
        if not isinstance(
            row,
            dict,
        ):
            continue

        doc_id = str(
            row.get(
                "doc_id"
            )
            or ""
        ).strip()

        if not doc_id:
            continue

        review_by_doc_id[
            doc_id
        ] = row

    #
    # Only documents currently classified HIT and routed to
    # Review are eligible for this endpoint.
    #
    eligible_doc_ids = {
        doc_id
        for doc_id in requested_doc_ids
        if doc_id in review_by_doc_id
    }

    rejected_doc_ids = sorted(
        requested_doc_ids
        - eligible_doc_ids
    )

    if not eligible_doc_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "None of the selected documents are "
                    "currently eligible for Review promotion."
                ),
                "requested_doc_ids": sorted(
                    requested_doc_ids
                ),
                "rejected_doc_ids": (
                    rejected_doc_ids
                ),
            },
        )

    #
    # Group eligible docs by their originating APC source job.
    #
    doc_ids_by_source_job: dict[
        str,
        list[str],
    ] = {}

    missing_source_job_ids: list[
        str
    ] = []

    for doc_id in sorted(
        eligible_doc_ids
    ):
        row = (
            review_by_doc_id.get(
                doc_id
            )
            or {}
        )

        source_job_id = str(
            row.get(
                "source_job_id"
            )
            or ""
        ).strip()

        if not source_job_id:
            missing_source_job_ids.append(
                doc_id
            )
            continue

        doc_ids_by_source_job.setdefault(
            source_job_id,
            [],
        ).append(
            doc_id
        )

    if (
        not doc_ids_by_source_job
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Selected Review documents could not "
                    "be resolved to their source APC jobs."
                ),
                "missing_source_job_doc_ids": (
                    missing_source_job_ids
                ),
            },
        )

    promoted: list[
        dict[str, Any]
    ] = []

    skipped: list[
        dict[str, Any]
    ] = []

    source_job_results: list[
        dict[str, Any]
    ] = []

    source_job_errors: list[
        dict[str, Any]
    ] = []

    #
    # Reuse the existing per-source-job promotion engine.
    #
    for (
        source_job_id,
        source_doc_ids,
    ) in sorted(
        doc_ids_by_source_job.items()
    ):
        try:
            job_result = (
                promote_processing_center_staged_results(
                    workspace=workspace,
                    request=(
                        PromoteStagedResultsRequest(
                            client=request.client,
                            project=request.project,
                            job_id=source_job_id,
                            doc_ids=(
                                source_doc_ids
                            ),
                            promote_all=False,
                            overwrite=(
                                request.overwrite
                            ),
                        )
                    ),
                )
            )

            source_job_results.append(
                {
                    "source_job_id": (
                        source_job_id
                    ),
                    "requested_doc_ids": (
                        source_doc_ids
                    ),
                    "promoted_count": (
                        job_result.get(
                            "promoted_count",
                            0,
                        )
                    ),
                    "skipped_count": (
                        job_result.get(
                            "skipped_count",
                            0,
                        )
                    ),
                    "promotion_status": (
                        job_result.get(
                            "promotion_status",
                            "",
                        )
                    ),
                }
            )

            for item in (
                job_result.get(
                    "promoted"
                )
                or []
            ):
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                promoted.append(
                    {
                        **item,
                        "source_job_id": (
                            source_job_id
                        ),
                    }
                )

            for item in (
                job_result.get(
                    "skipped"
                )
                or []
            ):
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                skipped.append(
                    {
                        **item,
                        "source_job_id": (
                            source_job_id
                        ),
                    }
                )

        except HTTPException as exc:
            source_job_errors.append(
                {
                    "source_job_id": (
                        source_job_id
                    ),
                    "doc_ids": (
                        source_doc_ids
                    ),
                    "status_code": (
                        exc.status_code
                    ),
                    "detail": (
                        exc.detail
                    ),
                }
            )

        except Exception as exc:
            source_job_errors.append(
                {
                    "source_job_id": (
                        source_job_id
                    ),
                    "doc_ids": (
                        source_doc_ids
                    ),
                    "error_type": (
                        type(exc).__name__
                    ),
                    "error": str(
                        exc
                    ),
                }
            )

    #
    # Refresh project-wide Promotion state after all writes.
    #
    refreshed_population = (
        get_processing_center_promotion_population(
            workspace=workspace,
            client=request.client,
            project=request.project,
        )
    )

    requested_by = (
        getattr(
            admin,
            "username",
            None,
        )
        or getattr(
            admin,
            "email",
            None,
        )
        or "INSYT Admin"
    )

    promoted_doc_ids = sorted(
        {
            str(
                item.get(
                    "doc_id"
                )
                or ""
            ).strip()
            for item in promoted
            if str(
                item.get(
                    "doc_id"
                )
                or ""
            ).strip()
        }
    )

    skipped_doc_ids = sorted(
        {
            str(
                item.get(
                    "doc_id"
                )
                or ""
            ).strip()
            for item in skipped
            if str(
                item.get(
                    "doc_id"
                )
                or ""
            ).strip()
        }
    )

    return {
        "workspace": workspace,
        "client": request.client,
        "project": request.project,

        "destination": "review",

        "requested_by": (
            requested_by
        ),

        "requested_at": (
            _utc_now()
        ),

        "overwrite": (
            request.overwrite
        ),

        "requested_doc_ids": sorted(
            requested_doc_ids
        ),

        "eligible_doc_ids": sorted(
            eligible_doc_ids
        ),

        "rejected_doc_ids": (
            rejected_doc_ids
        ),

        "missing_source_job_doc_ids": (
            missing_source_job_ids
        ),

        "source_job_count": len(
            doc_ids_by_source_job
        ),

        "source_job_ids": sorted(
            doc_ids_by_source_job.keys()
        ),

        "promoted_count": len(
            promoted_doc_ids
        ),

        "promoted_doc_ids": (
            promoted_doc_ids
        ),

        "promoted": (
            promoted
        ),

        "skipped_count": len(
            skipped_doc_ids
        ),

        "skipped_doc_ids": (
            skipped_doc_ids
        ),

        "skipped": (
            skipped
        ),

        "source_job_error_count": len(
            source_job_errors
        ),

        "source_job_errors": (
            source_job_errors
        ),

        "source_job_results": (
            source_job_results
        ),

        "promotion_population_counts": (
            refreshed_population.get(
                "counts"
            )
            or {}
        ),

        "status": (
            "completed"
            if not source_job_errors
            else "completed_with_errors"
        ),

        "message": (
            f"{len(promoted_doc_ids)} "
            "document(s) promoted to Review."
        ),
    }

@router.post(
    "/{workspace}/processing-center/"
    "promotion/send-cyber2"
)
def send_processing_center_cyber2_population(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    request: SendCyber2PopulationRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:

    requested_doc_ids = {
        str(doc_id or "").strip()
        for doc_id in (
            request.doc_ids
            or []
        )
        if str(doc_id or "").strip()
    }

    if not requested_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Select at least one "
                "Spreadsheet / CSV HIT."
            ),
        )

    current_population = (
        get_processing_center_promotion_population(
            workspace=workspace,
            client=request.client,
            project=request.project,
        )
    )

    spreadsheet_hits = (
        current_population.get(
            "spreadsheet_hits"
        )
        or []
    )

    spreadsheet_by_doc_id = {
        str(row.get("doc_id") or "").strip(): row
        for row in spreadsheet_hits
        if isinstance(row, dict)
        and str(
            row.get("doc_id")
            or ""
        ).strip()
    }

    eligible_doc_ids = {
        doc_id
        for doc_id in requested_doc_ids
        if doc_id in spreadsheet_by_doc_id
    }

    rejected_doc_ids = sorted(
        requested_doc_ids
        - eligible_doc_ids
    )

    if not eligible_doc_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "None of the selected documents "
                    "are currently eligible for Cyber²."
                ),
                "requested_doc_ids": sorted(
                    requested_doc_ids
                ),
                "rejected_doc_ids": (
                    rejected_doc_ids
                ),
            },
        )

    requested_by = (
        getattr(
            admin,
            "username",
            None,
        )
        or getattr(
            admin,
            "email",
            None,
        )
        or "INSYT Admin"
    )

    sent_at = _utc_now()

    sent: list[
        dict[str, Any]
    ] = []

    skipped: list[
        dict[str, Any]
    ] = []

    for doc_id in sorted(
        eligible_doc_ids
    ):
        row = (
            spreadsheet_by_doc_id[
                doc_id
            ]
        )

        if bool(
            row.get(
                "cyber2_sent"
            )
        ):
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": (
                        "already_sent_to_cyber2"
                    ),
                    "intake_index_path": (
                        row.get(
                            "cyber2_intake_index_path"
                        )
                    ),
                }
            )
            continue

        source_csv_path = str(
            row.get(
                "native_staged_blob_path"
            )
            or ""
        ).strip()

        if not source_csv_path:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": (
                        "missing_source_csv_path"
                    ),
                }
            )
            continue

        intake_index_path = (
            _cyber2_intake_document_path(
                workspace=workspace,
                client=request.client,
                project=request.project,
                doc_id=doc_id,
            )
        )

        payload = {
            "schema_version": 1,

            "workspace": workspace,
            "client": request.client,
            "project": request.project,

            "doc_id": doc_id,
            "file_id": row.get(
                "file_id"
            ),

            "status": "ready",
            "destination": "cyber2",

            "source_job_id": row.get(
                "source_job_id"
            ),

            "detection_job_id": row.get(
                "detection_job_id"
            ),

            "detection_run_id": row.get(
                "detection_run_id"
            ),

            "classification": row.get(
                "classification"
            ),

            "source_type": row.get(
                "source_type"
            ),

            "source_csv_path": (
                source_csv_path
            ),

            "original_filename": row.get(
                "original_filename"
            ),

            "original_workbook_file_id": (
                row.get(
                    "original_workbook_file_id"
                )
            ),

            "original_workbook_name": (
                row.get(
                    "original_workbook_name"
                )
            ),

            "sheet_name": row.get(
                "sheet_name"
            ),

            "sheet_index": row.get(
                "sheet_index"
            ),

            "sheet_visibility": row.get(
                "sheet_visibility"
            ),

            "entity_types": (
                row.get(
                    "entity_types"
                )
                or []
            ),

            "profiled_entity_count": (
                row.get(
                    "profiled_entity_count"
                )
            ),

            "detection_mode": row.get(
                "detection_mode"
            ),

            "type_profile_complete": (
                row.get(
                    "type_profile_complete"
                )
            ),

            "entity_counts_complete": (
                row.get(
                    "entity_counts_complete"
                )
            ),

            "intake_index_path": (
                intake_index_path
            ),

            "sent_to_cyber2_at": (
                sent_at
            ),

            "sent_to_cyber2_by": (
                requested_by
            ),
        }

        try:
            _write_processing_json_blob(
                blob_path=(
                    intake_index_path
                ),
                payload=payload,
                overwrite=True,
            )

            sent.append(
                {
                    "doc_id": doc_id,
                    "status": (
                        "sent_to_cyber2"
                    ),
                    "source_csv_path": (
                        source_csv_path
                    ),
                    "intake_index_path": (
                        intake_index_path
                    ),
                }
            )

        except Exception as exc:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": (
                        "cyber2_intake_"
                        "registration_failed"
                    ),
                    "error": str(exc),
                }
            )

    return {
        "workspace": workspace,
        "client": request.client,
        "project": request.project,

        "destination": "cyber2",

        "requested_doc_ids": sorted(
            requested_doc_ids
        ),

        "eligible_doc_ids": sorted(
            eligible_doc_ids
        ),

        "rejected_doc_ids": (
            rejected_doc_ids
        ),

        "sent_count": len(
            sent
        ),

        "sent": sent,

        "skipped_count": len(
            skipped
        ),

        "skipped": skipped,

        "requested_by": (
            requested_by
        ),

        "requested_at": (
            sent_at
        ),

        "status": "completed",
    }

@router.get(
    "/{workspace}/cyber2/intake"
)
def get_cyber2_intake(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    base_path = (
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    prefix = (
        f"{base_path}/cyber2/"
        f"intake/documents/"
    )

    container_client = (
        _processing_container_client()
    )

    documents: list[
        dict[str, Any]
    ] = []

    for blob in (
        container_client.list_blobs(
            name_starts_with=prefix
        )
    ):
        blob_path = str(
            blob.name
            or ""
        )

        if not blob_path.endswith(
            ".json"
        ):
            continue

        try:
            payload = (
                _read_processing_json_blob(
                    blob_path
                )
            )
        except Exception:
            continue

        if not isinstance(
            payload,
            dict,
        ):
            continue

        documents.append(
            {
                **payload,
                "last_modified": (
                    blob.last_modified.isoformat()
                    if getattr(
                        blob,
                        "last_modified",
                        None,
                    )
                    else None
                ),
            }
        )

    documents.sort(
        key=lambda row: (
            str(
                row.get(
                    "original_workbook_name"
                )
                or ""
            ),
            int(
                row.get(
                    "sheet_index"
                )
                or 0
            ),
            str(
                row.get(
                    "doc_id"
                )
                or ""
            ),
        )
    )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "intake_count": len(
            documents
        ),
        "documents": documents,
        "source_storage_account": (
            _review_account()
        ),
        "source_container": (
            _review_container(
                workspace
            )
        ),
        "source_mode": (
            "reference_existing_staged_csv"
        ),
    }

@router.get("/{workspace}/processing-center/jobs/{job_id}/report")
def get_processing_job_report(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str | None = Query(default=None),
    project: str | None = Query(default=None),
) -> dict[str, Any]:
    review_container = _review_container(workspace)

    # New worker-generated report location:
    # {client}/{workspace}/{project_storage_key}/processing_center/reports/{job_id}/{job_id}.summary.json
    if client and project:
        report_prefix = (
            f"{_project_base_path(workspace=workspace, client=client, project=project)}/"
            f"processing_center/reports/{job_id}"
        )

        summary_blob_path = f"{report_prefix}/{job_id}.summary.json"
        summary = _read_review_json_blob(
            container_name=review_container,
            blob_path=summary_blob_path,
        )

        if summary is not None:
            cost_events_blob_path = f"{report_prefix}/{job_id}.cost_events_by_meter.csv"
            stages_blob_path = f"{report_prefix}/{job_id}.stages.csv"
            files_blob_path = f"{report_prefix}/{job_id}.files.csv"
            containers_blob_path = f"{report_prefix}/{job_id}.containers.csv"
            review_promotion_blob_path = f"{report_prefix}/{job_id}.review_promotion.csv"
            review_manifest_blob_path = f"{report_prefix}/review_ready_manifest.csv"

            return {
                "job_id": job_id,
                "workspace": workspace,
                "client": client,
                "project": project,
                "report_source": "azure_worker_report_blob",
                "storage_account": os.getenv(
                    "INSYT_REVIEW_STORAGE_ACCOUNT",
                    "insytreviewstorage",
                ),
                "container": review_container,
                "summary_blob_path": summary_blob_path,
                "report": summary,
                "summary": summary,
                "uploaded_report_paths": {
                    "summary_json": summary_blob_path,
                    "cost_events_by_meter_csv": cost_events_blob_path,
                    "stages_csv": stages_blob_path,
                    "files_csv": files_blob_path,
                    "containers_csv": containers_blob_path,
                    "review_promotion_csv": review_promotion_blob_path,
                    "review_ready_manifest_csv": review_manifest_blob_path,
                },
                "cost_events_by_meter_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=cost_events_blob_path,
                ),
                "stages_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=stages_blob_path,
                ),
                "files_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=files_blob_path,
                ),
                "containers_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=containers_blob_path,
                ),
                "review_promotion_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=review_promotion_blob_path,
                ),
                "review_ready_manifest_csv": _read_review_text_blob(
                    container_name=review_container,
                    blob_path=review_manifest_blob_path,
                ),
            }

    # Legacy/local fallback for older API-side jobs.
    db = LedgerDB(_db_path())

    try:
        db.init_schema()
        return job_report_data(db, job_id)
    except ValueError as exc:
        detail = (
            f"job not found: {job_id}. "
            "For worker-generated APC reports, pass client and project query "
            "parameters so the API can read the Azure report blob."
        )
        raise HTTPException(status_code=404, detail=detail) from exc
    finally:
        db.close()