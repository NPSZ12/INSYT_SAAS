from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class WorksheetWorkUnit:
    unit_id: str
    start_row: int
    end_row: int
    start_offset: int
    end_offset: int
    row_count: int
    text_sha256: str
    text: str


def iter_worksheet_work_units(
    path: Path,
    *,
    max_chars: int = 32_000,
    max_rows: int = 500,
) -> Iterator[WorksheetWorkUnit]:
    """
    Stream deterministic worksheet chunks.

    Character offsets, line boundaries, and newline
    handling match the existing worksheet triage scanner.

    This module prepares work units only. It does not
    run detection or write checkpoints.
    """
    if max_chars < 1 or max_rows < 1:
        raise ValueError("Chunk limits must be positive.")

    parts: list[str] = []
    chunk_chars = 0
    chunk_rows = 0

    total_chars = 0
    total_rows = 0

    start_offset = 0
    start_row = 1
    index = 0

    with Path(path).open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        for line in handle:
            if not parts:
                start_offset = total_chars
                start_row = total_rows + 1

            parts.append(line)
            chunk_chars += len(line)
            chunk_rows += 1
            total_chars += len(line)
            total_rows += 1

            if (
                chunk_chars >= max_chars
                or chunk_rows >= max_rows
            ):
                index += 1
                text = "".join(parts)

                yield WorksheetWorkUnit(
                    unit_id=f"chunk-{index:06d}",
                    start_row=start_row,
                    end_row=total_rows,
                    start_offset=start_offset,
                    end_offset=total_chars,
                    row_count=chunk_rows,
                    text_sha256=hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                    text=text,
                )

                parts = []
                chunk_chars = 0
                chunk_rows = 0

        if parts:
            index += 1
            text = "".join(parts)

            yield WorksheetWorkUnit(
                unit_id=f"chunk-{index:06d}",
                start_row=start_row,
                end_row=total_rows,
                start_offset=start_offset,
                end_offset=total_chars,
                row_count=chunk_rows,
                text_sha256=hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                text=text,
            )