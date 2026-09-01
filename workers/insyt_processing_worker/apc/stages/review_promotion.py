from __future__ import annotations

import csv
import json
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET

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

DOCX_EXTENSIONS = {
    "docx",
}


PLACEHOLDER_TEXT_SOURCES = {
    "ocr_pending_placeholder",
    "native_text_signal_placeholder",
    "no_text_placeholder",
    "pdf_text_extraction_unavailable",
    "pdf_no_extractable_text",
}


PLACEHOLDER_TEXT_MARKERS = (
    "OCR dry-run placeholder.",
    "Live OCR has not been performed yet.",
    "Native text signal detected, but parser extraction is not available",
    "No extracted text available in local dry-run scaffold.",
    "PDF text extraction unavailable because pypdf is not installed.",
    "No extractable PDF text found.",
    "No extractable text found within Summaries text window.",
)

class ReviewPromotionRemediationRequired(RuntimeError):
    """
    Raised when a document cannot produce legitimate review-ready text.

    This is intentionally distinct from an unexpected processing failure.
    The native document may be preserved, but the document must not be
    represented as successfully promoted with synthetic placeholder text.
    """

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        text_source: str = "remediation_required",
    ) -> None:
        super().__init__(message)

        self.reason_code = str(
            reason_code
            or "TEXT_REMEDIATION_REQUIRED"
        )

        self.text_source = str(
            text_source
            or "remediation_required"
        )

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

def _extract_docx_native_text(
    path: Path,
) -> tuple[str, str]:
    """
    Extract native text directly from a DOCX package.

    DOCX files are ZIP containers containing WordprocessingML.
    This avoids requiring python-docx in the APC worker.

    The extractor reads:
      - main document body
      - headers
      - footers
      - footnotes
      - endnotes

    If the DOCX is unreadable or contains no meaningful text,
    promotion is sent to remediation rather than creating
    placeholder review text.
    """

    if not path.exists() or not path.is_file():
        raise ReviewPromotionRemediationRequired(
            f"DOCX source file does not exist: {path}",
            reason_code="DOCX_SOURCE_MISSING",
        )

    if not zipfile.is_zipfile(path):
        raise ReviewPromotionRemediationRequired(
            f"DOCX source is not a valid ZIP package: {path}",
            reason_code="DOCX_INVALID_PACKAGE",
        )

    namespace = {
        "w": (
            "http://schemas.openxmlformats.org/"
            "wordprocessingml/2006/main"
        ),
    }

    preferred_parts = [
        "word/document.xml",
    ]

    try:
        with zipfile.ZipFile(
            path,
            "r",
        ) as archive:
            available_names = set(
                archive.namelist()
            )

            supplemental_parts = sorted(
                name
                for name in available_names
                if (
                    name.startswith(
                        "word/header"
                    )
                    or name.startswith(
                        "word/footer"
                    )
                    or name
                    in {
                        "word/footnotes.xml",
                        "word/endnotes.xml",
                    }
                )
                and name.endswith(".xml")
            )

            xml_parts = [
                part
                for part in (
                    preferred_parts
                    + supplemental_parts
                )
                if part in available_names
            ]

            if (
                "word/document.xml"
                not in available_names
            ):
                raise ReviewPromotionRemediationRequired(
                    (
                        "DOCX package does not contain "
                        "word/document.xml."
                    ),
                    reason_code=(
                        "DOCX_DOCUMENT_XML_MISSING"
                    ),
                )

            output_sections: list[str] = []

            for part_name in xml_parts:
                try:
                    xml_data = (
                        archive.read(
                            part_name
                        )
                    )

                    root = ET.fromstring(
                        xml_data
                    )

                except (
                    KeyError,
                    ET.ParseError,
                    ValueError,
                ) as exc:
                    if (
                        part_name
                        == "word/document.xml"
                    ):
                        raise (
                            ReviewPromotionRemediationRequired(
                                (
                                    "Unable to parse primary "
                                    f"DOCX XML: {exc}"
                                ),
                                reason_code=(
                                    "DOCX_XML_PARSE_FAILED"
                                ),
                            )
                        ) from exc

                    continue

                paragraphs: list[str] = []

                for paragraph in root.findall(
                    ".//w:p",
                    namespace,
                ):
                    paragraph_parts: list[str] = []

                    for node in paragraph.iter():
                        local_name = (
                            node.tag.rsplit(
                                "}",
                                1,
                            )[-1]
                        )

                        if local_name == "t":
                            if node.text:
                                paragraph_parts.append(
                                    node.text
                                )

                        elif local_name == "tab":
                            paragraph_parts.append(
                                "\t"
                            )

                        elif local_name in {
                            "br",
                            "cr",
                        }:
                            paragraph_parts.append(
                                "\n"
                            )

                    paragraph_text = (
                        "".join(
                            paragraph_parts
                        )
                        .strip()
                    )

                    if paragraph_text:
                        paragraphs.append(
                            paragraph_text
                        )

                section_text = (
                    "\n".join(
                        paragraphs
                    )
                    .strip()
                )

                if section_text:
                    output_sections.append(
                        section_text
                    )

    except ReviewPromotionRemediationRequired:
        raise

    except zipfile.BadZipFile as exc:
        raise ReviewPromotionRemediationRequired(
            f"Invalid DOCX ZIP package: {exc}",
            reason_code="DOCX_INVALID_PACKAGE",
        ) from exc

    except Exception as exc:
        raise ReviewPromotionRemediationRequired(
            f"DOCX extraction failed: {exc}",
            reason_code="DOCX_EXTRACTION_FAILED",
        ) from exc

    extracted_text = (
        "\n\n".join(
            output_sections
        )
        .strip()
    )

    if not extracted_text:
        raise ReviewPromotionRemediationRequired(
            (
                "DOCX extraction completed but produced "
                "no meaningful text."
            ),
            reason_code="DOCX_NO_EXTRACTABLE_TEXT",
        )

    return (
        extracted_text,
        "docx_native_text",
    )

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

