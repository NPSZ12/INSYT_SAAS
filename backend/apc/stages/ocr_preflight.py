from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..pdf_utils import count_pdf_pages, pdf_is_encrypted
from ..telemetry import StageRunner
from ..util import ceil_div, json_dumps, utc_now


IMAGE_EXTENSIONS = {"tif", "tiff", "jpg", "jpeg", "png", "bmp", "heif", "heic"}
OCRABLE_EXTENSIONS = IMAGE_EXTENSIONS | {"pdf"}


def estimate_page_count(extension: str, source_bytes: int, settings: Settings, path: str | None = None) -> tuple[int, str, str]:
    ext = extension.lower().lstrip(".")
    if ext in IMAGE_EXTENSIONS:
        if ext in {"tif", "tiff"}:
            return max(1, ceil_div(source_bytes, settings.ocr_estimated_scanned_pdf_bytes_per_page)), "IMAGE_TIFF_ESTIMATE", "low"
        return 1, "IMAGE_SINGLE_PAGE", "medium"
    if ext == "pdf":
        if path:
            pages, confidence = count_pdf_pages(Path(path))
            if pages > 0:
                return pages, "PDF_PAGE_COUNT", confidence
        estimated = max(1, ceil_div(source_bytes, settings.ocr_estimated_scanned_pdf_bytes_per_page))
        return estimated, "PDF_SIZE_ESTIMATE", "low"
    return 0, "NOT_OCRABLE", "high"


def _ocr_reason(ext: str, has_native_text: bool, text_bytes: int, path: str | None, page_reason: str) -> str:
    if ext not in OCRABLE_EXTENSIONS:
        return "NO_OCR_REQUIRED_NOT_OCRABLE"
    if ext == "pdf" and path and pdf_is_encrypted(Path(path)):
        return "OCR_BLOCKED_ENCRYPTED_PDF"
    if ext in IMAGE_EXTENSIONS:
        return "OCR_REQUIRED_IMAGE_FILE"
    if ext == "pdf" and not has_native_text and text_bytes <= 0:
        return "OCR_REQUIRED_PDF_NATIVE_TEXT_EMPTY"
    if ext == "pdf" and not has_native_text:
        return "OCR_REQUIRED_PDF_LOW_TEXT_DENSITY"
    return "NO_OCR_REQUIRED_NATIVE_TEXT_PRESENT"


def run_ocr_preflight(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    rows = db.query(
        """
        SELECT file_id, original_path, extension, source_bytes, has_native_text, text_bytes, page_count
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND is_denisted=0 AND is_duplicate=0
        """,
        (job_id,),
    )
    with StageRunner(db, settings, job_id, matter_id, "ocr_preflight", "ocr-candidate-estimator-v2") as stage:
        candidates = 0
        estimated_pages = 0
        reason_counts: dict[str, int] = {}
        low_confidence_files = 0

        for row in rows:
            ext = (row["extension"] or "").lower()
            source_bytes = int(row["source_bytes"] or 0)
            existing_pages = int(row["page_count"] or 0)
            page_count, page_reason, confidence = estimate_page_count(ext, source_bytes, settings, row["original_path"])
            if existing_pages > 0 and ext == "pdf":
                page_count = existing_pages
                page_reason = "PDF_PAGE_COUNT_FROM_TEXT_STAGE"
                confidence = "medium"
            has_native_text = bool(row["has_native_text"])
            text_bytes = int(row["text_bytes"] or 0)
            ocr_reason = _ocr_reason(ext, has_native_text, text_bytes, row["original_path"], page_reason)
            requires_ocr = 1 if ocr_reason.startswith("OCR_REQUIRED") else 0
            if requires_ocr:
                candidates += 1
                estimated_pages += page_count
                if confidence == "low":
                    low_confidence_files += 1
            reason_counts[ocr_reason] = reason_counts.get(ocr_reason, 0) + 1
            db.execute(
                """
                UPDATE file_processing_metrics
                SET requires_ocr=?, page_count=?, updated_at=?, stage_status_json=json_patch(stage_status_json, ?)
                WHERE file_id=?
                """,
                (
                    requires_ocr,
                    page_count,
                    utc_now(),
                    json_dumps(
                        {
                            "ocr_preflight": {
                                "reason": ocr_reason,
                                "page_count_reason": page_reason,
                                "page_count_confidence": confidence,
                            }
                        }
                    ),
                    row["file_id"],
                ),
            )

        estimated_ocr_cost_usd = (
            estimated_pages / 1000.0 * settings.fallback_ocr_read_price_per_1000_pages
            if estimated_pages
            else 0.0
        )

        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = candidates
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = candidates
        stage.metrics.pages_out = estimated_pages
        stage.metrics.extra.update(
            {
                "ocr_candidate_files": candidates,
                "estimated_ocr_pages": estimated_pages,
                "estimated_ocr_cost_usd_not_ledgered": estimated_ocr_cost_usd,
                "reason_counts": reason_counts,
                "low_confidence_page_estimate_files": low_confidence_files,
            }
        )
        db.execute("UPDATE processing_job SET ocr_page_count=? WHERE job_id=?", (estimated_pages, job_id))
