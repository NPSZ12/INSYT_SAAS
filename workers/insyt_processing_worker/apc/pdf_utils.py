from __future__ import annotations

import os
import re
from pathlib import Path

_PAGE_RE = re.compile(rb"/Type\s*/Page(?!s)\b")
_ENCRYPT_RE = re.compile(rb"/Encrypt\b")
_TEXT_BLOCK_RE = re.compile(rb"BT\b.*?\bET", re.DOTALL)
_TEXT_SHOW_RE = re.compile(rb"\((?:\\.|[^\\)]){3,}\)\s*Tj|\[(?:.|\n|\r){3,}?\]\s*TJ", re.DOTALL)


def count_pdf_pages(path: Path) -> tuple[int, str]:
    """Return a lightweight PDF page count and confidence.

    This avoids external dependencies in the starter package. Production can replace
    this with pypdf/pdfium or Azure-native inspection. The regex works well for many
    normal PDFs and is much better than size-based guessing.
    """
    try:
        data = path.read_bytes()
    except Exception:
        return 0, "failed"
    if not data.startswith(b"%PDF") and b"%PDF" not in data[:1024]:
        return 0, "not_pdf"
    count = len(_PAGE_RE.findall(data))
    if count > 0:
        return count, "medium"
    # Fallback: some generated PDFs hide object syntax in object streams.
    return 1, "low"


def pdf_is_encrypted(path: Path) -> bool:
    try:
        data = path.read_bytes()[:1024 * 1024]
    except Exception:
        return False
    return bool(_ENCRYPT_RE.search(data))


def estimate_pdf_native_text_bytes(path: Path) -> tuple[int, str]:
    """
    Estimate whether a PDF has embedded/native text.

    This is intentionally a lightweight OCR-selection signal,
    not full PDF text extraction.

    Avoid running a DOTALL regex across an arbitrarily large
    binary PDF because malformed/compressed content can make
    that scan extremely expensive.
    """

    try:
        max_scan_bytes = max(
            1024 * 1024,
            int(
                os.getenv(
                    "APC_PDF_TEXT_SIGNAL_MAX_BYTES",
                    str(8 * 1024 * 1024),
                )
            ),
        )
    except Exception:
        max_scan_bytes = 8 * 1024 * 1024

    try:
        with path.open("rb") as fh:
            data = fh.read(max_scan_bytes)
    except Exception:
        return 0, "failed"

    if not data.startswith(b"%PDF") and b"%PDF" not in data[:1024]:
        return 0, "not_pdf"

    if _ENCRYPT_RE.search(data[:1024 * 1024]):
        return 0, "encrypted"

    #
    # Search only the bounded sample above.
    # Stop once enough native-text evidence is found;
    # this is an OCR eligibility signal, not an extraction pass.
    #
    textish = 0
    block_count = 0

    for block_match in _TEXT_BLOCK_RE.finditer(data):
        block_count += 1

        for match in _TEXT_SHOW_RE.finditer(
            block_match.group(0)
        ):
            textish += len(
                match.group(0)
            )

            if textish >= 4096:
                return (
                    textish,
                    "operator_signal",
                )

        if block_count >= 250:
            break

    if textish > 0:
        return (
            textish,
            "operator_signal",
        )

    if block_count > 0:
        return (
            0,
            "text_blocks_no_strings",
        )

    return (
        0,
        "no_text_operators",
    )
