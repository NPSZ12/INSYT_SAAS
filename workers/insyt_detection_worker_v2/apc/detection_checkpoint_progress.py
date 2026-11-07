from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .worksheet_work_units import (
    iter_worksheet_work_units,
)


def verify_detection_checkpoint_progress(
    *,
    worksheets: Iterable[dict[str, Any]],
    max_chars: int,
    max_rows: int,
) -> dict[str, Any]:
    """
    Verify the complete selected worksheet population.

    Each worksheet entry must contain:
      doc_id: original selected document ID
      path: local staged worksheet text path
      executor: existing document-scoped checkpoint executor

    Executor.load_completed verifies checkpoint identity,
    rule/source fingerprint and durable result artifact.

    Never use job status or checkpoint blob counts as
    evidence of completed detection work.
    """
    if (
        type(max_chars) is not int
        or max_chars < 1
        or type(max_rows) is not int
        or max_rows < 1
    ):
        raise ValueError("Invalid worksheet chunk boundaries.")

    population = list(worksheets)

    if not population:
        raise ValueError("Worksheet population is empty.")

    completed = 0
    total = 0
    seen_docs: set[str] = set()

    for worksheet in population:
        if not isinstance(worksheet, dict):
            raise TypeError("Invalid worksheet population entry.")

        doc_id = str(
            worksheet.get("doc_id") or ""
        ).strip()

        if not doc_id or doc_id in seen_docs:
            raise ValueError(
                "Missing or duplicate worksheet document ID."
            )

        seen_docs.add(doc_id)

        path = Path(worksheet["path"])
        executor = worksheet["executor"]

        if not path.is_file():
            raise FileNotFoundError(
                f"Worksheet source unavailable: {doc_id}"
            )

        load_completed = getattr(
            executor,
            "load_completed",
            None,
        )

        if not callable(load_completed):
            raise TypeError(
                "Worksheet executor lacks checkpoint restoration."
            )

        document_units = 0

        for unit in iter_worksheet_work_units(
            path,
            max_chars=max_chars,
            max_rows=max_rows,
        ):
            document_units += 1
            total += 1

            # This must return only a verified durable result.
            result = load_completed(unit)

            if result is None:
                continue

            if not isinstance(result, dict):
                raise ValueError(
                    "Invalid verified checkpoint result."
                )

            completed += 1

        if document_units == 0:
            raise ValueError(
                f"Worksheet has no work units: {doc_id}"
            )

    if total == 0 or completed > total:
        raise RuntimeError(
            "Invalid detection checkpoint population."
        )

    return {
        "checkpoint_verified": True,
        "completed_units": completed,
        "total_units": total,
        "job_complete": completed == total,
    }