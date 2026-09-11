from __future__ import annotations

from .azure_layout import AzureRoutingConfig
from .config import Settings
from .db import LedgerDB
from .stages.container_expansion import run_container_expansion
from .stages.dedupe import run_dedupe
from .stages.denist import load_denist_hashes, run_denist
from .stages.doc_id import run_doc_id_assignment
from .stages.families import run_family_detection
from .stages.hashing import run_hashing
from .stages.inventory import run_inventory
from .stages.ocr_dry_run import run_ocr_dry_run
from .stages.ocr_live_placeholder import run_live_ocr_placeholder
from .stages.ocr_preflight import run_ocr_preflight
from .stages.prior_processed import run_prior_processed_duplicate_suppression
from .stages.review_promotion import run_review_promotion
from .stages.text_extraction import run_text_extraction
from .processing_sets import build_processing_sets
from .util import bytes_to_gb, json_dumps, new_id, utc_now


def create_job(db: LedgerDB, matter_id: str, client_id: str, metadata: dict | None = None) -> str:
    job_id = new_id("JOB")
    db.execute(
        """
        INSERT INTO processing_job (job_id, matter_id, client_id, created_at, status, metadata_json)
        VALUES (?,?,?,?,?,?)
        """,
        (job_id, matter_id, client_id, utc_now(), "created", json_dumps(metadata or {})),
    )
    return job_id


def finalize_job(db: LedgerDB, job_id: str) -> None:
    totals = db.query_one(
        """
        SELECT
          coalesce(sum(estimated_cost_usd),0) AS total_cost
        FROM cost_event WHERE job_id=?
        """,
        (job_id,),
    )
    counts = db.query_one(
        """
        SELECT
        coalesce(sum(CASE WHEN is_container=0 AND is_denisted=0 AND is_duplicate=0 THEN 1 ELSE 0 END),0) AS unique_docs,
        coalesce(sum(CASE WHEN is_container=0 AND is_duplicate=1 THEN 1 ELSE 0 END),0) AS duplicate_docs,
        coalesce(sum(CASE WHEN is_container=0 AND is_denisted=1 THEN 1 ELSE 0 END),0) AS denist_docs,
        coalesce(
            sum(
                CASE
                    WHEN is_container=0
                        AND coalesce(
                            CAST(
                                json_extract(
                                    stage_status_json,
                                    '$.ocr_live.page_count'
                                ) AS INTEGER
                            ),
                            0
                        ) > 0
                    THEN CAST(
                        json_extract(
                            stage_status_json,
                            '$.ocr_live.page_count'
                        ) AS INTEGER
                    )

                    WHEN is_container=0
                        AND requires_ocr=1
                    THEN page_count

                    ELSE 0
                END
            ),
            0
        ) AS ocr_pages,
        (SELECT coalesce(source_bytes,0) FROM processing_job WHERE job_id=?) AS source_bytes,
        (SELECT coalesce(source_file_count,0) FROM processing_job WHERE job_id=?) AS source_file_count
        FROM file_processing_metrics WHERE job_id=?
        """,
        (job_id, job_id, job_id),
    )
    exception_count = db.scalar(
        "SELECT coalesce(sum(exceptions),0) FROM processing_stage_run WHERE job_id=?",
        (job_id,),
    ) or 0
    total_cost = float(totals["total_cost"] if totals else 0)
    source_bytes = int(counts["source_bytes"] or 0)
    unique_docs = int(counts["unique_docs"] or 0)
    ocr_pages = int(counts["ocr_pages"] or 0)
    source_gb = bytes_to_gb(source_bytes) if source_bytes else 0
    cost_per_gb = total_cost / source_gb if source_gb > 0 else 0
    cost_per_unique_doc = total_cost / unique_docs if unique_docs > 0 else 0
    ocr_cost = db.scalar(
        """
        SELECT coalesce(sum(estimated_cost_usd),0) FROM cost_event
        WHERE job_id=? AND lower(azure_service) LIKE '%document%' AND lower(meter_name) LIKE '%read%'
        """,
        (job_id,),
    ) or 0
    cost_per_ocr_page = float(ocr_cost) / ocr_pages if ocr_pages > 0 else 0

    db.execute(
        """
        UPDATE processing_job
        SET completed_at=?, status=?, source_bytes=?, source_file_count=?, unique_doc_count=?,
            duplicate_doc_count=?, denist_suppressed_count=?, ocr_page_count=?, exception_count=?,
            estimated_azure_cost_usd=?, effective_cost_per_source_gb=?, effective_cost_per_unique_doc=?,
            effective_cost_per_ocr_page=?
        WHERE job_id=?
        """,
        (
            utc_now(),
            "completed" if exception_count == 0 else "completed_with_exceptions",
            source_bytes,
            int(counts["source_file_count"] or 0),
            unique_docs,
            int(counts["duplicate_docs"] or 0),
            int(counts["denist_docs"] or 0),
            ocr_pages,
            int(exception_count),
            total_cost,
            cost_per_gb,
            cost_per_unique_doc,
            cost_per_ocr_page,
            job_id,
        ),
    )

