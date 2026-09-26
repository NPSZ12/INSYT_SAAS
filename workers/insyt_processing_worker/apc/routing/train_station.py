from __future__ import annotations

from typing import Any

from ..db import LedgerDB
from ..util import json_dumps, utc_now
from .file_type_registry import resolve_file_route


def route_train_station_files(
    *,
    db: LedgerDB,
    job_id: str,
) -> dict[str, Any]:
    rows = db.query(
        """
        SELECT
            file_id,
            original_path,
            normalized_path,
            extension,
            is_container
        FROM file_processing_metrics
        WHERE job_id=?
        ORDER BY normalized_path, file_id
        """,
        (job_id,),
    )

    continue_count = 0
    train_station_count = 0
    container_count = 0

    train_station_files: list[dict[str, Any]] = []

    for row in rows:
        #
        # Container/workbook parents have already served their
        # purpose in expansion. They are support records rather
        # than downstream primary documents.
        #
        if bool(row["is_container"]):
            container_count += 1
            continue

        route = resolve_file_route(
            extension=row["extension"],
            original_path=row["original_path"],
        )

        route_payload = {
            **route,
            "routed_at": utc_now(),
        }

        db.execute(
            """
            UPDATE file_processing_metrics
            SET
                stage_status_json=json_patch(
                    coalesce(stage_status_json, '{}'),
                    ?
                ),
                updated_at=?
            WHERE file_id=?
              AND job_id=?
            """,
            (
                json_dumps(
                    {
                        "file_routing": (
                            route_payload
                        )
                    }
                ),
                utc_now(),
                row["file_id"],
                job_id,
            ),
        )

        if route["status"] == "train_station":
            train_station_count += 1

            train_station_files.append(
                {
                    "file_id": str(
                        row["file_id"] or ""
                    ),
                    "original_path": str(
                        row["original_path"] or ""
                    ),
                    "extension": str(
                        route["extension"] or ""
                    ),
                    "reason": str(
                        route["reason"] or ""
                    ),
                }
            )

        else:
            continue_count += 1

    return {
        "registry_version": "1",
        "files_examined": (
            continue_count
            + train_station_count
        ),
        "continue_count": continue_count,
        "train_station_count": (
            train_station_count
        ),
        "container_support_count": (
            container_count
        ),
        "train_station_files": (
            train_station_files
        ),
    }