def _row_value(row, *names: str):
    for name in names:
        try:
            if hasattr(row, "keys") and name not in row.keys():
                continue

            value = row[name]
        except Exception:
            try:
                value = getattr(row, name, None)
            except Exception:
                value = None

        if value not in (None, ""):
            return value

    return None

def _is_placeholder_text(
    text: str,
    text_source: str = "",
) -> bool:
    """
    Identify legacy scaffold/dry-run content that must never be
    treated as legitimate extracted review text.
    """

    source_key = str(
        text_source
        or ""
    ).strip().casefold()

    if source_key in {
        item.casefold()
        for item in PLACEHOLDER_TEXT_SOURCES
    }:
        return True

    value = str(
        text
        or ""
    )

    return any(
        marker.casefold()
        in value.casefold()
        for marker
        in PLACEHOLDER_TEXT_MARKERS
    )

def _read_existing_extracted_text(row) -> tuple[str, str] | None:
    """
    Prefer text already produced by an earlier processing stage, especially
    Azure Document Intelligence Live OCR.

    The OCR stage runs before review_promotion and may populate one of several
    text-path fields depending on the current database schema.

    If the schema does not expose one of those path fields, fall back to the
    deterministic OCR output path derived from original_path and doc_id.
    """

    stage_status = _get_stage_status(row)
    ocr_live = stage_status.get("ocr_live") or {}

    stage_ocr_text_path = (
        ocr_live.get("text_path")
        if isinstance(ocr_live, dict)
        else None
    )

    text_path = _row_value(
        row,
        "ocr_text_path",
        "extracted_text_path",
        "text_path",
        "review_text_path",
        "output_text_path",
    )

    candidate_paths: list[Path] = []

    if stage_ocr_text_path:
        candidate_paths.append(
            Path(str(stage_ocr_text_path))
        )

    if text_path:
        text_path_obj = Path(str(text_path))

        if text_path_obj not in candidate_paths:
            candidate_paths.append(text_path_obj)

    # Live OCR fallback path:
    #
    #   source:
    #   .../<project>/uploads/example.png
    #
    #   OCR text:
    #   .../<project>/text/<DOC_ID>.txt
    #
    # This is the same deterministic location used by ocr_live_placeholder.py
    # when file_processing_metrics does not contain a writable text-path field.
    original_path = _row_value(
        row,
        "original_path",
        "source_path",
        "file_path",
        "path",
    )

    doc_id = _row_value(
        row,
        "doc_id",
        "assigned_doc_id",
        "document_id",
    )

    if original_path and doc_id:
        source = Path(str(original_path))

        derived_ocr_path = (
            source.parent.parent
            / "text"
            / f"{doc_id}.txt"
        )

        if derived_ocr_path not in candidate_paths:
            candidate_paths.append(derived_ocr_path)

    for path in candidate_paths:
        if not path.exists() or not path.is_file():
            continue

        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if not text.strip():
            continue

        text_source = (
            (
                ocr_live.get("engine")
                if isinstance(
                    ocr_live,
                    dict,
                )
                else None
            )
            or _row_value(
                row,
                "text_extraction_method",
                "ocr_engine",
            )
            or "existing_extracted_text"
        )

        text_source = str(
            text_source
        )

        #
        # Never resurrect legacy dry-run/scaffold text.
        #
        if _is_placeholder_text(
            text,
            text_source,
        ):
            continue

        return (
            text,
            text_source,
        )

    return None

