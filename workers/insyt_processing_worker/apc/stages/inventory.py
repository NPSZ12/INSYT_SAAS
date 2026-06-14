from __future__ import annotations

import mimetypes
from pathlib import Path

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import normalize_path, new_id, utc_now


SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def run_inventory(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    input_dir: str,
    custodian_id: str | None = None,
) -> None:
    root = Path(input_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"input directory not found: {input_dir}")

    with StageRunner(db, settings, job_id, matter_id, "inventory", "local-filesystem-inventory") as stage:
        file_rows = []
        total_bytes = 0
        now = utc_now()
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name in SKIP_NAMES:
                continue
            stat = path.stat()
            rel_path = normalize_path(path, root)
            extension = path.suffix.lower().lstrip(".")
            mime_type, _ = mimetypes.guess_type(path.name)
            file_id = new_id("FILE")
            total_bytes += stat.st_size
            file_rows.append(
                {
                    "file_id": file_id,
                    "matter_id": matter_id,
                    "job_id": job_id,
                    "custodian_id": custodian_id,
                    "original_path": str(path),
                    "normalized_path": rel_path,
                    "extension": extension,
                    "mime_type": mime_type or "application/octet-stream",
                    "source_bytes": stat.st_size,
                    "expanded_bytes": stat.st_size,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        db.executemany(
            """
            INSERT INTO file_processing_metrics (
                file_id, matter_id, job_id, custodian_id, original_path, normalized_path,
                extension, mime_type, source_bytes, expanded_bytes, created_at, updated_at
            ) VALUES (:file_id,:matter_id,:job_id,:custodian_id,:original_path,:normalized_path,
                      :extension,:mime_type,:source_bytes,:expanded_bytes,:created_at,:updated_at)
            """,
            file_rows,
        )

        # Blob transaction proxy: one read/list-ish event per file at intake.
        if file_rows:
            stage.quote_cost("Storage", "Blob Write Operations", len(file_rows), "operations")

        stage.metrics.files_out = len(file_rows)
        stage.metrics.bytes_out = total_bytes
        stage.metrics.documents_out = len(file_rows)
        stage.metrics.extra.update({"input_dir": str(root), "custodian_id": custodian_id})

        db.execute(
            """
            UPDATE processing_job
            SET source_bytes=?, source_file_count=?, expanded_bytes=?, processed_bytes=?
            WHERE job_id=?
            """,
            (total_bytes, len(file_rows), total_bytes, total_bytes, job_id),
        )
