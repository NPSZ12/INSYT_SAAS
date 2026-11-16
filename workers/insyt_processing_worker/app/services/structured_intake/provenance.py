from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from apc.db import LedgerDB
from apc.util import json_dumps, utc_now


def apply_structured_json_provenance(
    *,
    db: LedgerDB,
    job_id: str,
    staging_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """
    Enrich only JSON-normalized CSV working artifacts.

    Existing CSV files are untouched.

    Provenance is merged into stage_status_json via SQLite
    json_patch so existing stage metadata is preserved.
    """

    staging_dir = Path(
        staging_dir
    ).resolve()

    manifest_path = Path(
        manifest_path
    ).resolve()


    if not manifest_path.exists():
        return {
            "matched_count": 0,
            "updated_count": 0,
            "missing_count": 0,
        }


    payload = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )


    packages = (
        payload.get("packages")
        or []
    )


    matched_count = 0
    updated_count = 0
    missing_count = 0


    for package in packages:

        if not isinstance(
            package,
            dict,
        ):
            continue


        # Native JSON: attach lineage to the original
        # inventory file, never to a generated CSV.
        if package.get("status") == "native_deferred":
            native_name = str(
                package.get("source_filename") or ""
            ).strip()
            native_path = Path(
                str(package.get("original_source_path") or "")
            ).resolve()

            if (
                native_path.parent != staging_dir
                or native_path.name != native_name
                or native_path.suffix.lower()
                not in {".json", ".jsonl", ".ndjson"}
            ):
                raise ValueError(
                    "Native JSON provenance path is invalid."
                )

            rows = db.query(
                """
                SELECT file_id
                FROM file_processing_metrics
                WHERE job_id=?
                  AND (
                      original_path=?
                      OR normalized_path=?
                  )
                """,
                (
                    job_id,
                    str(native_path),
                    native_name,
                ),
            )

            if not rows:
                missing_count += 1
                continue

            matched_count += len(rows)

            structured_payload = {
                "structured_source": {
                    "source_family": "structured",
                    "source_format": "json",
                    "source_extension":
                        native_path.suffix.lower().lstrip("."),
                    "source_profile": str(
                        package.get("source_profile") or "plain"
                    ),
                    "original_json_filename": native_name,
                    "original_json_path": str(native_path),
                    "package_id": str(
                        package.get("package_id") or ""
                    ),
                    "package_count": int(
                        package.get("package_count") or 1
                    ),
                    "record_count": int(
                        package.get("record_count") or 0
                    ),
                    "adapter": "json_native",
                    "csv_generation_status": "not_started",
                }
            }

            for row in rows:
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET
                        updated_at=?,
                        stage_status_json=json_patch(
                            coalesce(stage_status_json, '{}'),
                            ?
                        )
                    WHERE job_id=? AND file_id=?
                    """,
                    (
                        utc_now(),
                        json_dumps(structured_payload),
                        job_id,
                        row["file_id"],
                    ),
                )
                updated_count += 1

            continue

        if (
            package.get("status")
            != "normalized"
        ):
            continue


        normalized_filename = str(
            package.get(
                "normalized_filename"
            )
            or ""
        ).strip()


        if not normalized_filename:
            continue


        normalized_path = (
            staging_dir
            / normalized_filename
        ).resolve()


        rows = db.query(
            """
            SELECT
                file_id,
                original_path,
                normalized_path,
                stage_status_json
            FROM file_processing_metrics
            WHERE job_id=?
              AND (
                    original_path=?
                    OR normalized_path=?
                  )
            """,
            (
                job_id,
                str(
                    normalized_path
                ),
                normalized_filename,
            ),
        )


        if not rows:
            missing_count += 1
            continue


        matched_count += len(
            rows
        )


        structured_payload = {
            "structured_source": {
                "source_family":
                    "structured",

                "source_format":
                    "json",

                "source_profile":
                    str(
                        package.get(
                            "source_profile"
                        )
                        or "plain"
                    ),

                "original_json_filename":
                    str(
                        package.get(
                            "source_filename"
                        )
                        or ""
                    ),

                "original_json_path":
                    str(
                        package.get(
                            "original_source_path"
                        )
                        or ""
                    ),

                "child_number": int(
                    package.get("child_number") or 1
                ),

                "source_record_start": int(
                    package.get("source_record_start") or 0
                ),

                "source_record_end": int(
                    package.get("source_record_end") or 0
                ),

                "source_total_record_count": int(
                    package.get("source_total_record_count")
                    or package.get("record_count")
                    or 0
                ),

                "package_id":
                    str(
                        package.get(
                            "package_id"
                        )
                        or ""
                    ),

                "package_count":
                    int(
                        package.get(
                            "package_count"
                        )
                        or 1
                    ),

                "record_count":
                    int(
                        package.get(
                            "record_count"
                        )
                        or 0
                    ),

                "normalized_format":
                    "csv",

                "normalized_filename":
                    normalized_filename,

                "adapter":
                    (
                        f"json_"
                        f"{str(package.get('source_profile') or 'plain')}"
                    ),
            }
        }


        for row in rows:

            db.execute(
                """
                UPDATE file_processing_metrics
                SET
                    updated_at=?,
                    stage_status_json=json_patch(
                        coalesce(
                            stage_status_json,
                            '{}'
                        ),
                        ?
                    )
                WHERE file_id=?
                """,
                (
                    utc_now(),
                    json_dumps(
                        structured_payload
                    ),
                    row["file_id"],
                ),
            )

            updated_count += 1


    return {
        "matched_count":
            matched_count,

        "updated_count":
            updated_count,

        "missing_count":
            missing_count,
    }
