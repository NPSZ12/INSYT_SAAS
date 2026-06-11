import re


TITLE_PATTERN = re.compile(r"^(\d{1,4}:\s+.+)$")
PAGE_PATTERN = re.compile(r"\bp{1,2}\.\s*(\d+)", re.IGNORECASE)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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


def parse_summary_outline(text: str):
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
                current["qcSummary"] = current["originalSummary"]
                items.append(current)

            title = stripped

            current = {
                "id": f"summary-{len(items) + 1}",
                "title": title,
                "linkedText": title,
                "citation": "",
                "originalSummary": "",
                "qcSummary": "",

                # Display-only original citation page, e.g. p. 5
                "page": None,
                "pageStart": None,
                "pageEnd": None,

                # Actual combined PDF page where this title appears
                "pdfPage": current_pdf_page,
                "pdf_page": current_pdf_page,
                "summaryPdfPage": current_pdf_page,
                "summary_pdf_page": current_pdf_page,
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
        current["qcSummary"] = current["originalSummary"]
        items.append(current)

    return items