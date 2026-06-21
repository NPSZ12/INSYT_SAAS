import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


SUMMARY_QC_TITLES = [
    "Report",
    "Overview",
    "Timeline of Key Events",
    "Pre-Existing Medical Conditions and Chronic Disease Management",
    "Initial Presentation, Diagnostic Delay, and Cancer Diagnosis",
    "Surgical Treatment and Intraoperative Findings",
    "Pathology Results and Staging",
    "Post-Operative Complications and Hospital Course",
    "Post-Operative Recovery, Functional Outcomes, and Ongoing Care",
    "Key Practitioners and Their Roles",
    "Key Concerns and Potential Issues",
    "Record Summaries",
]

SUMMARIES_EXTRACTION_STOP_MARKERS = [
    "Original Source Medical Records (converted to text)",
    "Original Source Medical Records Converted to Text",
]

DEFAULT_CHUNK_SIZE = 10
DEFAULT_STOP_MARKER_MIN_PAGE = 2


@dataclass
class SummaryTextChunk:
    chunk_index: int
    start_page: int
    end_page: int
    text: str
    stopped_on_marker: bool = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_title_key(title: str) -> str:
    return (
        title.strip()
        .lower()
        .replace("&", "and")
        .replace("-", " ")
        .replace(",", "")
        .replace(":", "")
    )


def _build_title_regex(title: str) -> re.Pattern:
    """
    Builds a forgiving heading regex.

    It allows the title to appear:
    - at the beginning of a line
    - with extra whitespace
    - with an optional colon
    - case-insensitive
    """

    escaped = re.escape(title.strip())
    escaped = escaped.replace(r"\ ", r"\s+")

    return re.compile(
        rf"(?im)^\s*{escaped}\s*:?\s*$"
    )


def _clean_extracted_text(text: str) -> str:
    """
    Light cleanup only. Do not over-normalize here because downstream
    section parsing benefits from preserved line breaks.
    """

    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive trailing whitespace per line.
    lines = [line.rstrip() for line in text.split("\n")]

    # Collapse very large blank gaps while preserving section readability.
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)

    return cleaned.strip()


def _truncate_at_stop_marker(
    text: str,
    *,
    start_page: int,
    stop_marker_min_page: int = DEFAULT_STOP_MARKER_MIN_PAGE,
) -> tuple[str, bool]:
    """
    Stop at the original-source-records section, but ignore early
    table-of-contents references.

    The PDFs may use either:
    - Original Source Medical Records (converted to text)
    - Original Source Medical Records Converted to Text
    """

    if not text:
        return "", False

    if start_page < stop_marker_min_page:
        return text, False

    marker_indexes: list[int] = []

    for marker in SUMMARIES_EXTRACTION_STOP_MARKERS:
        marker_index = text.find(marker)

        if marker_index >= 0:
            marker_indexes.append(marker_index)

    if not marker_indexes:
        return text, False

    marker_index = min(marker_indexes)

    return text[:marker_index].rstrip(), True


def _page_ranges(total_pages: int, chunk_size: int = DEFAULT_CHUNK_SIZE):
    start = 1

    while start <= total_pages:
        end = min(start + chunk_size - 1, total_pages)
        yield start, end
        start = end + 1


def _extract_pdf_page_range_text(
    doc: Any,
    start_page: int,
    end_page: int,
) -> str:
    """
    PyMuPDF pages are zero-indexed. User-facing page ranges are one-indexed.
    """

    parts: list[str] = []

    for page_number in range(start_page, end_page + 1):
        page = doc.load_page(page_number - 1)

        # "text" is intentionally used first because these summary PDFs
        # generally already contain embedded text after conversion.
        page_text = page.get_text("text") or ""

        parts.append(
            "\n".join(
                [
                    "",
                    f"===== PAGE {page_number} =====",
                    "",
                    page_text,
                    "",
                ]
            )
        )

    return "\n".join(parts)


