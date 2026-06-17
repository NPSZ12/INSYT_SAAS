from __future__ import annotations

from ..azure_layout import AzureRoutingConfig
from ..config import Settings
from ..db import LedgerDB
from ..doc_id_registry import reserve_doc_ids
from ..telemetry import StageRunner
from ..util import utc_now


def run_doc_id_assignment(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    routing: AzureRoutingConfig,
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

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        "doc_id_assignment",
        "sequential-doc-id",
    ) as stage:
        allocation = reserve_doc_ids(
            routing=routing,
            count=len(rows),
            prefix=prefix,
            width=width,
        )

        n = allocation.start_number

        for row in rows:
            doc_id = f"{prefix}{n:0{width}d}"

            db.execute(
                """
                UPDATE file_processing_metrics
                SET doc_id=?, updated_at=?
                WHERE file_id=?
                """,
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
                "registry_start_number": allocation.start_number,
                "registry_end_number": allocation.end_number,
                "previous_last_assigned_number": (
                    allocation.previous_last_assigned_number
                ),
                "new_last_assigned_number": (
                    allocation.new_last_assigned_number
                ),
                "registry_blob_path": allocation.registry_blob_path,
                "assigned": len(rows),
            }
        )
