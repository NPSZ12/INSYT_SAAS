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

            report = status.get("report") or {}
            report_job = report.get("job") or {}
            report_ocr = report.get("ocr") or {}
            report_cost = report.get("cost") or {}
            review_upload = status.get("review_upload") or {}
            report_upload = status.get("report_upload") or {}

            jobs.append(
                {
                    "job_id": job_id,
                    "status": status.get("status"),
                    "message": status.get("message"),
                    "matter_id": status.get("matter_id"),
                    "workspace": status.get("workspace") or workspace,
                    "client": status.get("client_id") or client,
                    "project": status.get("project_id") or project,
                    "generated_at": status.get("generated_at"),
                    "created_at": report_job.get("created_at"),
                    "completed_at": report_job.get("completed_at"),
                    "source_file_count": report_job.get("source_file_count"),
                    "expanded_file_count": report_job.get("expanded_file_count"),
                    "unique_doc_count": report_job.get("unique_doc_count"),
                    "duplicate_doc_count": report_job.get("duplicate_doc_count"),
                    "ocr_page_count": report_job.get("ocr_page_count"),
                    "ocr_candidate_files": report_ocr.get("candidate_files"),
                    "ocr_candidate_bytes": report_ocr.get("candidate_bytes"),
                    "ocr_candidate_gb": report_ocr.get("candidate_gb"),
                    "ocr_estimated_pages": report_ocr.get("estimated_pages"),
                    "ocr_estimated_cost_usd": report_ocr.get("estimated_cost_usd"),
                    "ocr_cost_pct_of_total": report_ocr.get("cost_pct_of_total"),
                    "ocr_reason_counts": report_ocr.get("reason_counts") or {},
                    "non_ocr_estimated_cost_usd": report_cost.get(
                        "non_ocr_estimated_cost_usd"
                    ),
                    "estimated_azure_cost_usd": report_job.get(
                        "estimated_azure_cost_usd"
                    ),
                    "downloaded_count": len(status.get("downloads") or []),
                    "native_text_upload_count": len(
                        review_upload.get("uploads") or []
                    ),
                    "report_upload_count": len(
                        report_upload.get("uploaded_reports") or []
                    ),
                    "warning_count": len(status.get("warnings") or []),
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


def _normalize_processing_history_job(job: dict[str, Any]) -> dict[str, Any]:
    """Flatten tracked APC worker status into the fields the UI expects.

    Cost fields ending in estimated_* remain estimates only. Actual Azure cost
    will be populated later from Azure Cost Management ingestion.
    """

    summary = (
        job.get("summary")
        or job.get("report")
        or job.get("job_report")
        or {}
    )

    job_summary = summary.get("job") or {}
    ocr_summary = summary.get("ocr") or {}
    cost_summary = summary.get("cost") or {}

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
        job.get("source_file_count"),
        job_summary.get("source_file_count"),
        summary.get("source_file_count"),
        len(downloads),
    )

    expanded_file_count = _get_nested_int(
        job.get("expanded_file_count"),
        job_summary.get("expanded_file_count"),
        summary.get("expanded_file_count"),
        source_file_count,
    )

    unique_doc_count = _get_nested_int(
        job.get("unique_doc_count"),
        job_summary.get("unique_doc_count"),
        summary.get("unique_doc_count"),
        review_upload.get("planned_docs"),
        hash_index_upload.get("added_count"),
        0,
    )

    duplicate_doc_count = _get_nested_int(
        job.get("duplicate_doc_count"),
        job_summary.get("duplicate_doc_count"),
        summary.get("duplicate_doc_count"),
        0,
    )

    ocr_page_count = _get_nested_int(
        job.get("ocr_page_count"),
        job_summary.get("ocr_page_count"),
        ocr_summary.get("pages"),
        ocr_summary.get("estimated_pages"),
        summary.get("ocr_page_count"),
        summary.get("ocr_estimated_pages"),
        0,
    )

    ocr_estimated_cost_usd = _get_nested_number(
        job.get("ocr_estimated_cost_usd"),
        ocr_summary.get("estimated_cost_usd"),
        summary.get("ocr_estimated_cost_usd"),
        summary.get("ocr_estimated_cost"),
        0,
    )

    estimated_azure_cost_usd = _get_nested_number(
        job.get("estimated_azure_cost_usd"),
        job_summary.get("estimated_azure_cost_usd"),
        cost_summary.get("total_estimated_azure_cost_usd"),
        summary.get("estimated_azure_cost_usd"),
        summary.get("total_estimated_azure_cost"),
        0,
    )

    normalized = {
        **job,
        "source_file_count": source_file_count,
        "expanded_file_count": expanded_file_count,
        "unique_doc_count": unique_doc_count,
        "duplicate_doc_count": duplicate_doc_count,
        "ocr_page_count": ocr_page_count,
        "ocr_estimated_cost_usd": ocr_estimated_cost_usd,
        "estimated_azure_cost_usd": estimated_azure_cost_usd,
        "downloaded_count": len(downloads),
        "native_text_upload_count": len(native_text_uploads),
        "report_upload_count": len(uploaded_reports),
        "warning_count": len(warnings),
        "hash_index_added_count": _safe_int(hash_index_upload.get("added_count")),
        "archive_upload_count": _safe_int(archive_upload.get("archived_count")),
        "report_file_count": len(report_files),
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
            _normalize_processing_history_job(job)
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

@router.get("/{workspace}/processing-center/jobs/{job_id}/report")
def get_processing_job_report(
    workspace: Literal["capture", "discovery", "summaries"],
    job_id: str,
) -> dict[str, Any]:
    db = LedgerDB(_db_path())

    try:
        db.init_schema()
        return job_report_data(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()