def _emit_pipeline_progress(
    progress_callback,
    *,
    db: LedgerDB,
    job_id: str,
    stage: str,
    current_step: str,
    stage_processed_files: int | None = None,
    stage_total_files: int | None = None,
    stage_failed_files: int | None = None,
    current_file: str | None = None,
) -> None:
    if not progress_callback:
        return

    job = db.query_one(
        """
        SELECT
            coalesce(source_file_count, 0) AS source_file_count,
            coalesce(expanded_file_count, 0) AS expanded_file_count,
            coalesce(unique_doc_count, 0) AS unique_doc_count,
            coalesce(duplicate_doc_count, 0) AS duplicate_doc_count,
            coalesce(denist_suppressed_count, 0) AS denist_suppressed_count,
            coalesce(ocr_page_count, 0) AS ocr_page_count,
            coalesce(exception_count, 0) AS exception_count
        FROM processing_job
        WHERE job_id=?
        """,
        (job_id,),
    )

    values = dict(job) if job else {}

    processed = (
        int(stage_processed_files)
        if stage_processed_files is not None
        else 0
    )

    total = (
        int(stage_total_files)
        if stage_total_files is not None
        else 0
    )

    failed = (
        int(stage_failed_files)
        if stage_failed_files is not None
        else 0
    )

    progress_callback(
        {
            "stage": stage,
            "current_stage": stage,
            "current_step": current_step,
            "current_file": current_file or "",
            "source_file_count": int(
                values.get("source_file_count") or 0
            ),
            "expanded_file_count": int(
                values.get("expanded_file_count") or 0
            ),
            "unique_doc_count": int(
                values.get("unique_doc_count") or 0
            ),
            "duplicate_doc_count": int(
                values.get("duplicate_doc_count") or 0
            ),
            "denist_suppressed_count": int(
                values.get("denist_suppressed_count") or 0
            ),
            "ocr_page_count": int(
                values.get("ocr_page_count") or 0
            ),
            "exception_count": int(
                values.get("exception_count") or 0
            ),
            "stage_processed_files": processed,
            "stage_total_files": total,
            "stage_failed_files": failed,
            "stage_remaining_files": max(
                total - processed,
                0,
            ),
        }
    )

