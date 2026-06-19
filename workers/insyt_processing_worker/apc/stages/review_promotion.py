from __future__ import annotations

import csv
import json
import os
import shutil

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import json_dumps, new_id, utc_now



TEXT_EXTENSIONS = {"txt", "csv", "json", "xml", "html", "htm", "md", "log", "rtf"}

DEFAULT_SUMMARIES_STOP_MARKER = "Original Source Medical Records Converted to Text"


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


def _get_stage_status(row) -> dict:
    raw = row["stage_status_json"] if "stage_status_json" in row.keys() else None

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _get_text_window_from_row(row) -> dict:
    status = _get_stage_status(row)
    text_extraction = status.get("text_extraction") or {}
    text_window = text_extraction.get("text_window") or {}

    return text_window if isinstance(text_window, dict) else {}


def _extract_pdf_text_window(
    path: Path,
    *,
    max_pages: int,
    stop_marker: str,
    include_stop_marker_page: bool,
) -> tuple[str, str]:
    """
    Extracts PDF text only through the Summaries text window.

    The native PDF remains untouched/full length. This only controls the staged
    .txt output used by Summaries panes and summary_extracts.
    """

    if PdfReader is None:
        return (
            "PDF text extraction unavailable because pypdf is not installed.\n"
            f"Original Path: {path}\n",
            "pdf_text_extraction_unavailable",
        )

    output_pages: list[str] = []
    marker = (stop_marker or "").lower()
    marker_found = False
    stop_marker_page = None

    reader = PdfReader(str(path))

    for page_number, page in enumerate(reader.pages, start=1):
        if page_number > max_pages:
            break

        page_text = page.extract_text() or ""
        page_has_marker = bool(marker and marker in page_text.lower())

        if page_has_marker:
            marker_found = True
            stop_marker_page = page_number

            if include_stop_marker_page:
                output_pages.append(
                    f"\n\n--- Page {page_number} ---\n\n{page_text}"
                )

            break

        output_pages.append(
            f"\n\n--- Page {page_number} ---\n\n{page_text}"
        )

    text = "\n".join(output_pages).strip()

    if not text:
        text = (
            "No extractable text found within Summaries text window.\n"
            f"Original Path: {path}\n"
            f"Max Pages: {max_pages}\n"
        )

    source = (
        "summaries_pdf_text_until_stop_marker"
        if marker_found
        else "summaries_pdf_text_until_max_pages"
    )

    if marker_found:
        source = f"{source}_page_{stop_marker_page}"

    return text, source


def _extract_pdf_native_text(path: Path) -> tuple[str, str]:
    """
    Generic PDF native text extraction for non-Summaries workspaces.
    Kept conservative to avoid changing Capture/Discovery behavior too much.
    """

    if PdfReader is None:
        return (
            "PDF text extraction unavailable because pypdf is not installed.\n"
            f"Original Path: {path}\n",
            "pdf_text_extraction_unavailable",
        )

    reader = PdfReader(str(path))
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append(
            f"\n\n--- Page {page_number} ---\n\n{page_text}"
        )

    text = "\n".join(pages).strip()

    if not text:
        return (
            "No extractable PDF text found.\n"
            f"Original Path: {path}\n",
            "pdf_no_extractable_text",
        )

    return text, "pdf_native_text"

def _safe_ext(extension: str | None) -> str:
    ext = (extension or "bin").lower().lstrip(".")
    return ext or "bin"


def _read_textish(path: Path, ext: str) -> tuple[str, str]:
    if ext in TEXT_EXTENSIONS:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "native_text_file"
        except Exception:
            return path.read_bytes().decode("utf-8", errors="replace"), "native_text_file_binary_decode"
    return "", "none"


def _build_text_output(row, workspace: str = "capture") -> tuple[str, str]:
    path = Path(row["original_path"])
    ext = _safe_ext(row["extension"])
    workspace_key = str(workspace or "capture").strip().lower()

    if ext in TEXT_EXTENSIONS:
        return _read_textish(path, ext)

    if ext == "pdf":
        if workspace_key == "summaries":
            text_window = _get_text_window_from_row(row)

            max_pages = int(
                text_window.get("page_count")
                or text_window.get("max_pages")
                or _summaries_text_max_pages()
            )

            max_pages = max(1, max_pages)

            stop_marker = (
                text_window.get("stop_marker")
                or _summaries_stop_marker()
            )

            include_stop_marker_page = bool(
                text_window.get("include_stop_marker_page")
                if "include_stop_marker_page" in text_window
                else _summaries_include_stop_marker_page()
            )

            return _extract_pdf_text_window(
                path,
                max_pages=max_pages,
                stop_marker=stop_marker,
                include_stop_marker_page=include_stop_marker_page,
            )

        if int(row["has_native_text"] or 0):
            return _extract_pdf_native_text(path)

    if int(row["requires_ocr"] or 0):
        return (
            "OCR dry-run placeholder. Live OCR has not been performed yet.\n"
            f"Doc ID: {row['doc_id']}\n"
            f"Original Path: {row['normalized_path']}\n"
            f"Estimated OCR Pages: {int(row['page_count'] or 0)}\n",
            "ocr_pending_placeholder",
        )

    if int(row["has_native_text"] or 0):
        return (
            "Native text signal detected, but parser extraction is not available for this file type.\n"
            f"Doc ID: {row['doc_id']}\n"
            f"Original Path: {row['normalized_path']}\n"
            f"Estimated Native Text Bytes: {int(row['text_bytes'] or 0)}\n",
            "native_text_signal_placeholder",
        )

    return (
        "No extracted text available in local dry-run scaffold.\n"
        f"Doc ID: {row['doc_id']}\n"
        f"Original Path: {row['normalized_path']}\n",
        "no_text_placeholder",
    )


