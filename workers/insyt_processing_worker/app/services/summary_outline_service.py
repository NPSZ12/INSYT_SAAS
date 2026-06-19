import re
from datetime import datetime, timezone


TITLE_PATTERN = re.compile(r"^(\d{1,4}:\s+.+)$")
PAGE_PATTERN = re.compile(r"\bp{1,2}\.\s*(\d+)", re.IGNORECASE)

FIELD_LABEL_PATTERN = re.compile(
    r"^(Title|Citation|Original Summary|QC Summary)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_multiline(value: str) -> str:
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_page(citation: str):
    match = PAGE_PATTERN.search(citation or "")

    if not match:
        return None

    try:
        return int(match.group(1))
    except Exception:
        return None


def split_text_pages(text: str):
    """
    Splits generated TXT into combined-PDF pages.

    Expects page markers from summary_text_service like:
    --- Page 332 ---
    """

    pages = []
    current_page = None
    current_lines = []

    for line in (text or "").splitlines():
        stripped = line.strip()

        page_match = re.match(
            r"^-{2,}\s*Page\s+(\d+)\s*-{2,}$",
            stripped,
            re.IGNORECASE,
        )

        if page_match:
            if current_page is not None:
                pages.append(
                    {
                        "pdf_page": current_page,
                        "text": "\n".join(current_lines),
                    }
                )

            current_page = int(page_match.group(1))
            current_lines = []
            continue

        current_lines.append(line)

    if current_page is not None:
        pages.append(
            {
                "pdf_page": current_page,
                "text": "\n".join(current_lines),
            }
        )

    return pages


def build_original_page_to_pdf_page_map(text: str):
    """
    Builds a map from original source visible page labels to actual
    combined-PDF pages.

    Only counts standalone labels like:
    Page 1
    Page 5

    Skips labels like:
    Page 5 of 127

    Mapping begins only after:
    Original Source Medical Records Converted to Text
    """

    anchor = "original source medical records converted to text"
    pages = split_text_pages(text)

    original_section_started = False
    page_map = {}

    for page in pages:
        pdf_page = page["pdf_page"]
        page_text = page["text"] or ""

        if not original_section_started:
            if anchor in page_text.lower():
                original_section_started = True
            else:
                continue

        lines = page_text.splitlines()

        for line in lines:
            stripped = line.strip()

            # Remove common icon/symbol before Page label.
            stripped = re.sub(r"^[^\w]*", "", stripped)

            # Match ONLY standalone "Page 5".
            # This intentionally does NOT match "Page 5 of 127".
            label_match = re.fullmatch(
                r"Page\s+(\d{1,5})",
                stripped,
                flags=re.IGNORECASE,
            )

            if not label_match:
                continue

            try:
                original_page = int(label_match.group(1))
            except Exception:
                continue

            if original_page not in page_map:
                page_map[original_page] = pdf_page

    return page_map


def find_original_source_start_page(text: str):
    page_map = build_original_page_to_pdf_page_map(text)

    return page_map.get(1)


def _make_summary_item(
    *,
    index: int,
    title: str,
    citation: str,
    original_summary: str,
    qc_summary: str,
    pdf_page,
):
    page = extract_page(citation)

    title = clean(title) or f"Summary {index}"
    citation = clean(citation)
    original_summary = clean_multiline(original_summary)
    qc_summary = clean_multiline(qc_summary)

    # If QC Summary is empty in the PDF, default it to Original Summary.
    # This gives the QC pane an editable starting point.
    if not qc_summary:
        qc_summary = original_summary

    return {
        "id": f"summary-{index}",
        "sectionId": f"SUMSEC{index:09d}",
        "section_id": f"SUMSEC{index:09d}",
        "sectionIndex": index,
        "section_index": index,

        "title": title,
        "linkedText": title,
        "citation": citation,

        "originalSummary": original_summary,
        "original_summary": original_summary,

        "qcSummary": qc_summary,
        "qc_summary": qc_summary,

        # Display-only original citation page, e.g. p. 5
        "page": page,
        "pageStart": page,
        "pageEnd": page,
        "page_start": page,
        "page_end": page,

        # Actual combined PDF page where this summary/title appears
        "pdfPage": pdf_page,
        "pdf_page": pdf_page,
        "summaryPdfPage": pdf_page,
        "summary_pdf_page": pdf_page,

        "status": "available",
    }


def _parse_labeled_summary_blocks(text: str):
    """
    Parses repeated labeled blocks like:

    Title:
    Citation:
    Original Summary:
    QC Summary:

    This is additive. If the PDF does not use these labels cleanly,
    parse_summary_outline falls back to the existing title/citation parser.
    """

    pages = split_text_pages(text)
    if not pages:
        pages = [{"pdf_page": None, "text": text or ""}]

    items = []
    current = None
    current_field = None

    def flush_current():
        nonlocal current

        if not current:
            return

        title = current.get("title", "")
        citation = current.get("citation", "")
        original_summary = current.get("original_summary", "")
        qc_summary = current.get("qc_summary", "")
        pdf_page = current.get("pdf_page")

        # Avoid creating junk records that have no meaningful fields.
        if not any(
            clean_multiline(value)
            for value in [title, citation, original_summary, qc_summary]
        ):
            current = None
            return

        items.append(
            _make_summary_item(
                index=len(items) + 1,
                title=title,
                citation=citation,
                original_summary=original_summary,
                qc_summary=qc_summary,
                pdf_page=pdf_page,
            )
        )

        current = None

    for page in pages:
        pdf_page = page.get("pdf_page")
        page_text = page.get("text") or ""

        for line in page_text.splitlines():
            stripped = line.strip()

            if not stripped:
                if current and current_field:
                    current[current_field] = (
                        current.get(current_field, "") + "\n"
                    )
                continue

            label_match = FIELD_LABEL_PATTERN.match(stripped)

            if label_match:
                label = label_match.group(1).lower()
                value = label_match.group(2) or ""

                if label == "title":
                    flush_current()
                    current = {
                        "title": value,
                        "citation": "",
                        "original_summary": "",
                        "qc_summary": "",
                        "pdf_page": pdf_page,
                    }
                    current_field = "title"
                    continue

                if current is None:
                    current = {
                        "title": "",
                        "citation": "",
                        "original_summary": "",
                        "qc_summary": "",
                        "pdf_page": pdf_page,
                    }

                if label == "citation":
                    current_field = "citation"
                elif label == "original summary":
                    current_field = "original_summary"
                elif label == "qc summary":
                    current_field = "qc_summary"
                else:
                    current_field = None

                if current_field:
                    existing = current.get(current_field, "")
                    current[current_field] = (
                        f"{existing}\n{value}".strip()
                        if existing
                        else value
                    )

                continue

            if current and current_field:
                existing = current.get(current_field, "")
                current[current_field] = (
                    f"{existing}\n{stripped}".strip()
                    if existing
                    else stripped
                )

    flush_current()

    # Only trust labeled parsing if it found real Summary fields.
    meaningful_items = [
        item
        for item in items
        if item.get("title")
        and (
            item.get("citation")
            or item.get("originalSummary")
            or item.get("qcSummary")
        )
    ]

    return meaningful_items


def _parse_legacy_summary_outline(text: str):
    """
    Existing parser behavior:
    - title line looks like: 1: Emergency Department Visit
    - citation line starts with YYYY/MM/DD
    - following lines become Original Summary and QC Summary
    """

    lines = (text or "").splitlines()

    items = []

    current = None
    summary_lines = []
    current_pdf_page = None

    for line in lines:
        stripped = line.strip()

        pdf_page_match = re.match(
            r"^-{2,}\s*Page\s+(\d+)\s*-{2,}$",
            stripped,
            re.IGNORECASE,
        )

        if pdf_page_match:
            current_pdf_page = int(pdf_page_match.group(1))
            continue

        title_match = TITLE_PATTERN.match(stripped)

        if title_match:
            if current:
                current["originalSummary"] = clean(
                    "\n".join(summary_lines)
                )
                current["original_summary"] = current["originalSummary"]
                current["qcSummary"] = current["originalSummary"]
                current["qc_summary"] = current["qcSummary"]
                items.append(current)

            title = stripped
            index = len(items) + 1

            current = {
                "id": f"summary-{index}",
                "sectionId": f"SUMSEC{index:09d}",
                "section_id": f"SUMSEC{index:09d}",
                "sectionIndex": index,
                "section_index": index,

                "title": title,
                "linkedText": title,
                "citation": "",

                "originalSummary": "",
                "original_summary": "",
                "qcSummary": "",
                "qc_summary": "",

                # Display-only original citation page, e.g. p. 5
                "page": None,
                "pageStart": None,
                "pageEnd": None,
                "page_start": None,
                "page_end": None,

                # Actual combined PDF page where this title appears
                "pdfPage": current_pdf_page,
                "pdf_page": current_pdf_page,
                "summaryPdfPage": current_pdf_page,
                "summary_pdf_page": current_pdf_page,

                "status": "available",
            }

            summary_lines = []
            continue

        if not current:
            continue

        if (
            not current["citation"]
            and re.match(r"^\d{4}/\d{2}/\d{2}", stripped)
        ):
            current["citation"] = stripped

            page = extract_page(stripped)

            current["page"] = page
            current["pageStart"] = page
            current["pageEnd"] = page
            current["page_start"] = page
            current["page_end"] = page

            continue

        if stripped.startswith("Page "):
            continue

        if stripped.startswith("----- PAGE"):
            continue

        if stripped.startswith("--- Page"):
            continue

        if stripped in {"$Ó", "$Ô"}:
            continue

        summary_lines.append(stripped)

    if current:
        current["originalSummary"] = clean(
            "\n".join(summary_lines)
        )
        current["original_summary"] = current["originalSummary"]
        current["qcSummary"] = current["originalSummary"]
        current["qc_summary"] = current["qcSummary"]
        items.append(current)

    return items


def parse_summary_outline(text: str):
    """
    Main parser used by Summaries.

    First tries structured labels:
      Title / Citation / Original Summary / QC Summary

    Falls back to existing legacy parser:
      1: Title
      YYYY/MM/DD citation line
      summary body
    """

    labeled_items = _parse_labeled_summary_blocks(text)

    if labeled_items:
        return labeled_items

    return _parse_legacy_summary_outline(text)


def build_summary_extract_payload(
    *,
    text: str,
    doc_id: str,
    source_pdf_name: str = "",
    native_pdf_path: str = "",
    text_path: str = "",
    workspace: str = "summaries",
):
    """
    Builds the structured JSON payload that will be saved beside the text file.

    This does not replace the original PDF.
    It only creates Summaries pane data.
    """

    sections = parse_summary_outline(text)

    if not sections and clean_multiline(text):
        sections = [
            _make_summary_item(
                index=1,
                title="Unparsed Summary",
                citation="",
                original_summary=text,
                qc_summary="",
                pdf_page=None,
            )
        ]

    return {
        "workspace": workspace,
        "doc_id": doc_id,
        "source_pdf_name": source_pdf_name,
        "native_pdf_path": native_pdf_path,
        "text_path": text_path,
        "extraction_status": "completed" if clean_multiline(text) else "empty_text",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "section_count": len(sections),
        "sections": sections,
    }