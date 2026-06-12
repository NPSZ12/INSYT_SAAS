from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now


def run_ocr_dry_run(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    """Record what OCR would cost without calling Azure Document Intelligence."""
    rows = db.query(
        """
        SELECT file_id, page_count, source_bytes
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND requires_ocr=1 AND is_denisted=0 AND is_duplicate=0
        """,
        (job_id,),
    )
    with StageRunner(db, settings, job_id, matter_id, "ocr_dry_run", "azure-document-intelligence-dry-run") as stage:
        total_pages = sum(int(r["page_count"] or 0) for r in rows)
        total_bytes = sum(int(r["source_bytes"] or 0) for r in rows)
        for row in rows:
            pages = int(row["page_count"] or 0)
            if pages <= 0:
                continue
            stage.quote_cost(
                azure_service="Azure AI Document Intelligence",
                meter_name="Read Pages",
                quantity=pages,
                unit="pages",
                file_id=row["file_id"],
                confidence_note="dry-run OCR estimate; no Azure Document Intelligence request was made",
            )
            db.execute(
                """
                UPDATE file_processing_metrics
                SET ocr_pages_submitted=0, ocr_pages_succeeded=0, ocr_pages_failed=0,
                    updated_at=?, stage_status_json=json_patch(stage_status_json, '{"ocr_dry_run":{"submitted":false}}')
                WHERE file_id=?
                """,
                (utc_now(), row["file_id"]),
            )
        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = len(rows)
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = len(rows)
        stage.metrics.bytes_in = total_bytes
        stage.metrics.pages_in = total_pages
        stage.metrics.pages_out = total_pages
        stage.metrics.extra.update(
            {
                "ocr_mode": "dry_run",
                "candidate_files": len(rows),
                "estimated_pages": total_pages,
                "safety": "No Azure OCR calls were made by this stage.",
            }
        )
