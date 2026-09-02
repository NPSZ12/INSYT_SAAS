from __future__ import annotations

import json
import re

from pathlib import Path

from ..azure_layout import AzureRoutingConfig
from ..config import Settings
from ..db import LedgerDB
from ..doc_id_registry import reserve_doc_ids
from ..telemetry import StageRunner
from ..util import json_dumps, utc_now


def _safe_filename_component(
    value: str,
    *,
    max_length: int = 100,
) -> str:
    clean = str(
        value
        or ""
    ).strip()

    clean = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        clean,
    )

    clean = re.sub(
        r"\s+",
        "_",
        clean,
    )

    clean = re.sub(
        r"_+",
        "_",
        clean,
    )

    clean = clean.strip(
        " ._"
    )

    if not clean:
        clean = "Unknown"

    return clean[
        :max_length
    ]


def _stage_status(
    row,
) -> dict:
    raw = None

    try:
        raw = row[
            "stage_status_json"
        ]
    except Exception:
        raw = None

    if not raw:
        return {}

    try:
        parsed = json.loads(
            raw
        )

        return (
            parsed
            if isinstance(
                parsed,
                dict,
            )
            else {}
        )

    except Exception:
        return {}


def _workbook_sheet_metadata(
    row,
) -> dict:
    status = _stage_status(
        row
    )

    workbook_sheet = (
        status.get(
            "workbook_sheet"
        )
        or {}
    )

    if not isinstance(
        workbook_sheet,
        dict,
    ):
        return {}

    return workbook_sheet


def _derived_workbook_csv_filename(
    *,
    doc_id: str,
    workbook_name: str,
    sheet_index: int,
    sheet_name: str,
) -> str:
    workbook_stem = (
        Path(
            str(
                workbook_name
                or "Workbook"
            )
        )
        .stem
    )

    workbook_part = (
        _safe_filename_component(
            workbook_stem,
            max_length=90,
        )
    )

    sheet_part = (
        _safe_filename_component(
            sheet_name,
            max_length=90,
        )
    )

    return (
        f"{doc_id}"
        f"__{workbook_part}"
        f"__Sheet_{sheet_index:04d}"
        f"__{sheet_part}.csv"
    )


def _unique_path(
    desired_path: Path,
) -> Path:
    if not desired_path.exists():
        return desired_path

    stem = desired_path.stem
    suffix = desired_path.suffix
    parent = desired_path.parent

    number = 2

    while True:
        candidate = (
            parent
            / f"{stem}__{number}{suffix}"
        )

        if not candidate.exists():
            return candidate

        number += 1


