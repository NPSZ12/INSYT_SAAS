from __future__ import annotations

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
