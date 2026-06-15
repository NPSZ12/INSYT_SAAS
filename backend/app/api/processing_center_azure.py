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
    INSYT_PROCESSING_CONTAINER=insyt-capture

    INSYT_REVIEW_STORAGE_ACCOUNT=insytreviewstorage
    INSYT_REVIEW_CONTAINER=insyt-capture
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Any, Literal

import json
from datetime import datetime, timezone
from uuid import uuid4

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
    return os.getenv("INSYT_PROCESSING_CONTAINER", "insyt-capture")


def _review_account() -> str:
    return os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")


def _review_container() -> str:
    return os.getenv("INSYT_REVIEW_CONTAINER", "insyt-capture")

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _queue_name() -> str:
    return os.getenv("APC_PROCESSING_QUEUE_NAME", "apc-processing-jobs")


def _new_job_id() -> str:
    return f"JOB-{uuid4().hex[:16].upper()}"


def _job_base_path(
    *,
    workspace: str,
    client: str,
    project: str,
    job_id: str,
) -> str:
    return (
        f"{workspace}/{client}/{project}/"
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
        review_container=_review_container(),
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

    uploads_prefix = (
        f"{workspace}/{client}/{project}/"
        f"source/processing_center/uploads/"
    )

    archive_prefix = (
        f"{workspace}/{client}/{project}/"
        f"processing_center/archive/{job_id}/uploads/"
    )

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

    uploads_prefix = (
        f"{workspace}/{client}/{project}/"
        f"source/processing_center/uploads/"
    )

    removed_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    removed_prefix = (
        f"{workspace}/{client}/{project}/"
        f"processing_center/removed/{removed_at}/uploads/"
    )

    selected_names = set(str(name or "").strip() for name in blob_names if name)

    if clear_all:
        blobs = [
            blob
            for blob in container_client.list_blobs(name_starts_with=uploads_prefix)
            if not str(blob.name).endswith("/")
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
                props = container_client.get_blob_client(name).get_blob_properties()
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

        if source_name.endswith("/"):
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
                raise RuntimeError(f"Removal copy did not complete: {copy_status}")

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
        f"{workspace}/{client}/{project}/"
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
                review_container = os.getenv(
                    "INSYT_REVIEW_CONTAINER",
                    f"insyt-{workspace}",
                )

                summary_blob_path = (
                    f"{workspace}/{client}/{project}/"
                    f"processing_center/reports/"
                    f"{apc_job_id}/{apc_job_id}.summary.json"
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
        "review_container": _review_container(),
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
    routing = _routing(workspace=workspace, client=client, project=project)

    try:
        uploads = azure_list_uploads(routing)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "uploads": uploads,
    }


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
        f"{workspace}/{client}/{project_id}/"
        f"source/processing_center/uploads/{safe_filename}"
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
            tracked_status = _read_processing_json_blob(
                container_name=os.getenv("INSYT_PROCESSING_CONTAINER", f"insyt-{workspace}"),
                blob_path=status_blob_path,
            )

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

    review_container = os.getenv("INSYT_REVIEW_CONTAINER", f"insyt-{workspace}")

    summary_blob_path = (
        f"{workspace}/{client}/{project}/processing_center/reports/"
        f"{apc_job_id}/{apc_job_id}.summary.json"
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
    review_container = os.getenv("INSYT_REVIEW_CONTAINER", f"insyt-{workspace}")

    summary_blob_path = (
        f"{workspace}/{client}/{project}/processing_center/reports/"
        f"{job_id}/{job_id}.summary.json"
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
    review_container = os.getenv("INSYT_REVIEW_CONTAINER", f"insyt-{workspace}")
    review_account = os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage")

    staged_prefix = (
        f"{workspace}/{client}/{project}/processing_center/staged/{job_id}"
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

        final_native_blob_path = (
            f"{workspace}/{client}/{project}/source/native/{native_filename}"
        )
        final_text_blob_path = (
            f"{workspace}/{client}/{project}/source/text/{doc_id}.txt"
        )

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
                "native_staged_blob_path": native_path,
                "text_staged_blob_path": text_blob.get("name") if text_blob else None,
                "native_staged_bytes": native_blob.get("size") or 0,
                "text_staged_bytes": text_blob.get("size") if text_blob else 0,
                "final_native_blob_path": final_native_blob_path,
                "final_text_blob_path": final_text_blob_path,
                "ready_to_promote": bool(text_blob),
            }
        )

    docs.sort(key=lambda item: item.get("doc_id") or "")

    summary = report.get("job") or {}
    ocr = report.get("ocr") or {}
    cost = report.get("cost") or {}

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "job_id": job_id,
        "storage_account": review_account,
        "container": review_container,
        "staged_prefix": staged_prefix,
        "native_prefix": native_prefix,
        "text_prefix": text_prefix,
        "doc_count": len(docs),
        "ready_to_promote_count": sum(
            1 for item in docs if item.get("ready_to_promote")
        ),
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
                        "completed_at": job.get("completed_at") or job.get("last_modified"),
                        "doc_count": staged.get("doc_count", 0),
                        "ready_to_promote_count": staged.get("ready_to_promote_count", 0),
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

        review_container = os.getenv("INSYT_REVIEW_CONTAINER", f"insyt-{workspace}")

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

            native_dest_exists = _review_blob_exists(
                container_name=review_container,
                blob_path=str(native_dest),
            )

            text_dest_exists = _review_blob_exists(
                container_name=review_container,
                blob_path=str(text_dest),
            )

            if (native_dest_exists or text_dest_exists) and not request.overwrite:
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
                        "message": (
                            "Final source file already exists. "
                            "Set overwrite=true to replace it."
                        ),
                    }
                )
                continue

            try:
                native_upload = _write_review_blob_bytes(
                    container_name=review_container,
                    blob_path=str(native_dest),
                    data=native_bytes,
                    overwrite=request.overwrite,
                    content_type="application/octet-stream",
                )

                text_upload = _write_review_blob_bytes(
                    container_name=review_container,
                    blob_path=str(text_dest),
                    data=text_bytes,
                    overwrite=request.overwrite,
                    content_type="text/plain; charset=utf-8",
                )

                promoted.append(
                    {
                        "doc_id": doc_id,
                        "status": "promoted",
                        "native": native_upload,
                        "text": text_upload,
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
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc



@router.get("/{workspace}/processing-center/jobs/{job_id}/report")
def get_processing_job_report(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
    client: str | None = Query(default=None),
    project: str | None = Query(default=None),
) -> dict[str, Any]:
    review_container = os.getenv("INSYT_REVIEW_CONTAINER", f"insyt-{workspace}")

    # New worker-generated report location:
    # {workspace}/{client}/{project}/processing_center/reports/{job_id}/{job_id}.summary.json
    if client and project:
        report_prefix = (
            f"{workspace}/{client}/{project}/processing_center/reports/{job_id}"
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