def build_summaries_large_pdf_text_from_bytes(
    pdf_bytes: bytes,
    *,
    pdf_name: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stop_marker_min_page: int = DEFAULT_STOP_MARKER_MIN_PAGE,
) -> dict[str, Any]:
    """
    Summaries-only large PDF text builder.

    Responsibilities:
    - Extract PDF text in 10-page chunks by default.
    - Stop at the exact Summaries stop marker.
    - Rebuild complete text before the original source records.
    - Detect configured QC section titles.
    - Return full text, chunks, sections, and manifest.

    This function does not write to Azure directly. The caller should write:
    - full text
    - chunk text
    - manifest JSON
    - section JSON
    """

    if fitz is None:
        raise RuntimeError(
            "PyMuPDF is not installed. Install dependency 'pymupdf' "
            "or add it to backend requirements."
        )

    if not pdf_bytes:
        raise ValueError("No PDF bytes provided.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        total_pages = int(doc.page_count or 0)

        chunks: list[SummaryTextChunk] = []
        full_parts: list[str] = []
        stopped_on_marker = False
        stopped_at_chunk_index: int | None = None
        stopped_at_page_range: str | None = None

        for chunk_index, (start_page, end_page) in enumerate(
            _page_ranges(total_pages, chunk_size),
            start=1,
        ):
            raw_chunk_text = _extract_pdf_page_range_text(
                doc,
                start_page,
                end_page,
            )

            raw_chunk_text, chunk_stopped = _truncate_at_stop_marker(
                raw_chunk_text,
                start_page=start_page,
                stop_marker_min_page=stop_marker_min_page,
            )

            cleaned_chunk_text = _clean_extracted_text(raw_chunk_text)

            chunk = SummaryTextChunk(
                chunk_index=chunk_index,
                start_page=start_page,
                end_page=end_page,
                text=cleaned_chunk_text,
                stopped_on_marker=chunk_stopped,
            )

            chunks.append(chunk)

            if cleaned_chunk_text:
                full_parts.append(
                    "\n".join(
                        [
                            "",
                            f"===== CHUNK {chunk_index}: PAGES {start_page}-{end_page} =====",
                            "",
                            cleaned_chunk_text,
                            "",
                        ]
                    )
                )

            if chunk_stopped:
                stopped_on_marker = True
                stopped_at_chunk_index = chunk_index
                stopped_at_page_range = f"{start_page}-{end_page}"
                break

        full_text = _clean_extracted_text("\n".join(full_parts))

        sections = extract_configured_qc_sections(full_text)

        manifest = {
            "pdf_name": pdf_name,
            "builder": "summaries_large_text_builder",
            "version": "1.0",
            "status": "completed",
            "created_at": _utc_now_iso(),
            "chunk_size": chunk_size,
            "stop_marker_min_page": stop_marker_min_page,
            "total_pdf_pages": total_pages,
            "chunks_created": len(chunks),
            "stopped_on_marker": stopped_on_marker,
            "stop_markers": SUMMARIES_EXTRACTION_STOP_MARKERS,
            "stopped_at_chunk_index": stopped_at_chunk_index,
            "stopped_at_page_range": stopped_at_page_range,
            "configured_qc_titles": SUMMARY_QC_TITLES,
            "detected_qc_titles": [
                section["title"]
                for section in sections
                if section.get("detected")
            ],
            "missing_qc_titles": [
                section["title"]
                for section in sections
                if not section.get("detected")
            ],
            "full_text_char_count": len(full_text),
        }

        return {
            "pdf_name": pdf_name,
            "full_text": full_text,
            "chunks": [
                {
                    "chunk_index": chunk.chunk_index,
                    "start_page": chunk.start_page,
                    "end_page": chunk.end_page,
                    "text": chunk.text,
                    "stopped_on_marker": chunk.stopped_on_marker,
                    "char_count": len(chunk.text or ""),
                }
                for chunk in chunks
            ],
            "sections": sections,
            "manifest": manifest,
        }

    finally:
        doc.close()


def extract_configured_qc_sections(full_text: str) -> list[dict[str, Any]]:
    """
    Finds configured QC titles and extracts text between each title and the
    next configured title.

    This prepares the structure we need later for Summary Sets, without yet
    forcing the batching/QC behavior.
    """

    if not full_text:
        return [
            {
                "title": title,
                "title_key": _normalize_title_key(title),
                "detected": False,
                "start_char": None,
                "end_char": None,
                "text": "",
                "char_count": 0,
            }
            for title in SUMMARY_QC_TITLES
        ]

    matches: list[dict[str, Any]] = []

    for title in SUMMARY_QC_TITLES:
        title_regex = _build_title_regex(title)
        match = title_regex.search(full_text)

        if match:
            matches.append(
                {
                    "title": title,
                    "title_key": _normalize_title_key(title),
                    "detected": True,
                    "heading_start": match.start(),
                    "heading_end": match.end(),
                }
            )
        else:
            matches.append(
                {
                    "title": title,
                    "title_key": _normalize_title_key(title),
                    "detected": False,
                    "heading_start": None,
                    "heading_end": None,
                }
            )

    detected = [
        item for item in matches if item.get("detected")
    ]

    detected.sort(key=lambda item: item["heading_start"])

    section_by_title: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(detected):
        next_item = detected[index + 1] if index + 1 < len(detected) else None

        start_char = item["heading_end"]
        end_char = (
            next_item["heading_start"]
            if next_item
            else len(full_text)
        )

        section_text = full_text[start_char:end_char].strip()

        section_by_title[item["title"]] = {
            "title": item["title"],
            "title_key": item["title_key"],
            "detected": True,
            "start_char": start_char,
            "end_char": end_char,
            "text": section_text,
            "char_count": len(section_text),
        }

    # Return sections in configured order, not discovered order.
    ordered_sections: list[dict[str, Any]] = []

    for title in SUMMARY_QC_TITLES:
        if title in section_by_title:
            ordered_sections.append(section_by_title[title])
        else:
            ordered_sections.append(
                {
                    "title": title,
                    "title_key": _normalize_title_key(title),
                    "detected": False,
                    "start_char": None,
                    "end_char": None,
                    "text": "",
                    "char_count": 0,
                }
            )

    return ordered_sections


def serialize_summaries_large_text_result(
    result: dict[str, Any],
) -> tuple[str, str, str]:
    """
    Convenience helper for callers that want strings ready for blob upload.

    Returns:
    - full_text
    - sections_json
    - manifest_json
    """

    full_text = result.get("full_text") or ""

    sections_json = json.dumps(
        result.get("sections") or [],
        indent=2,
        ensure_ascii=False,
    )

    manifest_json = json.dumps(
        result.get("manifest") or {},
        indent=2,
        ensure_ascii=False,
    )

    return full_text, sections_json, manifest_json