def _rename_workbook_sheet_csv(
    *,
    row,
    doc_id: str,
) -> dict:
    """
    Rename a worksheet-derived CSV after Doc ID assignment.

    Example:

        Sheet_0004__Claims.csv

    becomes:

        INSYT000000123__Client_Data__Sheet_0004__Claims.csv

    Original workbook/sheet lineage remains stored in
    stage_status_json.
    """

    workbook_sheet = (
        _workbook_sheet_metadata(
            row
        )
    )

    if not workbook_sheet:
        return {
            "renamed": False,
            "reason": (
                "not_workbook_sheet"
            ),
        }

    current_path_text = str(
        row[
            "original_path"
        ]
        or ""
    ).strip()

    if not current_path_text:
        return {
            "renamed": False,
            "reason": (
                "missing_original_path"
            ),
        }

    current_path = Path(
        current_path_text
    )

    if (
        current_path.suffix
        .lower()
        != ".csv"
    ):
        return {
            "renamed": False,
            "reason": (
                "workbook_child_not_csv"
            ),
        }

    workbook_name = str(
        workbook_sheet.get(
            "original_workbook_name"
        )
        or "Workbook"
    )

    sheet_name = str(
        workbook_sheet.get(
            "sheet_name"
        )
        or "Sheet"
    )

    try:
        sheet_index = int(
            workbook_sheet.get(
                "sheet_index"
            )
            or 0
        )

    except Exception:
        sheet_index = 0

    if sheet_index <= 0:
        sheet_index = 1

    derived_filename = (
        _derived_workbook_csv_filename(
            doc_id=doc_id,
            workbook_name=(
                workbook_name
            ),
            sheet_index=(
                sheet_index
            ),
            sheet_name=(
                sheet_name
            ),
        )
    )

    desired_path = (
        current_path.parent
        / derived_filename
    )

    if (
        current_path.name
        == desired_path.name
    ):
        final_path = (
            current_path
        )

    else:
        if not current_path.exists():
            return {
                "renamed": False,
                "reason": (
                    "source_csv_missing"
                ),
                "expected_path": (
                    str(
                        current_path
                    )
                ),
            }

        final_path = (
            _unique_path(
                desired_path
            )
        )

        current_path.rename(
            final_path
        )

    normalized_path = str(
        row[
            "normalized_path"
        ]
        or ""
    )

    if normalized_path:
        if "/" in normalized_path:
            normalized_parent = (
                normalized_path
                .rsplit(
                    "/",
                    1,
                )[0]
            )

            new_normalized_path = (
                f"{normalized_parent}/"
                f"{final_path.name}"
            )

        else:
            new_normalized_path = (
                final_path.name
            )

    else:
        new_normalized_path = (
            final_path.name
        )

    return {
        "renamed": True,
        "previous_path": (
            str(
                current_path
            )
        ),
        "new_path": (
            str(
                final_path
            )
        ),
        "previous_normalized_path": (
            normalized_path
        ),
        "new_normalized_path": (
            new_normalized_path
        ),
        "derived_filename": (
            final_path.name
        ),
        "workbook_name": (
            workbook_name
        ),
        "sheet_name": (
            sheet_name
        ),
        "sheet_index": (
            sheet_index
        ),
    }


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
    #
    # Containers are deliberately excluded.
    #
    # Successful ZIPs/workbooks remain parent source objects,
    # while their extracted children receive normal Doc IDs.
    #
    where = (
        "job_id=? "
        "AND is_container=0 "
        "AND is_denisted=0"
    )

    params: tuple = (
        job_id,
    )

    if suppress_duplicates:
        where += (
            " AND is_duplicate=0"
        )

    rows = db.query(
        f"""
        SELECT
            file_id,
            family_id,
            parent_file_id,
            source_container_file_id,
            original_path,
            normalized_path,
            extension,
            stage_status_json
        FROM file_processing_metrics
        WHERE {where}
        ORDER BY
            coalesce(
                family_id,
                file_id
            ),
            normalized_path
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
        allocation = (
            reserve_doc_ids(
                routing=routing,
                count=len(
                    rows
                ),
                prefix=prefix,
                width=width,
            )
        )

        n = (
            allocation.start_number
        )

        workbook_sheet_count = 0
        workbook_sheet_rename_count = 0
        workbook_sheet_rename_failures: list[
            dict
        ] = []

        for row in rows:
            doc_id = (
                f"{prefix}"
                f"{n:0{width}d}"
            )

            #
            # Assign Doc ID first.
            #
            db.execute(
                """
                UPDATE file_processing_metrics
                SET
                    doc_id=?,
                    updated_at=?
                WHERE file_id=?
                """,
                (
                    doc_id,
                    utc_now(),
                    row[
                        "file_id"
                    ],
                ),
            )

            workbook_metadata = (
                _workbook_sheet_metadata(
                    row
                )
            )

            if workbook_metadata:
                workbook_sheet_count += 1

                try:
                    rename_result = (
                        _rename_workbook_sheet_csv(
                            row=row,
                            doc_id=doc_id,
                        )
                    )

                    if rename_result.get(
                        "renamed"
                    ):
                        workbook_sheet_rename_count += 1

                        db.execute(
                            """
                            UPDATE file_processing_metrics
                            SET
                                original_path=?,
                                normalized_path=?,
                                updated_at=?,
                                stage_status_json=json_patch(
                                    stage_status_json,
                                    ?
                                )
                            WHERE file_id=?
                            """,
                            (
                                rename_result[
                                    "new_path"
                                ],
                                rename_result[
                                    "new_normalized_path"
                                ],
                                utc_now(),
                                json_dumps(
                                    {
                                        "workbook_sheet": {
                                            "doc_id": (
                                                doc_id
                                            ),
                                            "derived_filename": (
                                                rename_result[
                                                    "derived_filename"
                                                ]
                                            ),
                                            "derived_csv_path": (
                                                rename_result[
                                                    "new_path"
                                                ]
                                            ),
                                            "derived_normalized_path": (
                                                rename_result[
                                                    "new_normalized_path"
                                                ]
                                            ),
                                        }
                                    }
                                ),
                                row[
                                    "file_id"
                                ],
                            ),
                        )

                    else:
                        workbook_sheet_rename_failures.append(
                            {
                                "file_id": (
                                    row[
                                        "file_id"
                                    ]
                                ),
                                "doc_id": (
                                    doc_id
                                ),
                                **rename_result,
                            }
                        )

                except Exception as exc:
                    workbook_sheet_rename_failures.append(
                        {
                            "file_id": (
                                row[
                                    "file_id"
                                ]
                            ),
                            "doc_id": (
                                doc_id
                            ),
                            "error": repr(
                                exc
                            ),
                        }
                    )

                    #
                    # Filename enhancement failure must not
                    # invalidate the assigned Doc ID.
                    #
                    db.execute(
                        """
                        UPDATE file_processing_metrics
                        SET
                            updated_at=?,
                            stage_status_json=json_patch(
                                stage_status_json,
                                ?
                            )
                        WHERE file_id=?
                        """,
                        (
                            utc_now(),
                            json_dumps(
                                {
                                    "workbook_sheet": {
                                        "doc_id": (
                                            doc_id
                                        ),
                                        "derived_filename_status": (
                                            "rename_failed"
                                        ),
                                        "derived_filename_error": (
                                            repr(
                                                exc
                                            )
                                        ),
                                    }
                                }
                            ),
                            row[
                                "file_id"
                            ],
                        ),
                    )

            n += 1

        stage.metrics.files_in = (
            len(
                rows
            )
        )

        stage.metrics.files_out = (
            len(
                rows
            )
        )

        stage.metrics.documents_in = (
            len(
                rows
            )
        )

        stage.metrics.documents_out = (
            len(
                rows
            )
        )

        stage.metrics.exceptions = (
            len(
                workbook_sheet_rename_failures
            )
        )

        stage.metrics.extra.update(
            {
                "prefix": prefix,
                "requested_start_number": (
                    start_number
                ),
                "registry_start_number": (
                    allocation.start_number
                ),
                "registry_end_number": (
                    allocation.end_number
                ),
                "previous_last_assigned_number": (
                    allocation.previous_last_assigned_number
                ),
                "new_last_assigned_number": (
                    allocation.new_last_assigned_number
                ),
                "registry_blob_path": (
                    allocation.registry_blob_path
                ),
                "assigned": (
                    len(
                        rows
                    )
                ),
                "workbook_sheet_doc_count": (
                    workbook_sheet_count
                ),
                "workbook_sheet_rename_count": (
                    workbook_sheet_rename_count
                ),
                "workbook_sheet_rename_failures": (
                    workbook_sheet_rename_failures[
                        :50
                    ]
                ),
            }
        )