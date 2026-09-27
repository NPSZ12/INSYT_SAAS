from __future__ import annotations

import re
import time
from pathlib import Path

PDF_INSPECTION_MAX_SECONDS = 10.0


def _deadline() -> float:
    return (
        time.monotonic()
        + PDF_INSPECTION_MAX_SECONDS
    )


def _deadline_exceeded(
    deadline: float,
) -> bool:
    return (
        time.monotonic()
        >= deadline
    )

_PAGE_RE = re.compile(
    rb"/Type\s*/Page(?!s)\b"
)

_ENCRYPT_RE = re.compile(
    rb"/Encrypt\b"
)

_TEXT_BLOCK_RE = re.compile(
    rb"BT\b.*?\bET",
    re.DOTALL,
)

_TEXT_SHOW_RE = re.compile(
    rb"\((?:\\.|[^\\)]){3,}\)\s*Tj"
    rb"|\[(?:.|\n|\r){3,}?\]\s*TJ",
    re.DOTALL,
)


PDF_READ_CHUNK_BYTES = (
    256 * 1024
)

PDF_SCAN_OVERLAP_BYTES = 4096

PDF_ENCRYPT_SCAN_BYTES = (
    1024 * 1024
)

#
# Native-text inspection is only an OCR eligibility signal.
# It is intentionally bounded so a malformed or unusual PDF
# cannot hold the APC worker indefinitely.
#
PDF_NATIVE_TEXT_SCAN_MAX_BYTES = (
    32 * 1024 * 1024
)

PDF_NATIVE_TEXT_MAX_BLOCKS = 500


def _read_prefix(
    path: Path,
    max_bytes: int,
) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(
                max_bytes
            )
    except Exception:
        return b""


def _looks_like_pdf(
    path: Path,
) -> bool:
    prefix = _read_prefix(
        path,
        1024,
    )

    if not prefix:
        return False

    return (
        prefix.startswith(b"%PDF")
        or b"%PDF" in prefix
    )


def count_pdf_pages(
    path: Path,
) -> tuple[int, str]:
    """
    Return a lightweight PDF page count.

    The PDF is scanned incrementally rather than loaded
    entirely into memory.
    """

    if not _looks_like_pdf(path):
        return 0, "not_pdf"

    deadline = _deadline()

    count = 0
    carry = b""

    try:
        with path.open("rb") as stream:
            while True:
                if _deadline_exceeded(
                    deadline
                ):
                    return (
                        count if count > 0 else 0,
                        "timeout",
                    )

                chunk = stream.read(
                    PDF_READ_CHUNK_BYTES
                )

                if not chunk:
                    break

                carry_length = len(
                    carry
                )

                buffer = (
                    carry
                    + chunk
                )

                for match in (
                    _PAGE_RE.finditer(
                        buffer
                    )
                ):
                    if _deadline_exceeded(
                        deadline
                    ):
                        return (
                            count if count > 0 else 0,
                            "timeout",
                        )
                    #
                    # Do not recount a match contained
                    # entirely inside the overlap from the
                    # previous chunk.
                    #
                    if (
                        match.end()
                        > carry_length
                    ):
                        count += 1

                carry = buffer[
                    -PDF_SCAN_OVERLAP_BYTES:
                ]

    except Exception:
        return 0, "failed"

    if count > 0:
        return count, "medium"

    #
    # Some PDFs hide page dictionaries inside object streams.
    #
    return 1, "low"


def pdf_is_encrypted(
    path: Path,
) -> bool:
    data = _read_prefix(
        path,
        PDF_ENCRYPT_SCAN_BYTES,
    )

    if not data:
        return False

    return bool(
        _ENCRYPT_RE.search(
            data
        )
    )


def estimate_pdf_native_text_bytes(
    path: Path,
) -> tuple[int, str]:
    """
    Estimate whether a PDF contains embedded/native text.

    This is an OCR-selection signal, not final extraction.

    Inspection is intentionally bounded. A single PDF must
    never be able to monopolize the APC worker.
    """

    if not _looks_like_pdf(path):
        return 0, "not_pdf"

    prefix = _read_prefix(
        path,
        PDF_ENCRYPT_SCAN_BYTES,
    )

    if _ENCRYPT_RE.search(
        prefix
    ):
        return 0, "encrypted"

    deadline = _deadline()

    textish = 0
    block_count = 0
    bytes_scanned = 0
    carry = b""

    try:
        with path.open("rb") as stream:
            while (
                bytes_scanned
                < PDF_NATIVE_TEXT_SCAN_MAX_BYTES
            ):
                if _deadline_exceeded(
                    deadline
                ):
                    return (
                        textish,
                        "inspection_timeout",
                    )

                remaining = (
                    PDF_NATIVE_TEXT_SCAN_MAX_BYTES
                    - bytes_scanned
                )

                chunk = stream.read(
                    min(
                        PDF_READ_CHUNK_BYTES,
                        remaining,
                    )
                )

                if not chunk:
                    break

                bytes_scanned += len(
                    chunk
                )

                buffer = (
                    carry
                    + chunk
                )

                for block_match in (
                    _TEXT_BLOCK_RE.finditer(
                        buffer
                    )
                ):
                    if _deadline_exceeded(
                        deadline
                    ):
                        return (
                            textish,
                            "inspection_timeout",
                        )

                    block = (
                        block_match.group(0)
                    )

                    block_count += 1

                    for text_match in (
                        _TEXT_SHOW_RE.finditer(
                            block
                        )
                    ):
                        textish += len(
                            text_match.group(0)
                        )

                    if (
                        block_count
                        >= PDF_NATIVE_TEXT_MAX_BLOCKS
                    ):
                        break

                if (
                    textish > 0
                    or block_count
                    >= PDF_NATIVE_TEXT_MAX_BLOCKS
                ):
                    break

                carry = buffer[
                    -PDF_SCAN_OVERLAP_BYTES:
                ]

    except Exception:
        return 0, "failed"

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

    if (
        bytes_scanned
        >= PDF_NATIVE_TEXT_SCAN_MAX_BYTES
    ):
        return (
            0,
            "no_text_operators_bounded_scan",
        )

    return (
        0,
        "no_text_operators",
    )
