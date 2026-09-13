from __future__ import annotations

import csv
import json

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models import (
    StructuredNormalizationResult,
    StructuredPackageInfo,
    StructuredRecord,
)


def _flatten_value(
    value: Any,
    *,
    prefix: str = "",
    separator: str = ".",
) -> dict[str, Any]:
    """
    Flatten nested JSON objects into dot-notated columns.

    Lists of scalar values are serialized as JSON.
    Lists containing objects are also serialized as JSON so
    record boundaries are not accidentally multiplied.
    """

    flattened: dict[str, Any] = {}


    if isinstance(value, dict):

        for key, child in value.items():

            clean_key = str(
                key
            ).strip()

            column_name = (
                f"{prefix}{separator}{clean_key}"
                if prefix
                else clean_key
            )

            flattened.update(
                _flatten_value(
                    child,
                    prefix=column_name,
                    separator=separator,
                )
            )


        if not value and prefix:
            flattened[prefix] = ""

        return flattened


    if isinstance(value, list):

        if prefix:
            flattened[prefix] = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )

        return flattened


    if prefix:

        if value is None:
            flattened[prefix] = ""

        elif isinstance(
            value,
            bool,
        ):
            flattened[prefix] = (
                "true"
                if value
                else "false"
            )

        else:
            flattened[prefix] = value


    return flattened


def _iter_json_records(
    source_path: Path,
) -> Iterator[tuple[str, Any]]:
    """
    Yield logical records from JSON, JSONL, or NDJSON.

    Rules:

    .json top-level list
        -> one record per list item

    .json top-level dict containing "records" list
        -> one record per records[] item

    .json other top-level dict
        -> one logical record

    .json scalar
        -> one logical record

    .jsonl / .ndjson
        -> one record per non-empty line
    """

    extension = (
        source_path.suffix
        .strip()
        .lower()
    )


    if extension in {
        ".jsonl",
        ".ndjson",
    }:

        with source_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as handle:

            record_number = 0

            for line in handle:

                raw = line.strip()

                if not raw:
                    continue

                record_number += 1

                payload = json.loads(
                    raw
                )

                yield (
                    str(record_number),
                    payload,
                )

        return


    if extension != ".json":
        raise ValueError(
            f"Unsupported JSON extension: "
            f"{extension or '[none]'}"
        )


    with source_path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
    ) as handle:

        payload = json.load(
            handle
        )


    if isinstance(
        payload,
        list,
    ):

        for index, item in enumerate(
            payload,
            start=1,
        ):
            yield (
                str(index),
                item,
            )

        return


    if isinstance(
        payload,
        dict,
    ):

        records = payload.get(
            "records"
        )

        if isinstance(
            records,
            list,
        ):

            for index, item in enumerate(
                records,
                start=1,
            ):
                yield (
                    str(index),
                    item,
                )

            return


        yield (
            "1",
            payload,
        )

        return


    yield (
        "1",
        payload,
    )


def iter_plain_json_records(
    source_path: Path,
) -> Iterator[StructuredRecord]:
    """
    Convert generic JSON logical records into the shared
    StructuredRecord contract.
    """

    for (
        source_record_id,
        payload,
    ) in _iter_json_records(
        source_path
    ):

        if isinstance(
            payload,
            dict,
        ):

            fields = _flatten_value(
                payload
            )

            record_type = "object"

        elif isinstance(
            payload,
            list,
        ):

            fields = {
                "value": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            }

            record_type = "array"

        else:

            fields = {
                "value": (
                    ""
                    if payload is None
                    else payload
                )
            }

            record_type = type(
                payload
            ).__name__


        yield StructuredRecord(
            source_record_id=source_record_id,
            record_type=record_type,
            fields=fields,
        )


def _discover_columns(
    source_path: Path,
) -> list[str]:
    """
    First pass: discover the complete tabular schema.

    This avoids silently dropping columns that appear only
    in later JSON records.
    """

    columns: list[str] = []

    seen: set[str] = set()


    base_columns = [
        "INSYT_Source_Record_ID",
        "INSYT_Record_Type",
    ]


    for column in base_columns:

        columns.append(
            column
        )

        seen.add(
            column
        )


    for record in iter_plain_json_records(
        source_path
    ):

        for key in record.fields.keys():

            if key in seen:
                continue

            seen.add(
                key
            )

            columns.append(
                key
            )


    return columns


def normalize_plain_json_to_csv(
    *,
    source_path: Path,
    output_path: Path,
    package_id: str | None = None,
) -> StructuredNormalizationResult:
    """
    Normalize generic JSON into a CSV working artifact.

    The original JSON source is not modified.

    Population count is based on logical records, not the
    number of uploaded package files.
    """

    source_path = source_path.resolve()

    output_path = output_path.resolve()


    if not source_path.exists():
        raise FileNotFoundError(
            f"JSON source does not exist: "
            f"{source_path}"
        )


    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    columns = _discover_columns(
        source_path
    )


    record_count = 0


    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()


        for record in iter_plain_json_records(
            source_path
        ):

            record_count += 1


            row: dict[str, Any] = {
                "INSYT_Source_Record_ID":
                    record.source_record_id,

                "INSYT_Record_Type":
                    record.record_type,
            }


            row.update(
                record.fields
            )


            writer.writerow(
                row
            )


    package = StructuredPackageInfo(
        source_family="structured",
        source_format="json",
        source_profile="plain",

        source_path=source_path,
        source_filename=source_path.name,

        package_id=package_id,

        package_count=1,
        record_count=record_count,

        normalized_format="csv",
        normalized_csv_path=output_path,

        metadata={
            "adapter":
                "json_plain",

            "original_source_preserved":
                True,

            "record_boundary":
                (
                    "top_level_array_item_or_"
                    "records_array_item_or_"
                    "single_top_level_value"
                ),

            "column_count":
                len(columns),
        },
    )


    return StructuredNormalizationResult(
        package=package,

        normalized_csv_paths=[
            output_path
        ],

        group_counts={},

        metadata={
            "columns":
                columns,

            "record_count":
                record_count,
        },
    )