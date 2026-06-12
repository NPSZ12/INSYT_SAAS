from __future__ import annotations

from collections import defaultdict

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now


def run_dedupe(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    rows = db.query(
        """
        SELECT file_id, sha256, source_bytes, normalized_path
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND is_denisted=0
        ORDER BY sha256, normalized_path
        """,
        (job_id,),
    )
    with StageRunner(db, settings, job_id, matter_id, "dedupe", "exact-sha256-dedupe") as stage:
        stage.metrics.files_in = len(rows)
        stage.metrics.documents_in = len(rows)
        stage.metrics.bytes_in = sum(int(r["source_bytes"]) for r in rows)
        groups: dict[str, list] = defaultdict(list)
        for row in rows:
            if row["sha256"]:
                groups[row["sha256"]].append(row)

        duplicate_count = 0
        duplicate_bytes = 0
        group_count = 0
        for _hash, members in groups.items():
            if len(members) <= 1:
                continue
            group_count += 1
            canonical = members[0]
            for dup in members[1:]:
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET is_duplicate=1, duplicate_of_file_id=?, updated_at=?
                    WHERE file_id=?
                    """,
                    (canonical["file_id"], utc_now(), dup["file_id"]),
                )
                duplicate_count += 1
                duplicate_bytes += int(dup["source_bytes"])

        unique_count = len(rows) - duplicate_count
        stage.metrics.files_out = unique_count
        stage.metrics.documents_out = unique_count
        stage.metrics.bytes_out = stage.metrics.bytes_in - duplicate_bytes
        stage.metrics.extra.update(
            {
                "duplicate_groups": group_count,
                "duplicate_files": duplicate_count,
                "duplicate_bytes_suppressed": duplicate_bytes,
            }
        )
        db.execute(
            """
            UPDATE processing_job
            SET duplicate_doc_count=?, unique_doc_count=?
            WHERE job_id=?
            """,
            (duplicate_count, unique_count, job_id),
        )
