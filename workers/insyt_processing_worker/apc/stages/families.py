from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import new_id, utc_now


CONTAINER_EXTENSIONS = {"zip", "pst", "ost", "msg", "eml", "mbox", "tar", "gz", "7z", "rar"}


def run_family_detection(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
) -> None:
    """
    Assign provisional family IDs while preserving any family
    relationship already established during container expansion.

    MSG attachment expansion may create a shared family_id for the
    parent email and its child attachments before this stage runs.
    Those existing IDs must not be overwritten.
    """

    rows = db.query(
        """
        SELECT
            file_id,
            extension,
            is_denisted,
            is_duplicate,
            family_id
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
        ORDER BY normalized_path
        """,
        (
            job_id,
        ),
    )

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        "family_detection",
        "provisional-family-detector",
    ) as stage:
        reviewable = [
            row
            for row in rows
            if (
                not row["is_denisted"]
                and not row["is_duplicate"]
            )
        ]

        family_count = 0
        container_count = 0
        preserved_family_count = 0
        new_family_count = 0

        for row in reviewable:
            existing_family_id = str(
                row["family_id"]
                or ""
            ).strip()

            if existing_family_id:
                family_id = existing_family_id
                preserved_family_count += 1
            else:
                family_id = new_id(
                    "FAM"
                )
                new_family_count += 1

            if (
                row["extension"]
                or ""
            ).lower() in CONTAINER_EXTENSIONS:
                container_count += 1

            db.execute(
                """
                UPDATE file_processing_metrics
                SET
                    family_id=?,
                    updated_at=?
                WHERE file_id=?
                """,
                (
                    family_id,
                    utc_now(),
                    row["file_id"],
                ),
            )

            family_count += 1

        stage.metrics.files_in = len(
            rows
        )

        stage.metrics.files_out = len(
            reviewable
        )

        stage.metrics.documents_in = len(
            rows
        )

        stage.metrics.documents_out = len(
            reviewable
        )

        stage.metrics.extra.update(
            {
                "family_count": (
                    family_count
                ),
                "preserved_family_count": (
                    preserved_family_count
                ),
                "new_family_count": (
                    new_family_count
                ),
                "container_candidates": (
                    container_count
                ),
                "note": (
                    "Preserves family IDs established during "
                    "container/email expansion; assigns new "
                    "family IDs only when none already exists."
                ),
            }
        )
