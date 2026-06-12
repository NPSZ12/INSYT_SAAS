from __future__ import annotations

import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .azure_blob_adapter import (
    azure_download_uploads,
    azure_upload_report_files,
    azure_upload_review_outputs,
    upload_processing_job_status,
)
from .azure_layout import AzureRoutingConfig, build_azure_routing_summary
from .config import DEFAULT_SETTINGS
from .db import LedgerDB
from .orchestrator import run_local_pipeline
from .reports import export_job_report, job_report_data
from .util import utc_now


@dataclass
class AzureRunResult:
    job_id: str | None
    status: str
    message: str
    routing: dict[str, Any]
    staging_dir: str
    local_review_root: str | None
    downloads: list[dict[str, Any]]
    report_files: dict[str, str]
    review_upload: dict[str, Any] | None
    report_upload: dict[str, Any] | None
    status_upload: dict[str, Any] | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_label(value: str) -> str:
    return str(value or "job").replace("/", "_").replace("\\", "_").replace(" ", "_")


def build_job_status_payload(
    *,
    routing: AzureRoutingConfig,
    job_id: str | None,
    status: str,
    message: str,
    matter_id: str,
    client_id: str,
    project_id: str,
    report: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "job_id": job_id,
        "status": status,
        "message": message,
        "matter_id": matter_id,
        "client_id": client_id,
        "project_id": project_id,
        "workspace": routing.workspace,
        "routing": build_azure_routing_summary(routing, job_id=job_id, promotion_count=0),
        "warnings": warnings or [],
        "report": report,
    }


def run_azure_processing_job(
    *,
    db: LedgerDB,
    routing: AzureRoutingConfig,
    matter_id: str,
    doc_prefix: str = "INSYT",
    enable_ocr_dry_run: bool = True,
    enable_live_ocr: bool = False,
    azure_write: bool = False,
    overwrite: bool = False,
    staging_root: str = ".apc_azure_runs",
    output_root: str = ".apc_azure_review_output",
    export_dir: str | None = "reports",
    clean_staging: bool = False,
    upload_status: bool = True,
) -> AzureRunResult:
    """Run the proven v0.8 Azure intake -> processing -> review promotion flow.

    This function is intentionally synchronous. API deployments can call it from a
    queue/worker later, but the code path remains deterministic and easy to test.
    """

    warnings = routing.validate()
    run_label = _safe_label(matter_id)
    staging_dir = Path(staging_root) / run_label / "uploads"
    review_root = Path(output_root)
    job_id: str | None = None
    status_upload: dict[str, Any] | None = None

    try:
        downloads = azure_download_uploads(
            routing,
            str(staging_dir),
            overwrite=True,
            export_dir=export_dir,
        )
        real_downloads = [r for r in downloads if r.get("status") in {"downloaded", "skipped_exists"}]
        if not real_downloads:
            result = AzureRunResult(
                job_id=None,
                status="no_uploads",
                message="No processing uploads were found. Nothing to process.",
                routing=build_azure_routing_summary(routing, job_id=None, promotion_count=0),
                staging_dir=str(staging_dir),
                local_review_root=None,
                downloads=downloads,
                report_files={},
                review_upload=None,
                report_upload=None,
                status_upload=None,
                warnings=warnings,
            )
            return result

        job_id = run_local_pipeline(
            db=db,
            settings=DEFAULT_SETTINGS,
            input_dir=str(staging_dir),
            matter_id=matter_id,
            client_id=routing.client,
            doc_prefix=doc_prefix,
            enable_ocr_dry_run=enable_ocr_dry_run,
            enable_live_ocr=enable_live_ocr,
            promote_review_ready=True,
            output_root=str(review_root),
        )
        local_review_root = review_root / job_id

        report_files: dict[str, str] = {}
        if export_dir:
            report_files = export_job_report(db, job_id, export_dir)

        review_upload = None
        report_upload = None
        if azure_write:
            review_upload = azure_upload_review_outputs(
                db=db,
                routing=routing,
                job_id=job_id,
                local_review_root=str(local_review_root),
                azure_write=True,
                overwrite=overwrite,
                export_dir=export_dir,
            )
            report_upload = azure_upload_report_files(
                routing=routing,
                job_id=job_id,
                local_review_root=str(local_review_root),
                report_files=list(report_files.values()),
                azure_write=True,
                overwrite=True,
                export_dir=export_dir,
            )

        report = job_report_data(db, job_id)
        status_payload = build_job_status_payload(
            routing=routing,
            job_id=job_id,
            status="completed",
            message="Azure processing job completed.",
            matter_id=matter_id,
            client_id=routing.client,
            project_id=routing.project,
            report=report,
            warnings=warnings,
        )
        if upload_status and azure_write:
            status_upload = upload_processing_job_status(
                routing=routing,
                job_id=job_id,
                payload=status_payload,
                overwrite=True,
            )

        if clean_staging and azure_write:
            shutil.rmtree(Path(staging_root) / run_label, ignore_errors=True)
            shutil.rmtree(local_review_root, ignore_errors=True)

        return AzureRunResult(
            job_id=job_id,
            status="completed",
            message="Azure processing job completed.",
            routing=build_azure_routing_summary(routing, job_id=job_id, promotion_count=0),
            staging_dir=str(staging_dir),
            local_review_root=str(local_review_root),
            downloads=downloads,
            report_files=report_files,
            review_upload=review_upload,
            report_upload=report_upload,
            status_upload=status_upload,
            warnings=warnings,
        )
    except Exception as exc:
        # If a job was created before failure, persist a failure status when allowed.
        if job_id and upload_status and azure_write:
            try:
                status_upload = upload_processing_job_status(
                    routing=routing,
                    job_id=job_id,
                    payload=build_job_status_payload(
                        routing=routing,
                        job_id=job_id,
                        status="failed",
                        message=str(exc),
                        matter_id=matter_id,
                        client_id=routing.client,
                        project_id=routing.project,
                        report=None,
                        warnings=warnings,
                    ),
                    overwrite=True,
                )
            except Exception:
                status_upload = None
        raise
