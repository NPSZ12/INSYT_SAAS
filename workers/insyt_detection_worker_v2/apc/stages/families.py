from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import new_id, utc_now


CONTAINER_EXTENSIONS = {"zip", "pst", "ost", "msg", "eml", "mbox", "tar", "gz", "7z", "rar"}


def run_family_detection(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    """Assign provisional family IDs.

    v0.4 expands ZIP containers before this provisional family stage. This stage still emits
    family telemetry and creates a stable placeholder family_id for every reviewable
    item so downstream Doc ID and reports can be tested.
    """
    rows = db.query(
        """
        SELECT file_id, extension, is_denisted, is_duplicate
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0
        ORDER BY normalized_path
        """,
        (job_id,),
    )
    with StageRunner(db, settings, job_id, matter_id, "family_detection", "provisional-family-detector") as stage:
        reviewable = [r for r in rows if not r["is_denisted"] and not r["is_duplicate"]]
        family_count = 0
        container_count = 0
        for row in reviewable:
            family_id = new_id("FAM")
            if (row["extension"] or "").lower() in CONTAINER_EXTENSIONS:
                container_count += 1
            db.execute(
                "UPDATE file_processing_metrics SET family_id=?, updated_at=? WHERE file_id=?",
                (family_id, utc_now(), row["file_id"]),
            )
            family_count += 1
        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = len(reviewable)
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = len(reviewable)
        stage.metrics.extra.update(
            {
                "family_count": family_count,
                "container_candidates": container_count,
                "note": "v0.4 provisional family IDs after ZIP expansion; email/PST family logic remains in backlog",
            }
        )
