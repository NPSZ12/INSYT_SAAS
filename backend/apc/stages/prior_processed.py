from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import json_dumps, utc_now


def run_prior_processed_duplicate_suppression(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
) -> None:
    """Suppress files already promoted in prior jobs for the same matter/project.

    This stage runs after hashing + within-job dedupe and before Doc ID assignment.

    If a current file's SHA256 was already promoted to review in a prior job for
    the same matter_id, mark the current file as a duplicate. Existing downstream
    filters then automatically skip Doc ID assignment and review promotion.
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

    prior_rows = db.query(
        """
        SELECT
          f.file_id,
          f.job_id,
          f.doc_id,
          f.normalized_path,
          f.native_output_path,
          f.text_output_path,
          f.sha256
        FROM file_processing_metrics f
        JOIN processing_job j ON j.job_id = f.job_id
        WHERE f.job_id <> ?
          AND j.matter_id = ?
          AND f.is_container=0
          AND f.is_denisted=0
          AND f.is_duplicate=0
          AND f.promoted_to_review=1
          AND f.doc_id IS NOT NULL
          AND f.sha256 IS NOT NULL
          AND f.sha256 <> ''
        ORDER BY j.completed_at DESC, j.created_at DESC, f.doc_id
        """,
        (job_id, matter_id),
    )

    prior_by_sha256: dict[str, dict] = {}

    for row in prior_rows:
        sha256 = str(row["sha256"] or "").strip().lower()
        if sha256 and sha256 not in prior_by_sha256:
            prior_by_sha256[sha256] = dict(row)

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        "prior_processed_duplicate_suppression",
        "sha256-project-history-suppression",
    ) as stage:
        suppressed = 0
        checked = 0
        examples: list[dict] = []

        for row in current_rows:
            checked += 1
            sha256 = str(row["sha256"] or "").strip().lower()

            prior = prior_by_sha256.get(sha256)
            if not prior:
                continue

            duplicate_note = {
                "prior_processed_duplicate": {
                    "status": "suppressed",
                    "reason": "sha256_already_promoted_in_prior_job",
                    "prior_job_id": prior.get("job_id"),
                    "prior_file_id": prior.get("file_id"),
                    "prior_doc_id": prior.get("doc_id"),
                    "prior_normalized_path": prior.get("normalized_path"),
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
                        "prior_job_id": prior.get("job_id"),
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