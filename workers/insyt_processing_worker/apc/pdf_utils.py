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
        with path.open("rb") as fh:
            data = fh.read(1024 * 1024)
    except Exception:
        return False

    return b"/Encrypt" in data


def estimate_pdf_native_text_bytes(path: Path) -> tuple[int, str]:
    """
    Estimate whether a PDF contains native text operators.

    This is only an OCR-selection signal. It deliberately avoids
    regex parsing across arbitrary PDF binary streams because some
    PDFs can cause extremely expensive backtracking.
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

    if b"/Encrypt" in data[:1024 * 1024]:
        return 0, "encrypted"

    #
    # Lightweight linear byte scanning only.
    #
    # BT/ET delimit PDF text objects.
    # Tj/TJ are common text-showing operators.
    #
    bt_count = data.count(b"BT")
    et_count = data.count(b"ET")

    if bt_count == 0 or et_count == 0:
        return 0, "no_text_operators"

    tj_count = data.count(b"Tj")
    tj_array_count = data.count(b"TJ")
    text_operator_count = tj_count + tj_array_count

    if text_operator_count == 0:
        return 0, "text_blocks_no_strings"

    #
    # This is intentionally an estimate, not extracted text length.
    # Give each discovered text-show operator a conservative amount
    # of signal weight while bounding the result.
    #
    estimated_text_bytes = min(
        text_operator_count * 64,
        1024 * 1024,
    )

    return (
        max(estimated_text_bytes, 1),
        "operator_signal",
    )