def run_review_promotion(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    output_root: str,
) -> None:
    """Promote final reviewable set into source/native and source/text style folders.

    Local dev writes to an output folder. Production Azure Blob writes must use
    the canonical INSYT project path:

        {client}/{workspace}/{project_storage_key}/source/native
        {client}/{workspace}/{project_storage_key}/source/text

    Prefer AzureRoutingConfig.review_paths() for production blob paths instead
    of rebuilding client/workspace/project paths in this stage.
    """
    rows = db.query(
        """
        SELECT file_id, doc_id, original_path, normalized_path, extension, source_bytes, page_count,
            text_bytes, has_native_text, requires_ocr, is_duplicate, is_denisted, family_id,
            parent_file_id, md5, sha1, sha256, stage_status_json
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND is_denisted=0 AND is_duplicate=0 AND doc_id IS NOT NULL
        ORDER BY doc_id
        """,
        (job_id,),
    )
    
    job = db.query_one(
        "SELECT metadata_json FROM processing_job WHERE job_id=?",
        (job_id,),
    )

    workspace = "capture"

    try:
        metadata = json.loads(job["metadata_json"] or "{}") if job else {}
        workspace = str(metadata.get("workspace") or "capture").strip().lower()
    except Exception:
        workspace = "capture"

    root = Path(output_root).resolve() / job_id
    native_dir = root / "source" / "native"
    text_dir = root / "source" / "text"
    report_dir = root / "processing_center" / "reports"
    native_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / "review_ready_manifest.csv"

    with StageRunner(db, settings, job_id, matter_id, "review_promotion", "doc-id-native-text-promoter") as stage:
        exceptions: list[dict] = []
        promoted = 0
        native_bytes = 0
        text_bytes = 0
        manifest_rows = []
        for row in rows:
            ext = _safe_ext(row["extension"])
            doc_id = row["doc_id"]
            native_output = native_dir / f"{doc_id}.{ext}"
            text_output = text_dir / f"{doc_id}.txt"
            status = "promoted"
            event_exceptions: list[dict] = []
            text_source = "none"
            try:
                shutil.copy2(row["original_path"], native_output)
                native_bytes += native_output.stat().st_size
                text_content, text_source = _build_text_output(
                    row,
                    workspace=workspace,
                )
                text_output.write_text(text_content, encoding="utf-8", errors="replace")
                text_bytes += text_output.stat().st_size
                promoted += 1
            except Exception as exc:  # noqa: BLE001
                status = "failed"
                event_exceptions.append({"error": repr(exc)})
                exceptions.append({"file_id": row["file_id"], "doc_id": doc_id, "error": repr(exc)})

            db.execute(
                """
                UPDATE file_processing_metrics
                SET promoted_to_review=?, native_output_path=?, text_output_path=?, review_export_status=?,
                    updated_at=?, stage_status_json=json_patch(stage_status_json, ?)
                WHERE file_id=?
                """,
                (
                    1 if status == "promoted" else 0,
                    str(native_output),
                    str(text_output),
                    status,
                    utc_now(),
                    json_dumps({"review_promotion": {"status": status, "text_source": text_source}}),
                    row["file_id"],
                ),
            )
            db.execute(
                """
                INSERT INTO review_promotion_event (
                    event_id, matter_id, job_id, file_id, doc_id, original_path,
                    native_output_path, text_output_path, status, text_source, exception_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("PROMOTE"),
                    matter_id,
                    job_id,
                    row["file_id"],
                    doc_id,
                    row["original_path"],
                    str(native_output),
                    str(text_output),
                    status,
                    text_source,
                    json_dumps(event_exceptions),
                    utc_now(),
                ),
            )
            manifest_rows.append(
                {
                    "doc_id": doc_id,
                    "original_path": row["normalized_path"],
                    "original_filename": Path(row["normalized_path"]).name,
                    "native_path": str(native_output),
                    "text_path": str(text_output),
                    "extension": ext,
                    "source_bytes": int(row["source_bytes"] or 0),
                    "page_count": int(row["page_count"] or 0),
                    "requires_ocr": int(row["requires_ocr"] or 0),
                    "text_source": text_source,
                    "family_id": row["family_id"] or "",
                    "parent_file_id": row["parent_file_id"] or "",
                    "md5": row["md5"] or "",
                    "sha1": row["sha1"] or "",
                    "sha256": row["sha256"] or "",
                    "status": status,
                }
            )

        if manifest_rows:
            with manifest_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
                writer.writeheader()
                writer.writerows(manifest_rows)

        # Proxy for Azure Blob writes in production: native + text per promoted doc + manifest.
        blob_writes = (promoted * 2) + (1 if manifest_rows else 0)
        if blob_writes:
            stage.quote_cost("Storage", "Blob Write Operations", blob_writes, "operations", confidence_note="proxy for review-ready native/text/manifest writes")

        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = promoted
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = promoted
        stage.metrics.bytes_in = sum(int(r["source_bytes"] or 0) for r in rows)
        stage.metrics.bytes_out = native_bytes + text_bytes
        stage.metrics.exceptions = len(exceptions)
        stage.metrics.extra.update(
            {
                "workspace": workspace,
                "output_root": str(root),
                "native_dir": str(native_dir),
                "text_dir": str(text_dir),
                "manifest_path": str(manifest_path),
                "promoted_docs": promoted,
                "native_bytes": native_bytes,
                "text_bytes": text_bytes,
                "blob_write_proxy_count": blob_writes,
                "exceptions": exceptions[:50],
            }
        )
