from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apc.util import json_dumps, utc_now


def link_plain_json_families(
    *,
    db: Any,
    job_id: str,
    staging_dir: Path,
    manifest_path: Path,
) -> dict[str, int]:
    """
    Link inventoried plain JSON parents and normalized CSV children.

    Called after inventory and before processing-set creation.
    Does not assign Doc IDs or change unrelated document families.
    """
    staging_dir = Path(staging_dir).resolve()
    manifest_path = Path(manifest_path).resolve()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    packages = [
        item
        for item in manifest.get("packages", [])
        if (
            isinstance(item, dict)
            and item.get("status") == "normalized"
            and item.get("source_profile") in {
                "plain",
                "salesforce",
            }
        )
    ]

    if not packages:
        return {"parents": 0, "children": 0}

    groups: dict[str, list[dict[str, Any]]] = {}

    for package in packages:
        source_name = str(
            package.get("source_filename") or ""
        )

        if (
            not source_name
            or Path(source_name).name != source_name
            or Path(source_name).suffix.lower()
            not in {".json", ".jsonl", ".ndjson"}
        ):
            raise ValueError(
                "Invalid plain JSON source filename."
            )

        groups.setdefault(source_name, []).append(package)

    assignments = []

    # Validate every family before modifying any ledger rows.
    for source_name, children in sorted(groups.items()):
        native_path = (staging_dir / source_name).resolve()

        if (
            native_path.parent != staging_dir
            or not native_path.is_file()
        ):
            raise RuntimeError(
                f"Inventoried JSON native missing: {source_name}"
            )

        parent_rows = db.query(
            """
            SELECT file_id, extension, is_container,
                   parent_file_id
            FROM file_processing_metrics
            WHERE job_id=? AND original_path=?
            """,
            (job_id, str(native_path)),
        )

        if len(parent_rows) != 1:
            raise RuntimeError(
                f"Expected one native parent: {source_name}; "
                f"found {len(parent_rows)}"
            )

        parent = parent_rows[0]
        parent_id = str(parent["file_id"])

        if (
            str(parent["extension"] or "").lower().lstrip(".")
            not in {"json", "jsonl", "ndjson"}
            or bool(parent["is_container"])
            or parent["parent_file_id"]
        ):
            raise RuntimeError(
                "Native JSON parent has unexpected ledger state."
            )

        child_assignments = []
        child_numbers = set()
        child_ids = set()

        for package in children:
            child_number = int(package.get("child_number") or 0)

            if child_number < 1 or child_number in child_numbers:
                raise RuntimeError(
                    "Duplicate or invalid JSON child number."
                )

            child_numbers.add(child_number)

            csv_name = str(
                package.get("normalized_filename") or ""
            )

            if (
                not csv_name
                or Path(csv_name).name != csv_name
                or Path(csv_name).suffix.lower() != ".csv"
            ):
                raise ValueError(
                    "Invalid JSON normalized CSV filename."
                )

            csv_path = (staging_dir / csv_name).resolve()

            if (
                csv_path.parent != staging_dir
                or not csv_path.is_file()
            ):
                raise RuntimeError(
                    f"JSON child CSV missing: {csv_name}"
                )

            rows = db.query(
                """
                SELECT file_id, parent_file_id, extension
                FROM file_processing_metrics
                WHERE job_id=?
                  AND (
                      original_path=?
                      OR normalized_path=?
                  )
                """,
                (job_id, str(csv_path), csv_name),
            )

            if len(rows) != 1:
                raise RuntimeError(
                    f"Expected one CSV child: {csv_name}; "
                    f"found {len(rows)}"
                )

            child = rows[0]
            child_id = str(child["file_id"])

            if (
                child_id == parent_id
                or child_id in child_ids
                or str(child["extension"] or "").lower().lstrip(".")
                != "csv"
                or (
                    child["parent_file_id"]
                    and str(child["parent_file_id"]) != parent_id
                )
            ):
                raise RuntimeError(
                    "JSON child ledger relationship conflict."
                )

            child_ids.add(child_id)
            child_assignments.append(
                (child_id, child_number, package)
            )

        if child_numbers != set(range(1, len(children) + 1)):
            raise RuntimeError(
                "JSON child numbering is not contiguous."
            )

        assignments.append(
            (parent_id, source_name, child_assignments)
        )

    total_children = 0

    for parent_id, source_name, children in assignments:
        db.execute(
            """
            UPDATE file_processing_metrics
            SET is_container=1,
                stage_status_json=json_patch(
                    coalesce(stage_status_json, '{}'), ?
                ),
                updated_at=?
            WHERE job_id=? AND file_id=?
            """,
            (
                json_dumps({
                    "structured_json_parent": {
                        "source_filename": source_name,
                        "child_count": len(children),
                    }
                }),
                utc_now(),
                job_id,
                parent_id,
            ),
        )

        for child_id, child_number, package in children:
            db.execute(
                """
                UPDATE file_processing_metrics
                SET parent_file_id=?,
                    stage_status_json=json_patch(
                        coalesce(stage_status_json, '{}'), ?
                    ),
                    updated_at=?
                WHERE job_id=? AND file_id=?
                """,
                (
                    parent_id,
                    json_dumps({
                        "structured_json_child": {
                            "parent_file_id": parent_id,
                            "child_number": child_number,
                            "package_id": package.get("package_id"),
                            "source_record_start": int(
                                package.get("source_record_start") or 0
                            ),
                            "source_record_end": int(
                                package.get("source_record_end") or 0
                            ),
                        }
                    }),
                    utc_now(),
                    job_id,
                    child_id,
                ),
            )

            total_children += 1

    return {
        "parents": len(assignments),
        "children": total_children,
    }
