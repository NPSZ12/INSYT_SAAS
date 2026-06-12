from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now


def run_doc_id_assignment(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    prefix: str = "INSYT",
    start_number: int = 1,
    width: int = 9,
    suppress_duplicates: bool = True,
) -> None:
    where = "job_id=? AND is_container=0 AND is_denisted=0"
    params: tuple = (job_id,)
    if suppress_duplicates:
        where += " AND is_duplicate=0"
    rows = db.query(
        f"""
        SELECT file_id, family_id, normalized_path
        FROM file_processing_metrics
        WHERE {where}
        ORDER BY coalesce(family_id, file_id), normalized_path
        """,
        params,
    )
    with StageRunner(db, settings, job_id, matter_id, "doc_id_assignment", "sequential-doc-id") as stage:
        n = start_number
        for row in rows:
            doc_id = f"{prefix}{n:0{width}d}"
            db.execute(
                "UPDATE file_processing_metrics SET doc_id=?, updated_at=? WHERE file_id=?",
                (doc_id, utc_now(), row["file_id"]),
            )
            n += 1
        stage.metrics.files_in = len(rows)
        stage.metrics.files_out = len(rows)
        stage.metrics.documents_in = len(rows)
        stage.metrics.documents_out = len(rows)
        stage.metrics.extra.update({"prefix": prefix, "start_number": start_number, "assigned": len(rows)})
