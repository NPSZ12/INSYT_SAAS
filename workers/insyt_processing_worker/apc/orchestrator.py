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
          coalesce(sum(CASE WHEN is_container=0 AND requires_ocr=1 THEN page_count ELSE 0 END),0) AS ocr_pages,
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
) -> str:
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
        load_denist_hashes(db, denist_hash_file, source_name="user-provided")

    run_inventory(db, settings, job_id, matter_id, input_dir=input_dir, custodian_id=custodian_id)
    run_container_expansion(db, settings, job_id, matter_id, input_dir=input_dir)
    run_hashing(db, settings, job_id, matter_id)
    run_denist(db, settings, job_id, matter_id)
    run_dedupe(db, settings, job_id, matter_id)
    run_prior_processed_duplicate_suppression(
        db,
        settings,
        job_id,
        matter_id,
        prior_processed_index=prior_processed_index,
    )
    run_family_detection(db, settings, job_id, matter_id)

    routing = AzureRoutingConfig.from_args(
        workspace=workspace,
        client=client_id,
        project=matter_id,
        azure_write=True,
    )

    run_doc_id_assignment(
        db,
        settings,
        job_id,
        matter_id,
        routing=routing,
        prefix=doc_prefix,
    )

    run_text_extraction(
        db,
        settings,
        job_id,
        matter_id,
        workspace=workspace,
    )
    run_ocr_preflight(db, settings, job_id, matter_id)

    if enable_live_ocr:
        if not settings.enable_live_ocr:
            raise RuntimeError(
                "Live OCR requested but neither APC_ENABLE_LIVE_OCR nor "
                "APC_API_ALLOW_LIVE_OCR is true."
            )
        run_live_ocr_placeholder(db, settings, job_id, matter_id)
    elif enable_ocr_dry_run:
        run_ocr_dry_run(db, settings, job_id, matter_id)

    if promote_review_ready:
        from pathlib import Path
        resolved_output_root = output_root or str(Path(input_dir).resolve().parent / ".apc_review_output")
        run_review_promotion(db, settings, job_id, matter_id, output_root=resolved_output_root)

    finalize_job(db, job_id)
    return job_id
