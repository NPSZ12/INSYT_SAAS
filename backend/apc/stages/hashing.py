from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import utc_now


def _hash_file(path: Path) -> tuple[str, str, str]:
    md5 = hashlib.md5()  # nosec: eDiscovery dedupe compatibility, not password/security use.
    sha1 = hashlib.sha1()  # nosec: NSRL compatibility.
    sha256 = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha1.hexdigest(), sha256.hexdigest()


def run_hashing(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    rows = db.query("SELECT file_id, original_path, source_bytes FROM file_processing_metrics WHERE job_id=? AND is_container=0", (job_id,))
    with StageRunner(db, settings, job_id, matter_id, "hash", "local-hasher") as stage:
        stage.metrics.files_in = len(rows)
        stage.metrics.documents_in = len(rows)
        stage.metrics.bytes_in = sum(int(r["source_bytes"]) for r in rows)
        updated = 0
        exceptions = []
        for row in rows:
            path = Path(row["original_path"])
            try:
                md5, sha1, sha256 = _hash_file(path)
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET md5=?, sha1=?, sha256=?, updated_at=?
                    WHERE file_id=?
                    """,
                    (md5, sha1, sha256, utc_now(), row["file_id"]),
                )
                updated += 1
            except Exception as exc:  # noqa: BLE001 - keep pipeline moving and record exceptions.
                exceptions.append({"file_id": row["file_id"], "error": repr(exc)})
        stage.metrics.files_out = updated
        stage.metrics.documents_out = updated
        stage.metrics.bytes_out = stage.metrics.bytes_in
        stage.metrics.exceptions = len(exceptions)
        stage.metrics.extra["file_exceptions"] = exceptions[:50]
