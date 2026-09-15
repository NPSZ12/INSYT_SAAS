from __future__ import annotations

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
    """Estimate whether a PDF has embedded/native text without external libs.

    This is not full extraction. It is a signal for OCR candidate selection.
    """
    try:
        data = path.read_bytes()
    except Exception:
        return 0, "failed"
    if not data.startswith(b"%PDF") and b"%PDF" not in data[:1024]:
        return 0, "not_pdf"
    if _ENCRYPT_RE.search(data[:1024 * 1024]):
        return 0, "encrypted"
    blocks = _TEXT_BLOCK_RE.findall(data)
    if not blocks:
        return 0, "no_text_operators"
    textish = 0
    for block in blocks[:500]:
        for match in _TEXT_SHOW_RE.findall(block):
            textish += len(match)
    if textish > 0:
        return textish, "operator_signal"
    return 0, "text_blocks_no_strings"
