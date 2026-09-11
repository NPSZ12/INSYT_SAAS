from __future__ import annotations

from pathlib import Path
from ..processing_sets import refresh_job_population_counts

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now


def load_denist_hashes(db: LedgerDB, hash_file: str, source_name: str = "external", source_version: str | None = None) -> int:
    path = Path(hash_file)
    if not path.exists():
        raise FileNotFoundError(hash_file)
    now = utc_now()
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip().lower()
        if not value or value.startswith("#"):
            continue
        if len(value) == 32:
            hash_type = "md5"
        elif len(value) == 40:
            hash_type = "sha1"
        elif len(value) == 64:
            hash_type = "sha256"
        else:
            continue
        rows.append((value, hash_type, source_name, source_version, now))
    db.executemany(
        "INSERT OR REPLACE INTO denist_hash (hash_value, hash_type, source_name, source_version, created_at) VALUES (?,?,?,?,?)",
        rows,
    )
    return len(rows)


def run_denist(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    set_id: str | None = None,
) -> None:
    rows = db.query(
        """
        SELECT
            f.file_id,
            f.md5,
            f.sha1,
            f.sha256
        FROM file_processing_metrics f
        WHERE f.job_id=?
          AND f.is_container=0
          AND (
                ? IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM processing_set_file psf
                    WHERE psf.file_id=f.file_id
                      AND psf.set_id=?
                )
          )
        ORDER BY f.normalized_path, f.file_id
        """,
        (
            job_id,
            set_id,
            set_id,
        ),
    )

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        "denist",
        "hashset-denist",
    ) as stage:
        stage.metrics.files_in = len(rows)
        stage.metrics.documents_in = len(rows)

        hits = 0

        for row in rows:
            matches = False

            for hash_value in (
                row["md5"],
                row["sha1"],
                row["sha256"],
            ):
                if not hash_value:
                    continue

                if db.scalar(
                    """
                    SELECT 1
                    FROM denist_hash
                    WHERE hash_value=?
                    LIMIT 1
                    """,
                    (hash_value.lower(),),
                ):
                    matches = True
                    break

            if matches:
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET is_denisted=1,
                        updated_at=?
                    WHERE file_id=?
                    """,
                    (
                        utc_now(),
                        row["file_id"],
                    ),
                )

                hits += 1

        stage.metrics.files_out = len(rows) - hits
        stage.metrics.documents_out = len(rows) - hits

        stage.metrics.extra.update(
            {
                "processing_set_id": set_id,
                "denist_hits": hits,
            }
        )

        refresh_job_population_counts(
            db=db,
            job_id=job_id,
        )
