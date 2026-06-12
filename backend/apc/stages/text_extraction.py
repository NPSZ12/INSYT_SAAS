from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..pdf_utils import count_pdf_pages, estimate_pdf_native_text_bytes, pdf_is_encrypted
from ..telemetry import StageRunner
from ..util import json_dumps, utc_now


TEXT_EXTENSIONS = {"txt", "csv", "json", "xml", "html", "htm", "md", "log", "rtf"}


def _text_file_signal(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data.strip()), "text_file"


def _native_text_signal(path: Path, extension: str) -> tuple[int, int, str, str, bool]:
    ext = extension.lower().lstrip(".")
    if ext in TEXT_EXTENSIONS:
        text_bytes, signal = _text_file_signal(path)
        return 0, text_bytes, "not_applicable", signal, False
    if ext == "pdf":
        pages, page_confidence = count_pdf_pages(path)
        text_bytes, signal = estimate_pdf_native_text_bytes(path)
        return pages, text_bytes, page_confidence, signal, pdf_is_encrypted(path)
    return 0, 0, "not_applicable", "unsupported_native_text_lite", False


def run_text_extraction(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    rows = db.query(
        """
        SELECT file_id, original_path, extension, source_bytes
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND is_denisted=0 AND is_duplicate=0
        """,
        (job_id,),
    )
    with StageRunner(db, settings, job_id, matter_id, "text_extraction", "native-text-and-pdf-signal") as stage:
        text_docs = 0
        text_bytes_total = 0
        pdf_pages_total = 0
        encrypted_pdfs = 0
        exceptions = []
        signal_counts: dict[str, int] = {}
        for row in rows:
            try:
                path = Path(row["original_path"])
                ext = row["extension"] or ""
                page_count, text_bytes, page_confidence, text_signal, encrypted = _native_text_signal(path, ext)
                has_text = 1 if text_bytes >= settings.ocr_low_text_bytes_threshold else 0
                if has_text:
                    text_docs += 1
                    text_bytes_total += text_bytes
                if page_count:
                    pdf_pages_total += page_count
                if encrypted:
                    encrypted_pdfs += 1
                signal_counts[text_signal] = signal_counts.get(text_signal, 0) + 1
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET text_bytes=?, has_native_text=?, page_count=CASE WHEN ? > 0 THEN ? ELSE page_count END,
                        updated_at=?, stage_status_json=json_patch(stage_status_json, ?)
                    WHERE file_id=?
                    """,
                    (
                        text_bytes,
                        has_text,
                        page_count,
                        page_count,
                        utc_now(),
                        json_dumps(
                            {
                                "text_extraction": {
                                    "signal": text_signal,
                                    "page_count": page_count,
                                    "page_count_confidence": page_confidence,
                                    "encrypted_pdf": encrypted,
                                }
                            }
                        ),
                        row["file_id"],
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                exceptions.append({"file_id": row["file_id"], "error": repr(exc)})
        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = len(rows)
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = len(rows)
        stage.metrics.bytes_in = sum(int(r["source_bytes"]) for r in rows)
        stage.metrics.bytes_out = text_bytes_total
        stage.metrics.pages_out = pdf_pages_total
        stage.metrics.exceptions = len(exceptions)
        stage.metrics.extra.update(
            {
                "text_docs": text_docs,
                "text_bytes_total": text_bytes_total,
                "pdf_pages_total": pdf_pages_total,
                "encrypted_pdfs": encrypted_pdfs,
                "signal_counts": signal_counts,
                "exceptions": exceptions[:50],
            }
        )
