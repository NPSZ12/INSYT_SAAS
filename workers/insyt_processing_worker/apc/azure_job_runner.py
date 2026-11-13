from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .azure_blob_adapter import (
    azure_download_uploads,
    azure_read_processed_hash_index,
    azure_update_processed_hash_index,
    azure_upload_report_files,
    azure_upload_review_outputs,
    upload_processing_job_status,
    azure_upload_xl_files_outputs,
)

from app.services.document_lifecycle_writer import (
    bulk_upsert_document_lifecycle,
)

from .azure_layout import AzureRoutingConfig, build_azure_routing_summary
from .config import DEFAULT_SETTINGS
from .db import LedgerDB
from .orchestrator import run_local_pipeline
from .reports import export_job_report, job_report_data
from .util import utc_now


def validate_structured_csv_uploads(
    *,
    db: LedgerDB,
    job_id: str,
    upload_result: dict[str, Any],
) -> int:
    """
    Reconcile adapter-generated CSV documents with the existing
    common uploader. No new upload or processing path.
    """
    rows = db.query(
        """
        SELECT file_id, parent_file_id, extension,
               is_container, is_duplicate, is_denisted,
               doc_id, stage_status_json
        FROM file_processing_metrics
        WHERE job_id=?
        """,
        (job_id,),
    )

    parents = set()
    children_by_parent = {}
    eligible = {}

    for row in rows:
        status = json.loads(row["stage_status_json"] or "{}")
        parent_metadata = status.get("structured_json_parent")
        child_metadata = status.get("structured_json_child")

        file_id = str(row["file_id"] or "")
        parent_id = str(row["parent_file_id"] or "")
        extension = str(row["extension"] or "").lower().lstrip(".")

        if (
            isinstance(parent_metadata, dict)
            and parent_metadata.get("source_filename")
            and bool(row["is_container"])
        ):
            parents.add(file_id)

        if not isinstance(child_metadata, dict):
            continue

        if (
            extension != "csv"
            or not parent_id
            or str(child_metadata.get("parent_file_id") or "")
            != parent_id
        ):
            raise RuntimeError(
                "Structured CSV lineage invalid: "
                f"file_id={file_id}"
            )

        children_by_parent.setdefault(parent_id, set()).add(file_id)

        # Duplicate and DENIST suppression are existing
        # APC behaviors; suppressed files are not uploads.
        if bool(row["is_duplicate"]) or bool(row["is_denisted"]):
            continue

        if not row["doc_id"]:
            raise RuntimeError(
                "Structured CSV is missing Doc ID: "
                f"file_id={file_id}"
            )

        eligible[file_id] = str(row["doc_id"])

    for parent_id in parents:
        if not children_by_parent.get(parent_id):
            raise RuntimeError(
                "Structured source produced no registered CSV children: "
                f"parent_file_id={parent_id}"
            )

    uploaded_rows = upload_result.get("uploaded")
    if not isinstance(uploaded_rows, list):
        raise RuntimeError(
            "Common uploader returned no uploaded-file inventory."
        )

    uploaded = {}
    for row in uploaded_rows:
        if not isinstance(row, dict):
            raise RuntimeError(
                "Invalid common uploader file inventory."
            )
        file_id = str(row.get("file_id") or "")
        if file_id in eligible:
            if file_id in uploaded:
                raise RuntimeError(
                    "Structured CSV uploaded more than once: "
                    f"file_id={file_id}"
                )
            uploaded[file_id] = row

    if set(uploaded) != set(eligible):
        missing = sorted(set(eligible) - set(uploaded))
        raise RuntimeError(
            "Structured CSV upload reconciliation failed: "
            f"expected={len(eligible)}, "
            f"uploaded={len(uploaded)}, "
            f"missing_file_ids={missing}"
        )

    for file_id, doc_id in eligible.items():
        row = uploaded[file_id]
        if (
            str(row.get("doc_id") or "") != doc_id
            or row.get("status") != "uploaded"
            or not bool(row.get("is_csv_child"))
            or not bool(row.get("detection_ready"))
            or not str(row.get("text_staged_blob_path") or "")
        ):
            raise RuntimeError(
                "Structured CSV not detection-ready after upload: "
                f"file_id={file_id}"
            )

    return len(eligible)


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
    xl_files_upload: dict[str, Any] | None
    report_upload: dict[str, Any] | None
    status_upload: dict[str, Any] | None
    hash_index_upload: dict[str, Any] | None
    warnings: list[Any]

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
    warnings: list[Any] | None = None,
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
    processing_set_size: int = 500,
    overwrite: bool = False,
    staging_root: str = ".apc_azure_runs",
    output_root: str = ".apc_azure_review_output",
    export_dir: str | None = "reports",
    clean_staging: bool = False,
    upload_status: bool = True,
    progress_callback=None,
    cancellation_callback=None,
    after_ocr_preflight_callback=None,
    ocr_dispatch_callback=None,
    selected_uploads: list[str] | None = None,
    tracked_job_id: str | None = None,
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
        if cancellation_callback:
            cancellation_callback(
                "azure_download_start"
            )

        # Important: each Azure run must start from only the blobs currently
        # pending in source/processing_center/uploads. Without clearing this
        # local folder, stale files from prior runs can be processed again even
        # after Azure uploads were archived or removed.
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        downloads = azure_download_uploads(
            routing,
            str(staging_dir),
            overwrite=True,
            export_dir=export_dir,
            blob_names=selected_uploads,
        )

        if cancellation_callback:
            cancellation_callback(
                "azure_download_complete"
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
                hash_index_upload=None,
                warnings=warnings,
            )
            return result
        
        prior_processed_index = azure_read_processed_hash_index(routing)

        job_id = run_local_pipeline(
            db=db,
            settings=DEFAULT_SETTINGS,
            input_dir=str(staging_dir),
            matter_id=matter_id,
            client_id=routing.client,
            workspace=routing.workspace,
            doc_prefix=doc_prefix,
            enable_ocr_dry_run=enable_ocr_dry_run,
            enable_live_ocr=enable_live_ocr,
            processing_set_size=processing_set_size,
            promote_review_ready=True,
            output_root=str(review_root),
            prior_processed_index=prior_processed_index,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
            after_ocr_preflight_callback=after_ocr_preflight_callback,
            ocr_dispatch_callback=ocr_dispatch_callback,
            job_id=tracked_job_id,
        )
        local_review_root = review_root / job_id

        if cancellation_callback:
            cancellation_callback(
                "post_processing"
            )

        if cancellation_callback:
            cancellation_callback(
                "report_generation"
            )

        report_files: dict[str, str] = {}

        if export_dir:
            report_files = export_job_report(
                db,
                job_id,
                export_dir,
            )

        review_upload = None
        report_upload = None
        hash_index_upload = None
        xl_files_upload = None

        if cancellation_callback:
            cancellation_callback(
                "azure_review_upload"
            )

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

            xl_files_upload = (
                azure_upload_xl_files_outputs(
                    db=db,
                    routing=routing,
                    job_id=job_id,
                    azure_write=True,
                    overwrite=overwrite,
                )
            )

            # ONE hardened CSV staging/upload path.
            # JSON and workbook CSV children are both
            # included by azure_upload_xl_files_outputs.
            planned = int(
                xl_files_upload.get("planned_count", 0) or 0
            )
            uploaded = int(
                xl_files_upload.get("uploaded_count", 0) or 0
            )
            failed = int(
                xl_files_upload.get("failed_count", 0) or 0
            )

            if failed or uploaded != planned:
                raise RuntimeError(
                    "Common CSV Azure staging incomplete: "
                    f"planned={planned}, "
                    f"uploaded={uploaded}, "
                    f"failed={failed}"
                )

            validate_structured_csv_uploads(
                db=db,
                job_id=job_id,
                upload_result=xl_files_upload,
            )

            staging_payloads = [
                payload
                for payload in (
                    review_upload,
                    xl_files_upload,
                )
                if isinstance(
                    payload,
                    dict,
                )
            ]

            try:
                lifecycle_result = (
                    bulk_upsert_document_lifecycle(
                        ledger_db=db,
                        workspace=routing.workspace,
                        client=routing.client,
                        project=routing.project,
                        source_job_id=job_id,
                        tracked_job_id=tracked_job_id,
                        staging_payloads=staging_payloads,
                    )
                )

                if (
                    lifecycle_result.get(
                        "enabled"
                    )
                ):
                    warnings.append(
                        {
                            "type":
                                "document_lifecycle_index",

                            "message":
                                "Document lifecycle index updated.",

                            "status":
                                lifecycle_result.get(
                                    "status",
                                    "",
                                ),

                            "row_count":
                                lifecycle_result.get(
                                    "row_count",
                                    0,
                                ),

                            "written_count":
                                lifecycle_result.get(
                                    "written_count",
                                    0,
                                ),

                            "chunk_size":
                                lifecycle_result.get(
                                    "chunk_size",
                                    0,
                                ),
                        }
                    )

            except Exception as lifecycle_exc:
                warnings.append(
                    {
                        "type":
                            "document_lifecycle_index_error",

                        "message":
                            (
                                "Document lifecycle indexing failed "
                                "after staging completed. "
                                "The APC job will remain successful "
                                "and can be reconciled separately."
                            ),

                        "job_id":
                            job_id,

                        "error":
                            repr(
                                lifecycle_exc
                            ),

                        "reconciliation_required":
                            True,
                    }
                )

            hash_index_upload = azure_update_processed_hash_index(
                db=db,
                routing=routing,
                job_id=job_id,
                overwrite=True,
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
            xl_files_upload=xl_files_upload,
            report_upload=report_upload,
            status_upload=status_upload,
            hash_index_upload=hash_index_upload,
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
