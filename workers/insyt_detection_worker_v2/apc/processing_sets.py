from __future__ import annotations

import json

from typing import Any

from .db import LedgerDB
from .util import utc_now


ALLOWED_PROCESSING_SET_SIZES = {
    100,
    250,
    500,
    1000,
}


def normalize_processing_set_size(
    set_size: int,
) -> int:
    value = int(set_size)

    if value <= 0:
        raise ValueError(
            "Processing set size must be greater than zero."
        )

    return value

def _stage_status(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if not value:
        return {}

    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _workbook_parent_file_id(row: Any) -> str:
    status = _stage_status(row["stage_status_json"])

    workbook_sheet = status.get("workbook_sheet") or {}

    if not isinstance(workbook_sheet, dict):
        return ""

    return str(
        workbook_sheet.get("original_workbook_file_id")
        or row["parent_file_id"]
        or ""
    ).strip()

def build_processing_sets(
    *,
    db: LedgerDB,
    job_id: str,
    matter_id: str,
    set_size: int,
) -> dict[str, Any]:
    resolved_set_size = normalize_processing_set_size(
        set_size
    )

    #
    # Load the entire post-expansion ledger because
    # workbook parents may be container records that
    # must accompany their worksheet children.
    #
    all_rows = db.query(
        """
        SELECT
            file_id,
            normalized_path,
            extension,
            is_container,
            is_denisted,
            is_duplicate,
            parent_file_id,
            stage_status_json
        FROM file_processing_metrics
        WHERE job_id=?
        ORDER BY normalized_path, file_id
        """,
        (job_id,),
    )

    rows_by_id = {
        str(row["file_id"]): row
        for row in all_rows
    }

    #
    # Only leaf records count toward the configured
    # processing-set population.
    #
    primary_rows = [
        row
        for row in all_rows
        if (
            not bool(
                row[
                    "is_container"
                ]
            )
            and not bool(
                row[
                    "is_denisted"
                ]
            )
            and not bool(
                row[
                    "is_duplicate"
                ]
            )
        )
    ]

    workbook_children: dict[str, list[Any]] = {}
    standalone_rows: list[Any] = []

    for row in primary_rows:
        parent_file_id = _workbook_parent_file_id(row)

        if parent_file_id:
            workbook_children.setdefault(
                parent_file_id,
                [],
            ).append(row)
        else:
            standalone_rows.append(row)

    #
    # A processing unit is either:
    #
    #   1. one standalone leaf file, or
    #   2. one workbook family consisting of its
    #      support parent plus all worksheet children.
    #
    units: list[dict[str, Any]] = []

    for row in standalone_rows:
        units.append(
            {
                "sort_key": (
                    str(row["normalized_path"] or ""),
                    str(row["file_id"] or ""),
                ),
                "primary_rows": [row],
                "support_rows": [],
            }
        )

    for parent_file_id, child_rows in workbook_children.items():
        child_rows = sorted(
            child_rows,
            key=lambda row: (
                str(row["normalized_path"] or ""),
                str(row["file_id"] or ""),
            ),
        )

        parent_row = rows_by_id.get(parent_file_id)

        support_rows = (
            [parent_row]
            if parent_row is not None
            else []
        )

        if parent_row is not None:
            sort_key = (
                str(parent_row["normalized_path"] or ""),
                str(parent_row["file_id"] or ""),
            )
        else:
            first_child = child_rows[0]
            sort_key = (
                str(first_child["normalized_path"] or ""),
                str(first_child["file_id"] or ""),
            )

        units.append(
            {
                "sort_key": sort_key,
                "primary_rows": child_rows,
                "support_rows": support_rows,
            }
        )

    units.sort(
        key=lambda unit: unit["sort_key"]
    )

    #
    # Pack complete units into deterministic sets.
    # Workbook families are never split.
    #
    packed_sets: list[dict[str, Any]] = []

    current_primary: list[Any] = []
    current_support: list[Any] = []

    def flush_current() -> None:
        nonlocal current_primary
        nonlocal current_support

        if not current_primary:
            return

        packed_sets.append(
            {
                "primary_rows": current_primary,
                "support_rows": current_support,
            }
        )

        current_primary = []
        current_support = []

    for unit in units:
        unit_primary = unit["primary_rows"]
        unit_support = unit["support_rows"]

        unit_size = len(unit_primary)

        if (
            current_primary
            and len(current_primary) + unit_size
            > resolved_set_size
        ):
            flush_current()

        current_primary.extend(unit_primary)

        existing_support_ids = {
            str(row["file_id"])
            for row in current_support
        }

        for support_row in unit_support:
            support_id = str(
                support_row["file_id"]
            )

            if support_id not in existing_support_ids:
                current_support.append(
                    support_row
                )
                existing_support_ids.add(
                    support_id
                )

    flush_current()

    now = utc_now()

    #
    # Idempotent rebuild before processing begins.
    #
    db.execute(
        """
        DELETE FROM processing_set_file
        WHERE job_id=?
        """,
        (job_id,),
    )

    db.execute(
        """
        DELETE FROM processing_set
        WHERE job_id=?
        """,
        (job_id,),
    )

    created_sets: list[dict[str, Any]] = []

    for set_number, packed in enumerate(
        packed_sets,
        start=1,
    ):
        primary = packed["primary_rows"]
        support = packed["support_rows"]

        set_label = (
            f"APCSET-{set_number:04d}"
        )

        set_id = (
            f"{job_id}-{set_label}"
        )

        physical_member_count = (
            len(primary) + len(support)
        )

        db.execute(
            """
            INSERT INTO processing_set (
                set_id,
                job_id,
                matter_id,
                set_number,
                configured_set_size,
                status,
                file_count,
                processed_count,
                success_count,
                failed_count,
                duplicate_count,
                prior_duplicate_count,
                denist_count,
                hash_index_count_before,
                hash_index_count_after,
                detection_status,
                created_at,
                updated_at,
                metadata_json
            )
            VALUES (
                ?,?,?,?,?,?,
                ?,?,?,?,?,?,?,
                ?,?,?,?,?,
                ?
            )
            """,
            (
                set_id,
                job_id,
                matter_id,
                set_number,
                resolved_set_size,
                "pending",
                len(primary),
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "not_ready",
                now,
                now,
                json.dumps(
                    {
                        "set_label": set_label,
                        "processing_file_count": (
                            len(primary)
                        ),
                        "support_file_count": (
                            len(support)
                        ),
                        "physical_member_count": (
                            physical_member_count
                        ),
                    }
                ),
            ),
        )

        memberships = []
        ordinal = 1

        #
        # Workbook support parents first so lineage
        # is present before child Doc ID processing.
        #
        for row in support:
            memberships.append(
                (
                    set_id,
                    row["file_id"],
                    job_id,
                    ordinal,
                    "workbook_parent",
                    0,
                    "pending",
                    0,
                    None,
                    now,
                    now,
                )
            )
            ordinal += 1

        for row in primary:
            memberships.append(
                (
                    set_id,
                    row["file_id"],
                    job_id,
                    ordinal,
                    "primary",
                    1,
                    "pending",
                    0,
                    None,
                    now,
                    now,
                )
            )
            ordinal += 1

        if memberships:
            db.executemany(
                """
                INSERT INTO processing_set_file (
                    set_id,
                    file_id,
                    job_id,
                    ordinal,
                    membership_role,
                    counts_toward_set_size,
                    status,
                    attempts,
                    last_error,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                memberships,
            )

        created_sets.append(
            {
                "set_id": set_id,
                "set_label": set_label,
                "set_number": set_number,
                "configured_set_size": (
                    resolved_set_size
                ),
                "file_count": len(primary),
                "support_file_count": (
                    len(support)
                ),
                "physical_member_count": (
                    physical_member_count
                ),
                "status": "pending",
            }
        )

    return {
        "job_id": job_id,
        "matter_id": matter_id,
        "set_size": resolved_set_size,
        "eligible_file_count": len(
            primary_rows
        ),
        "physical_member_count": sum(
            item["physical_member_count"]
            for item in created_sets
        ),
        "support_file_count": sum(
            item["support_file_count"]
            for item in created_sets
        ),
        "set_count": len(created_sets),
        "sets": created_sets,
    }
    
def refresh_job_population_counts(
    *,
    db: LedgerDB,
    job_id: str,
) -> dict[str, int]:
    denist_count = int(
        db.scalar(
            """
            SELECT COUNT(*)
            FROM file_processing_metrics
            WHERE job_id=?
              AND is_container=0
              AND is_denisted=1
            """,
            (job_id,),
        )
        or 0
    )

    duplicate_count = int(
        db.scalar(
            """
            SELECT COUNT(*)
            FROM file_processing_metrics
            WHERE job_id=?
              AND is_container=0
              AND is_denisted=0
              AND is_duplicate=1
            """,
            (job_id,),
        )
        or 0
    )

    unique_count = int(
        db.scalar(
            """
            SELECT COUNT(*)
            FROM file_processing_metrics
            WHERE job_id=?
              AND is_container=0
              AND is_denisted=0
              AND is_duplicate=0
            """,
            (job_id,),
        )
        or 0
    )

    db.execute(
        """
        UPDATE processing_job
        SET denist_suppressed_count=?,
            duplicate_doc_count=?,
            unique_doc_count=?
        WHERE job_id=?
        """,
        (
            denist_count,
            duplicate_count,
            unique_count,
            job_id,
        ),
    )

    return {
        "denist_count": denist_count,
        "duplicate_count": duplicate_count,
        "unique_count": unique_count,
    }