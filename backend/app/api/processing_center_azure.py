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

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

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


class AzureRunResponse(BaseModel):
    job_id: str
    status: str
    message: str | None = None
    routing: dict[str, Any] | None = None
    downloads: list[dict[str, Any]] = []
    review_upload: dict[str, Any] | None = None
    report_upload: dict[str, Any] | None = None
    status_upload: dict[str, Any] | None = None
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


@router.post(
    "/{workspace}/processing-center/azure-run/start",
    response_model=AzureRunResponse,
)
def start_azure_processing(
    workspace: Literal["capture", "discovery", "summaries"],
    request: AzureRunStartRequest,
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

        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        db.close()


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