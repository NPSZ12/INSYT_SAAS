from __future__ import annotations

import re

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now

def _highest_existing_doc_number(
    db: LedgerDB,
    matter_id: str,
    prefix: str,
) -> int:
    pattern = re.compile(
        rf"^{re.escape(prefix)}(\d+)$",
        re.IGNORECASE,
    )

    rows = db.query(
        """
        SELECT doc_id
        FROM file_processing_metrics
        WHERE matter_id=?
          AND doc_id IS NOT NULL
          AND doc_id <> ''
        """,
        (matter_id,),
    )

    highest = 0

    for row in rows:
        doc_id = str(row["doc_id"] or "").strip()
        match = pattern.match(doc_id)

        if not match:
            continue

        try:
            highest = max(highest, int(match.group(1)))
        except ValueError:
            continue

    return highest

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
        highest_existing = _highest_existing_doc_number(
            db=db,
            matter_id=matter_id,
            prefix=prefix,
        )

        effective_start_number = max(
            int(start_number or 1),
            highest_existing + 1,
        )

        n = effective_start_number

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
        stage.metrics.extra.update(
            {
                "prefix": prefix,
                "requested_start_number": start_number,
                "highest_existing": highest_existing,
                "effective_start_number": effective_start_number,
                "assigned": len(rows),
            }
        )
