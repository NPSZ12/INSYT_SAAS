from __future__ import annotations

from typing import Any


class NativeJsonStagingIncomplete(RuntimeError):
    pass



def load_expected_native_json_doc_ids(
    *,
    db: Any,
    job_id: str,
) -> set[str]:
    """Read eligible native JSON inventory independently of provenance."""

    rows = db.query(
        """
        SELECT doc_id
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND LOWER(
              LTRIM(COALESCE(extension, ''), '.')
          ) IN ('json', 'jsonl', 'ndjson')
        """,
        (job_id,),
    )

    expected: set[str] = set()

    for row in rows:
        doc_id = str(row["doc_id"] or "").strip()
        if not doc_id or doc_id in expected:
            raise NativeJsonStagingIncomplete(
                "Native JSON inventory contains a missing "
                "or duplicate Doc ID."
            )
        expected.add(doc_id)

    return expected


def validate_native_json_staging(
    result: dict[str, Any],
    *,
    expected_doc_ids: set[str] | None = None,
) -> None:
    """Reject incomplete native JSON staging before Detection readiness."""

    if not isinstance(result, dict):
        raise NativeJsonStagingIncomplete(
            "Missing structured JSON staging result."
        )

    planned = int(result.get("planned_count") or 0)
    uploaded_count = int(result.get("uploaded_count") or 0)
    failed_count = int(result.get("failed_count") or 0)
    rows = result.get("uploaded")

    if (
        planned < 0
        or uploaded_count < 0
        or failed_count < 0
        or not isinstance(rows, list)
        or failed_count != 0
        or planned != uploaded_count
        or uploaded_count != len(rows)
    ):
        raise NativeJsonStagingIncomplete(
            "Native JSON staging was incomplete; "
            "manual Detection readiness is prohibited."
        )

    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            raise NativeJsonStagingIncomplete(
                "Invalid native JSON staging record."
            )

        doc_id = str(row.get("doc_id") or "").strip()
        native = str(
            row.get("native_staged_blob_path") or ""
        ).strip()
        text = str(
            row.get("text_staged_blob_path") or ""
        ).strip()
        extension = str(
            row.get("extension") or ""
        ).strip().lower().lstrip(".")

        if (
            not doc_id
            or doc_id in seen
            or not native.endswith(
                f"/structured/native/{doc_id}.{extension}"
            )
            or extension not in {"json", "jsonl", "ndjson"}
            or not text.endswith(
                f"/structured/text/{doc_id}.txt"
            )
            or row.get("status") != "uploaded"
        ):
            raise NativeJsonStagingIncomplete(
                "Native JSON staging identity or paths invalid."
            )

        seen.add(doc_id)

    if expected_doc_ids is not None:
        if (
            not isinstance(expected_doc_ids, set)
            or any(
                not isinstance(doc_id, str) or not doc_id.strip()
                for doc_id in expected_doc_ids
            )
            or seen != expected_doc_ids
        ):
            raise NativeJsonStagingIncomplete(
                "Staged native JSON Doc IDs do not exactly "
                "match the eligible APC inventory."
            )
