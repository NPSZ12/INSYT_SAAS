from __future__ import annotations

import os
from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..pdf_utils import count_pdf_pages, estimate_pdf_native_text_bytes, pdf_is_encrypted

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from ..telemetry import StageRunner
from ..util import json_dumps, utc_now


TEXT_EXTENSIONS = {"txt", "csv", "json", "xml", "html", "htm", "md", "log", "rtf"}

DEFAULT_SUMMARIES_STOP_MARKER = "Original Source Medical Records Converted to Text"


def _is_summaries_workspace(workspace: str | None) -> bool:
    return str(workspace or "").strip().lower() == "summaries"


def _summaries_stop_marker() -> str:
    return os.getenv(
        "APC_SUMMARIES_STOP_MARKER",
        DEFAULT_SUMMARIES_STOP_MARKER,
    ).strip()


def _summaries_text_max_pages() -> int:
    try:
        return max(
            1,
            int(os.getenv("APC_SUMMARIES_TEXT_MAX_PAGES", "400")),
        )
    except Exception:
        return 400


def _summaries_include_stop_marker_page() -> bool:
    return os.getenv(
        "APC_SUMMARIES_INCLUDE_STOP_MARKER_PAGE",
        "false",
    ).strip().lower() in {"1", "true", "yes", "y", "on"}


def _estimate_summaries_pdf_text_window(path: Path) -> dict:
    """
    Summaries PDFs are combined packets.

    The native PDF must stay whole, but text/OCR should only apply to the
    summary section before:
        Original Source Medical Records Converted to Text

    This avoids extracting/OCRing the underlying source medical records.
    """

    total_pages, total_page_confidence = count_pdf_pages(path)

    result = {
        "total_page_count": total_pages,
        "page_count": total_pages,
        "page_count_confidence": total_page_confidence,
        "text_bytes": 0,
        "signal": "summaries_pdf_window_unavailable",
        "encrypted": pdf_is_encrypted(path),
        "stop_marker": _summaries_stop_marker(),
        "stop_marker_found": False,
        "stop_marker_page": None,
        "max_pages": _summaries_text_max_pages(),
        "include_stop_marker_page": _summaries_include_stop_marker_page(),
    }

    if result["encrypted"]:
        result["page_count"] = min(
            total_pages or result["max_pages"],
            result["max_pages"],
        )
        result["signal"] = "summaries_pdf_encrypted_limited_pages"
        return result

    if PdfReader is None:
        result["page_count"] = min(
            total_pages or result["max_pages"],
            result["max_pages"],
        )
        result["signal"] = "summaries_pdf_pypdf_unavailable_limited_pages"
        return result

    stop_marker = result["stop_marker"].lower()
    max_pages = result["max_pages"]
    include_stop_marker_page = result["include_stop_marker_page"]

    text_bytes_total = 0
    effective_pages = 0

    try:
        reader = PdfReader(str(path))

        for page_index, page in enumerate(reader.pages, start=1):
            if page_index > max_pages:
                effective_pages = max_pages
                result["signal"] = "summaries_pdf_max_pages_reached"
                break

            page_text = page.extract_text() or ""
            page_text_bytes = len(page_text.encode("utf-8", errors="ignore"))
            page_has_stop_marker = bool(
                stop_marker and stop_marker in page_text.lower()
            )

            if page_has_stop_marker:
                result["stop_marker_found"] = True
                result["stop_marker_page"] = page_index

                if include_stop_marker_page:
                    text_bytes_total += page_text_bytes
                    effective_pages = page_index
                else:
                    effective_pages = max(0, page_index - 1)

                result["signal"] = "summaries_pdf_stop_marker_found"
                break

            text_bytes_total += page_text_bytes
            effective_pages = page_index

        if not result["stop_marker_found"] and effective_pages == 0:
            effective_pages = min(total_pages or max_pages, max_pages)
            result["signal"] = "summaries_pdf_no_text_limited_pages"

        elif not result["stop_marker_found"] and effective_pages < max_pages:
            result["signal"] = "summaries_pdf_completed_before_max_pages"

        elif not result["stop_marker_found"]:
            result["signal"] = "summaries_pdf_stop_marker_not_found_limited_pages"

        result["page_count"] = effective_pages
        result["text_bytes"] = text_bytes_total

        return result

    except Exception as exc:
        result["page_count"] = min(
            total_pages or max_pages,
            max_pages,
        )
        result["signal"] = f"summaries_pdf_window_error:{type(exc).__name__}"
        return result

def _text_file_signal(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data.strip()), "text_file"


def _native_text_signal(
    path: Path,
    extension: str,
    workspace: str | None = None,
) -> tuple[int, int, str, str, bool, dict]:
    ext = extension.lower().lstrip(".")

    if ext in TEXT_EXTENSIONS:
        text_bytes, signal = _text_file_signal(path)
        return 0, text_bytes, "not_applicable", signal, False, {}

    if ext == "pdf":
        if _is_summaries_workspace(workspace):
            summaries_window = _estimate_summaries_pdf_text_window(path)

            return (
                int(summaries_window.get("page_count") or 0),
                int(summaries_window.get("text_bytes") or 0),
                str(summaries_window.get("page_count_confidence") or "unknown"),
                str(summaries_window.get("signal") or "summaries_pdf_window"),
                bool(summaries_window.get("encrypted") or False),
                summaries_window,
            )

        pages, page_confidence = count_pdf_pages(path)
        text_bytes, signal = estimate_pdf_native_text_bytes(path)

        return pages, text_bytes, page_confidence, signal, pdf_is_encrypted(path), {}

    return 0, 0, "not_applicable", "unsupported_native_text_lite", False, {}


def run_text_extraction(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    workspace: str = "capture",
) -> None:
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
                page_count, text_bytes, page_confidence, text_signal, encrypted, text_window = _native_text_signal(
                    path,
                    ext,
                    workspace=workspace,
                )
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
                                    "workspace": workspace,
                                    "text_window": text_window,
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
                "workspace": workspace,
                "summaries_stop_marker": (
                    _summaries_stop_marker()
                    if _is_summaries_workspace(workspace)
                    else ""
                ),
                "summaries_text_max_pages": (
                    _summaries_text_max_pages()
                    if _is_summaries_workspace(workspace)
                    else None
                ),
                "exceptions": exceptions[:50],
            }
        )
