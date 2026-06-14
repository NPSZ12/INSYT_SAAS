from __future__ import annotations

from typing import Any

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import json_dumps, utc_now


def _normalize_prior_hash_index(
    prior_processed_index: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not prior_processed_index:
        return {}

    items = prior_processed_index.get("items") or {}

    if isinstance(items, dict):
        return {
            str(sha256).strip().lower(): dict(record or {})
            for sha256, record in items.items()
            if str(sha256).strip()
        }

    if isinstance(items, list):
        normalized: dict[str, dict[str, Any]] = {}

        for record in items:
            if not isinstance(record, dict):
                continue

            sha256 = str(record.get("sha256") or "").strip().lower()
            if sha256 and sha256 not in normalized:
                normalized[sha256] = dict(record)

        return normalized

    return {}


def run_prior_processed_duplicate_suppression(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    prior_processed_index: dict[str, Any] | None = None,
) -> None:
    """Suppress files already promoted in prior jobs for the same project.

    This stage runs after hashing + within-job dedupe and before Doc ID assignment.

    If a current file's SHA256 already exists in the Azure project-level processed
    hash index, mark the current file as a duplicate. Existing downstream filters
    then automatically skip Doc ID assignment and review promotion.
    """

    current_rows = db.query(
        """
        SELECT file_id, normalized_path, sha256, stage_status_json
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND sha256 IS NOT NULL
          AND sha256 <> ''
        ORDER BY normalized_path
        """,
        (job_id,),
    )

    prior_by_sha256 = _normalize_prior_hash_index(prior_processed_index)

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        "prior_processed_duplicate_suppression",
        "azure-sha256-project-history-suppression",
    ) as stage:
        suppressed = 0
        checked = 0
        examples: list[dict[str, Any]] = []

        for row in current_rows:
            checked += 1
            sha256 = str(row["sha256"] or "").strip().lower()

            prior = prior_by_sha256.get(sha256)
            if not prior:
                continue

            duplicate_note = {
                "prior_processed_duplicate": {
                    "status": "suppressed",
                    "reason": "sha256_already_exists_in_project_hash_index",
                    "prior_job_id": prior.get("first_processed_job_id")
                    or prior.get("job_id"),
                    "prior_doc_id": prior.get("doc_id"),
                    "prior_original_name": prior.get("original_name")
                    or prior.get("normalized_path"),
                    "prior_native_output_path": prior.get("native_output_path"),
                    "prior_text_output_path": prior.get("text_output_path"),
                    "sha256": sha256,
                }
            }

            db.execute(
                """
                UPDATE file_processing_metrics
                SET is_duplicate=1,
                    duplicate_of_file_id=?,
                    updated_at=?,
                    stage_status_json=json_patch(stage_status_json, ?)
                WHERE file_id=?
                """,
                (
                    prior.get("file_id"),
                    utc_now(),
                    json_dumps(duplicate_note),
                    row["file_id"],
                ),
            )

            suppressed += 1

            if len(examples) < 25:
                examples.append(
                    {
                        "file_id": row["file_id"],
                        "normalized_path": row["normalized_path"],
                        "sha256": sha256,
                        "prior_job_id": prior.get("first_processed_job_id")
                        or prior.get("job_id"),
                        "prior_doc_id": prior.get("doc_id"),
                    }
                )

        stage.metrics.files_in = len(current_rows)
        stage.metrics.files_out = max(0, len(current_rows) - suppressed)
        stage.metrics.documents_in = len(current_rows)
        stage.metrics.documents_out = max(0, len(current_rows) - suppressed)
        stage.metrics.extra.update(
            {
                "checked_current_files": checked,
                "prior_index_size": len(prior_by_sha256),
                "suppressed_prior_processed_duplicates": suppressed,
                "examples": examples,
            }
        )