def run_local_pipeline(
    db: LedgerDB,
    settings: Settings,
    input_dir: str,
    matter_id: str,
    client_id: str,
    workspace: str = "capture",
    doc_prefix: str = "INSYT",
    custodian_id: str | None = None,
    denist_hash_file: str | None = None,
    enable_ocr_dry_run: bool = False,
    enable_live_ocr: bool = False,
    promote_review_ready: bool = False,
    output_root: str | None = None,
    prior_processed_index: dict | None = None,
    progress_callback=None,
    cancellation_callback=None,
    processing_set_size: int = 500,
) -> str:
    def check_cancel(
        stage: str,
    ) -> None:
        if cancellation_callback:
            cancellation_callback(
                stage
            )

    db.init_schema()
    job_id = create_job(
        db,
        matter_id=matter_id,
        client_id=client_id,
        metadata={
            "input_dir": input_dir,
            "workspace": workspace,
            "client_id": client_id,
            "project": matter_id,
            "doc_prefix": doc_prefix,
            "custodian_id": custodian_id,
            "enable_ocr_dry_run": enable_ocr_dry_run,
            "enable_live_ocr": enable_live_ocr,
            "promote_review_ready": promote_review_ready,
            "output_root": output_root,
            "prior_processed_index_count": len(
                (prior_processed_index or {}).get("items", {})
                if isinstance(prior_processed_index, dict)
                else {}
            ),
        },
    )
    db.execute("UPDATE processing_job SET status=? WHERE job_id=?", ("running", job_id))

    if denist_hash_file:
        load_denist_hashes(
            db,
            denist_hash_file,
            source_name="user-provided",
        )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="inventory",
        current_step="Inventorying source uploads.",
    )

    check_cancel("inventory")
    run_inventory(
        db,
        settings,
        job_id,
        matter_id,
        input_dir=input_dir,
        custodian_id=custodian_id,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="container_expansion",
        current_step="Expanding archives and workbook containers.",
    )

    check_cancel("container_expansion")
    run_container_expansion(
        db,
        settings,
        job_id,
        matter_id,
        input_dir=input_dir,
    )

    expanded_total = int(
        db.scalar(
            """
            SELECT coalesce(expanded_file_count, 0)
            FROM processing_job
            WHERE job_id=?
            """,
            (job_id,),
        )
        or 0
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="hashing",
        current_step="Hashing expanded leaf files.",
        stage_total_files=expanded_total,
    )

    check_cancel("hashing")
    run_hashing(
        db,
        settings,
        job_id,
        matter_id,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="denist",
        current_step="Applying deNIST suppression.",
        stage_total_files=expanded_total,
    )

    check_cancel("denist")
    run_denist(
        db,
        settings,
        job_id,
        matter_id,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="dedupe",
        current_step="Checking duplicate documents.",
        stage_total_files=expanded_total,
    )

    check_cancel("dedupe")
    run_dedupe(
        db,
        settings,
        job_id,
        matter_id,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="prior_processed",
        current_step="Checking previously processed documents.",
    )

    check_cancel("prior_processed")
    run_prior_processed_duplicate_suppression(
        db,
        settings,
        job_id,
        matter_id,
        prior_processed_index=prior_processed_index,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="family_detection",
        current_step="Identifying document families.",
    )

    check_cancel("family_detection")
    run_family_detection(
        db,
        settings,
        job_id,
        matter_id,
    )

    check_cancel("processing_sets")
    processing_sets = build_processing_sets(
        db=db,
        job_id=job_id,
        matter_id=matter_id,
        set_size=processing_set_size,
    )

    db.execute(
        """
        UPDATE processing_job
        SET metadata_json=json_patch(
            coalesce(metadata_json, '{}'),
            ?
        )
        WHERE job_id=?
        """,
        (
            json_dumps(
                {
                    "processing_sets": {
                        "enabled": True,
                        "configured_set_size": (
                            processing_set_size
                        ),
                        "set_count": (
                            processing_sets["set_count"]
                        ),
                        "eligible_file_count": (
                            processing_sets[
                                "eligible_file_count"
                            ]
                        ),
                        "sets": processing_sets["sets"],
                    }
                }
            ),
            job_id,
        ),
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="processing_sets",
        current_step=(
            f"Created "
            f"{processing_sets['set_count']:,} "
            f"processing set(s) from "
            f"{processing_sets['eligible_file_count']:,} "
            f"expanded leaf files."
        ),
        stage_processed_files=0,
        stage_total_files=(
            processing_sets["eligible_file_count"]
        ),
    )

    routing = AzureRoutingConfig.from_args(
        workspace=workspace,
        client=client_id,
        project=matter_id,
        azure_write=True,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="doc_id_assignment",
        current_step="Assigning INSYT document IDs.",
    )

    check_cancel("doc_id_assignment")
    run_doc_id_assignment(
        db,
        settings,
        job_id,
        matter_id,
        routing=routing,
        prefix=doc_prefix,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="text_extraction",
        current_step="Preparing native text extraction.",
    )

    check_cancel("text_extraction")
    run_text_extraction(
        db,
        settings,
        job_id,
        matter_id,
        workspace=workspace,
        progress_callback=progress_callback,
    )

    _emit_pipeline_progress(
        progress_callback,
        db=db,
        job_id=job_id,
        stage="ocr_preflight",
        current_step="Evaluating OCR requirements.",
    )

    check_cancel("ocr_preflight")
    run_ocr_preflight(
        db,
        settings,
        job_id,
        matter_id,
    )

    if enable_live_ocr:
        if not settings.enable_live_ocr:
            raise RuntimeError(
                "Live OCR requested but neither APC_ENABLE_LIVE_OCR nor "
                "APC_API_ALLOW_LIVE_OCR is true."
            )

        check_cancel("ocr_live")

        live_ocr_result = run_live_ocr_placeholder(
            db,
            settings,
            job_id,
            matter_id,
            cancellation_callback=cancellation_callback,
        )

        if int(live_ocr_result.get("exception_count") or 0) > 0:
            warnings = live_ocr_result.get("warnings") or []

            db.execute(
                """
                UPDATE processing_job
                SET metadata_json=json_patch(
                    coalesce(metadata_json, '{}'),
                    ?
                )
                WHERE job_id=?
                """,
                (
                    json_dumps(
                        {
                            "live_ocr_status": "completed_with_exceptions",
                            "live_ocr_warnings": warnings,
                        }
                    ),
                    job_id,
                ),
            )

    elif enable_ocr_dry_run:
        check_cancel("ocr_dry_run")
        run_ocr_dry_run(db, settings, job_id, matter_id)

    if promote_review_ready:
        from pathlib import Path

        resolved_output_root = (
            output_root
            or str(
                Path(input_dir)
                .resolve()
                .parent
                / ".apc_review_output"
            )
        )

        check_cancel("review_promotion")

        run_review_promotion(
            db,
            settings,
            job_id,
            matter_id,
            output_root=resolved_output_root,
            cancellation_callback=cancellation_callback,
        )

    finalize_job(db, job_id)
    return job_id