def _build_text_output(
    row,
    workspace: str = "capture",
) -> tuple[str, str]:
    path = Path(
        row["original_path"]
    )

    ext = _safe_ext(
        row["extension"]
    )

    workspace_key = str(
        workspace
        or "capture"
    ).strip().lower()

    #
    # First preference:
    # legitimate output already created by an earlier stage,
    # including Azure Document Intelligence.
    #
    existing_text = (
        _read_existing_extracted_text(
            row
        )
    )

    if existing_text is not None:
        text_content, text_source = (
            existing_text
        )

        if (
            text_content.strip()
            and not _is_placeholder_text(
                text_content,
                text_source,
            )
        ):
            return (
                text_content,
                text_source,
            )

    #
    # Plain text/native text formats.
    #
    if ext in TEXT_EXTENSIONS:
        text_content, text_source = (
            _read_textish(
                path,
                ext,
            )
        )

        if (
            text_content.strip()
            and not _is_placeholder_text(
                text_content,
                text_source,
            )
        ):
            return (
                text_content,
                text_source,
            )

        raise ReviewPromotionRemediationRequired(
            (
                "Native text file contains no "
                "legitimate extracted text."
            ),
            reason_code=(
                "NATIVE_TEXT_EMPTY"
            ),
        )

    #
    # ZIP-expanded DOCX files must be parsed directly rather
    # than falling into the OCR placeholder branch.
    #
    if ext in DOCX_EXTENSIONS:
        return (
            _extract_docx_native_text(
                path
            )
        )

    #
    # PDF native extraction.
    #
    if ext == "pdf":
        if (
            workspace_key
            == "summaries"
        ):
            text_window = (
                _get_text_window_from_row(
                    row
                )
            )

            max_pages = int(
                text_window.get(
                    "page_count"
                )
                or text_window.get(
                    "max_pages"
                )
                or _summaries_text_max_pages()
            )

            max_pages = max(
                1,
                max_pages,
            )

            stop_marker = (
                text_window.get(
                    "stop_marker"
                )
                or _summaries_stop_marker()
            )

            include_stop_marker_page = bool(
                (
                    text_window.get(
                        "include_stop_marker_page"
                    )
                    if (
                        "include_stop_marker_page"
                        in text_window
                    )
                    else (
                        _summaries_include_stop_marker_page()
                    )
                )
            )

            text_content, text_source = (
                _extract_pdf_text_window(
                    path,
                    max_pages=max_pages,
                    stop_marker=stop_marker,
                    include_stop_marker_page=(
                        include_stop_marker_page
                    ),
                )
            )

            if _is_placeholder_text(
                text_content,
                text_source,
            ):
                raise (
                    ReviewPromotionRemediationRequired(
                        (
                            "Summaries PDF text "
                            "extraction did not produce "
                            "review-ready text."
                        ),
                        reason_code=(
                            "PDF_TEXT_REMEDIATION_REQUIRED"
                        ),
                    )
                )

            return (
                text_content,
                text_source,
            )

        if int(
            row["has_native_text"]
            or 0
        ):
            text_content, text_source = (
                _extract_pdf_native_text(
                    path
                )
            )

            if (
                text_content.strip()
                and not _is_placeholder_text(
                    text_content,
                    text_source,
                )
            ):
                return (
                    text_content,
                    text_source,
                )

    #
    # At this point OCR was required but no legitimate live OCR
    # result exists. This must be remediation, not fake text.
    #
    if int(
        row["requires_ocr"]
        or 0
    ):
        raise ReviewPromotionRemediationRequired(
            (
                "Document requires OCR, but no legitimate "
                "live OCR text is available."
            ),
            reason_code=(
                "LIVE_OCR_TEXT_MISSING"
            ),
            text_source=(
                "ocr_remediation_required"
            ),
        )

    #
    # Native-text signal without an available parser is also
    # remediation. Never synthesize text.
    #
    if int(
        row["has_native_text"]
        or 0
    ):
        raise ReviewPromotionRemediationRequired(
            (
                "Native text was detected, but no supported "
                "parser produced review-ready text."
            ),
            reason_code=(
                "NATIVE_TEXT_PARSER_REQUIRED"
            ),
            text_source=(
                "native_text_remediation_required"
            ),
        )

    raise ReviewPromotionRemediationRequired(
        (
            "No legitimate extracted text is available "
            "for review promotion."
        ),
        reason_code=(
            "NO_REVIEW_READY_TEXT"
        ),
        text_source=(
            "text_remediation_required"
        ),
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
        SELECT *
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
            status = "pending"
            event_exceptions: list[dict] = []
            text_source = "none"

            try:
                #
                # Preserve the native document even when text
                # extraction later requires remediation.
                #
                shutil.copy2(
                    row["original_path"],
                    native_output,
                )

                native_bytes += (
                    native_output
                    .stat()
                    .st_size
                )

                (
                    text_content,
                    text_source,
                ) = _build_text_output(
                    row,
                    workspace=workspace,
                )

                if (
                    not text_content.strip()
                    or _is_placeholder_text(
                        text_content,
                        text_source,
                    )
                ):
                    raise (
                        ReviewPromotionRemediationRequired(
                            (
                                "Text extraction returned "
                                "non-reviewable content."
                            ),
                            reason_code=(
                                "NON_REVIEWABLE_TEXT"
                            ),
                            text_source=(
                                text_source
                                or "text_remediation_required"
                            ),
                        )
                    )

                text_output.write_text(
                    text_content,
                    encoding="utf-8",
                    errors="replace",
                )

                text_bytes += (
                    text_output
                    .stat()
                    .st_size
                )

                status = "promoted"
                promoted += 1

            except (
                ReviewPromotionRemediationRequired
            ) as exc:
                status = (
                    "remediation_required"
                )

                text_source = (
                    exc.text_source
                )

                #
                # A prior run may have left a stale text file.
                # Remove it so the document cannot appear
                # review-ready accidentally.
                #
                if text_output.exists():
                    try:
                        text_output.unlink()
                    except Exception:
                        pass

                remediation_event = {
                    "error": str(exc),
                    "reason_code": (
                        exc.reason_code
                    ),
                    "remediation_required": (
                        True
                    ),
                }

                event_exceptions.append(
                    remediation_event
                )

                exceptions.append(
                    {
                        "file_id": (
                            row["file_id"]
                        ),
                        "doc_id": doc_id,
                        **remediation_event,
                    }
                )

            except Exception as exc:  # noqa: BLE001
                status = "failed"

                if text_output.exists():
                    try:
                        text_output.unlink()
                    except Exception:
                        pass

                event_exceptions.append(
                    {
                        "error": repr(
                            exc
                        ),
                    }
                )

                exceptions.append(
                    {
                        "file_id": (
                            row["file_id"]
                        ),
                        "doc_id": doc_id,
                        "error": repr(
                            exc
                        ),
                    }
                )

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
                (
                    str(text_output)
                    if status == "promoted"
                    else None
                ),
                    status,
                    utc_now(),
                    json_dumps(
                        {
                            "review_promotion": {
                                "status": status,
                                "text_source": text_source,
                                "remediation_required": (
                                    status == "remediation_required"
                                ),
                                "exceptions": event_exceptions,
                            }
                        }
                    ),
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
                    (
                        str(text_output)
                        if status == "promoted"
                        else ""
                    ),
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
                    "text_path": (
                        str(text_output)
                        if status == "promoted"
                        else ""
                    ),
                    "remediation_required": (
                        1
                        if status == "remediation_required"
                        else 0
                    ),
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
