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


def parse_summary_outline(text: str):
    lines = (text or "").splitlines()

    items = []

    current = None
    summary_lines = []

    for line in lines:
        stripped = line.strip()

        title_match = TITLE_PATTERN.match(stripped)

        if title_match:
            if current:
                current["originalSummary"] = clean(
                    "\n".join(summary_lines)
                )

                current["qcSummary"] = current[
                    "originalSummary"
                ]

                items.append(current)

            current = {
                "id": f"summary-{len(items) + 1}",
                "title": stripped,
                "citation": "",
                "originalSummary": "",
                "qcSummary": "",
                "page": None,
                "pageStart": None,
                "pageEnd": None,
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