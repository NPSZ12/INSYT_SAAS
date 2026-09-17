from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from .azure_blob_adapter import azure_list_uploads, read_processing_job_status
from .azure_job_runner import run_azure_processing_job
from .azure_layout import AzureRoutingConfig
from .db import LedgerDB
from .reports import job_report_data

try:  # pragma: no cover - optional API dependency
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel, Field
except Exception as exc:  # pragma: no cover
    raise RuntimeError("FastAPI dependencies are not installed. Run: pip install -e .[api,azure]") from exc


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
    processing_account: str | None = None
    review_account: str | None = None
    processing_container: str | None = None
    review_container: str | None = None
    allow_same_account: bool = False


class ApiSettings(BaseModel):
    db_path: str
    allow_azure_write: bool
    allow_live_ocr: bool
    processing_account: str
    review_account: str


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}


def _db_path() -> str:
    return os.getenv("APC_DB_PATH", "./apc.api.db")


def _routing(
    *,
    workspace: Literal["capture", "discovery", "summaries"],
    client: str,
    project: str,
    processing_account: str | None = None,
    review_account: str | None = None,
    processing_container: str | None = None,
    review_container: str | None = None,
    azure_write: bool = False,
    allow_same_account: bool = False,
) -> AzureRoutingConfig:
    return AzureRoutingConfig.from_args(
        workspace=workspace,
        client=client,
        project=project,
        processing_account=processing_account,
        review_account=review_account,
        processing_container=processing_container,
        review_container=review_container,
        azure_write=azure_write,
        allow_same_account=allow_same_account,
    )


app = FastAPI(
    title="INSYT Azure Processing Center API",
    version="1.0.0",
    description="Backend-ready API wrapper for Azure Processing Center v0.9. Live OCR remains blocked unless explicitly enabled.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "azure-processing-center", "version": "1.0.0"}


@app.get("/api/settings", response_model=ApiSettings)
def api_settings() -> ApiSettings:
    return ApiSettings(
        db_path=_db_path(),
        allow_azure_write=_bool_env("APC_API_ALLOW_AZURE_WRITE", False),
        allow_live_ocr=_bool_env("APC_API_ALLOW_LIVE_OCR", False),
        processing_account=os.getenv("INSYT_PROCESSING_STORAGE_ACCOUNT", "insytprodstorage"),
        review_account=os.getenv("INSYT_REVIEW_STORAGE_ACCOUNT", "insytreviewstorage"),
    )


@app.get("/api/{workspace}/processing-center/uploads")
def list_uploads(
    workspace: Literal["capture", "discovery", "summaries"],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:
    routing = _routing(workspace=workspace, client=client, project=project)
    try:
        uploads = azure_list_uploads(routing)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"workspace": workspace, "client": client, "project": project, "uploads": uploads}


@app.post("/api/{workspace}/processing-center/azure-run/start")
def start_azure_run(workspace: Literal["capture", "discovery", "summaries"], request: AzureRunStartRequest) -> dict[str, Any]:
    allow_write = _bool_env("APC_API_ALLOW_AZURE_WRITE", False)
    allow_live_ocr = _bool_env("APC_API_ALLOW_LIVE_OCR", False)
    if request.azure_write and not allow_write:
        raise HTTPException(status_code=403, detail="Azure writes are disabled for this API. Set APC_API_ALLOW_AZURE_WRITE=true to enable.")
    if request.enable_live_ocr and not allow_live_ocr:
        raise HTTPException(status_code=403, detail="Live OCR is disabled for this API. Set APC_API_ALLOW_LIVE_OCR=true to enable.")

    routing = _routing(
        workspace=workspace,
        client=request.client,
        project=request.project,
        processing_account=request.processing_account,
        review_account=request.review_account,
        processing_container=request.processing_container,
        review_container=request.review_container,
        azure_write=request.azure_write,
        allow_same_account=request.allow_same_account,
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


@app.get("/api/{workspace}/processing-center/jobs/{job_id}")
def get_job_status(
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
        row = db.query_one("SELECT * FROM processing_job WHERE job_id=?", (job_id,))
        if not row:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return dict(row)
    finally:
        db.close()


@app.get("/api/{workspace}/processing-center/jobs/{job_id}/report")
def get_job_report(
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
