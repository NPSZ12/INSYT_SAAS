from __future__ import annotations

import csv
import json
import tempfile

import ijson

from pathlib import Path
from typing import Any

from ..models import (
    StructuredNormalizationResult,
    StructuredPackageInfo,
)


MAX_SALESFORCE_RECORD_EVENT_BYTES = 16 * 1024 * 1024
MAX_SALESFORCE_RECORD_DEPTH = 64


def _validate_record_event_budget(
    source_path: Path,
) -> None:
    """
    Check top-level Salesforce records using incremental
    parser events, including standalone objects.

    An individual large string may still be materialized
    as an event before its size is checked.
    """
    bom = bytes((0xEF, 0xBB, 0xBF))

    def open_events():
        handle = source_path.open("rb")
        if handle.read(3) != bom:
            handle.seek(0)
        return handle

    # Identify the existing record boundary without
    # materializing the JSON source.
    with open_events() as handle:
        events = ijson.parse(handle)
        try:
            _, root_event, _ = next(events)
        except StopIteration:
            raise ValueError("Empty Salesforce JSON.")

        if root_event == "start_array":
            record_prefix = "item"
        elif root_event == "start_map":
            has_records_field = any(
                prefix == ""
                and event == "map_key"
                and value == "records"
                for prefix, event, value in events
            )
            record_prefix = (
                "records.item"
                if has_records_field
                else ""
            )
        else:
            raise ValueError(
                "Unsupported Salesforce JSON root."
            )

    # Second streaming pass applies the same budget
    # to array items and standalone root objects.
    with open_events() as handle:
        active = False
        depth = 0
        event_bytes = 0

        for prefix, event, value in ijson.parse(handle):
            if not active:
                if (
                    prefix == record_prefix
                    and event == "start_map"
                ):
                    active = True
                    depth = 1
                    event_bytes = 0
                continue

            if event in {"start_map", "start_array"}:
                depth += 1
                if depth > MAX_SALESFORCE_RECORD_DEPTH:
                    raise ValueError(
                        "Salesforce record nesting-depth "
                        "budget exceeded."
                    )

            elif event in {"end_map", "end_array"}:
                depth -= 1
                if depth == 0:
                    active = False
                    continue

            elif event == "map_key":
                event_bytes += len(
                    str(value).encode("utf-8")
                )

            elif event in {
                "string", "number", "boolean", "null"
            }:
                event_bytes += len(
                    str(value).encode("utf-8")
                )

            if event_bytes > MAX_SALESFORCE_RECORD_EVENT_BYTES:
                raise ValueError(
                    "Salesforce record size budget exceeded."
                )


META_COLUMNS = [
    "INSYT_Source_Record_ID",
    "INSYT_SF_Object_Type",
    "INSYT_SF_Record_ID",
    "INSYT_SF_Parent_Record_ID",
    "INSYT_SF_Parent_Source_Record_ID",
    "INSYT_SF_Relationship",
    "INSYT_SF_JSON_Path",
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, bool)):
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        )
    return str(value)


def _is_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and (
            isinstance(value.get("attributes"), dict)
            or "Id" in value
        )
    )


def _top_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        if "records" in payload:
            records = payload["records"]
            if not isinstance(records, list):
                raise ValueError(
                    "Salesforce records must be an array."
                )

            # A Salesforce query response may represent
            # only one page of the total result set.
            # Never silently publish incomplete data.
            if payload.get("done") is False or (
                payload.get("nextRecordsUrl")
                and payload.get("done") is not True
            ):
                raise ValueError(
                    "Incomplete Salesforce query page: "
                    "additional pages must be supplied "
                    "before CSV normalization."
                )
            if not (
                "totalSize" in payload
                or "done" in payload
                or any(_is_record(r) for r in records)
            ):
                raise ValueError(
                    "Unrecognized Salesforce query result."
                )
        elif _is_record(payload):
            records = [payload]
        else:
            raise ValueError(
                "JSON does not contain recognizable "
                "Salesforce records."
            )
    else:
        raise ValueError("Unsupported Salesforce JSON root.")

    if not all(isinstance(r, dict) for r in records):
        raise ValueError("Salesforce record must be an object.")

    if records and not any(_is_record(r) for r in records):
        raise ValueError(
            "No recognizable Salesforce records found."
        )

    return records


def _rows_for_record(
    record: dict[str, Any],
    *,
    path: str,
    parent_id: str = "",
    parent_source_id: str = "",
    relationship: str = "",
):
    attributes = record.get("attributes")
    attributes = (
        attributes if isinstance(attributes, dict) else {}
    )
    record_id = _as_text(record.get("Id"))
    source_id = path
    row: dict[str, str] = {
        "INSYT_Source_Record_ID": source_id,
        "INSYT_SF_Object_Type": _as_text(
            attributes.get("type") or relationship
        ),
        "INSYT_SF_Record_ID": record_id,
        "INSYT_SF_Parent_Record_ID": parent_id,
        "INSYT_SF_Parent_Source_Record_ID": parent_source_id,
        "INSYT_SF_Relationship": relationship,
        "INSYT_SF_JSON_Path": path,
    }
    children = []

    def flatten(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            if (
                isinstance(value.get("records"), list)
                and (
                    "totalSize" in value
                    or "done" in value
                    or any(
                        _is_record(item)
                        for item in value["records"]
                    )
                )
            ):
                # Related-record collections can have
                # independent Salesforce pagination.
                if value.get("done") is False or (
                    value.get("nextRecordsUrl")
                    and value.get("done") is not True
                ):
                    raise ValueError(
                        "Incomplete Salesforce related-record "
                        "page: additional relationship records "
                        "are required before CSV normalization."
                    )

                declared = value.get("totalSize")
                actual = len(value["records"])

                if (
                    declared is not None
                    and value.get("done") is True
                    and (
                        type(declared) is not int
                        or declared < 0
                        or declared != actual
                    )
                ):
                    raise ValueError(
                        "Salesforce related-record count mismatch: "
                        f"relationship {prefix}, "
                        f"declared {declared}, found {actual}."
                    )

                row[f"SF__{prefix}.__related_count"] = str(
                    actual
                )
                for index, child in enumerate(value["records"]):
                    if not isinstance(child, dict):
                        raise ValueError(
                            "Related Salesforce record is not an object."
                        )
                    child_path = (
                        f"{path}/{prefix.replace('.', '/')}"
                        f"/records/{index}"
                    )
                    children.extend(
                        _rows_for_record(
                            child,
                            path=child_path,
                            parent_id=record_id,
                            parent_source_id=source_id,
                            relationship=prefix,
                        )
                    )
            else:
                if not value:
                    row[f"SF__{prefix}"] = "{}"
                for key, item in value.items():
                    flatten(f"{prefix}.{key}", item)
        elif isinstance(value, list):
            # Preserve arrays without multiplying arbitrary
            # field values into unrelated record rows.
            row[f"SF__{prefix}"] = _as_text(value)
        else:
            row[f"SF__{prefix}"] = _as_text(value)

    for key, value in record.items():
        if key == "attributes":
            for attr_key, attr_value in attributes.items():
                row[f"SF__attributes.{attr_key}"] = _as_text(
                    attr_value
                )
        else:
            flatten(key, value)

    yield row
    yield from children


def _iter_salesforce_records(source_path: Path):
    """
    Iterate one top-level Salesforce record at a time.

    A first streaming pass validates the root and query
    pagination metadata. The second pass yields records.

    Nested object sizes remain subject to per-record limits.
    """
    with source_path.open("rb") as handle:
        if handle.read(3) != bytes((0xEF, 0xBB, 0xBF)):
            handle.seek(0)
        events = ijson.parse(handle)
        try:
            _, root_event, _ = next(events)
        except StopIteration:
            raise ValueError("Empty Salesforce JSON.")

        if root_event not in {"start_map", "start_array"}:
            raise ValueError(
                "Unsupported Salesforce JSON root."
            )

        has_records_array = False
        has_records_field = False
        done = None
        next_url = None
        declared_total = None
        observed_total = 0

        if root_event == "start_map":
            for prefix, event, value in events:
                if prefix == "records" and event in {
                    "start_array", "start_map", "null"
                }:
                    has_records_field = True
                    if event == "start_array":
                        has_records_array = True
                elif (
                    prefix == "records.item"
                    and event == "start_map"
                ):
                    observed_total += 1
                elif (
                    prefix == "totalSize"
                    and event in {"number", "integer"}
                ):
                    declared_total = value
                elif prefix == "done" and event == "boolean":
                    done = value
                elif prefix == "nextRecordsUrl" and event in {
                    "string", "null"
                }:
                    next_url = value

            if done is False or (
                next_url and done is not True
            ):
                raise ValueError(
                    "Incomplete Salesforce query page: "
                    "additional pages must be supplied "
                    "before CSV normalization."
                )

            if has_records_field and not has_records_array:
                raise ValueError(
                    "Salesforce records must be an array."
                )

            if (
                has_records_array
                and declared_total is not None
                and done is True
                and (
                    not isinstance(declared_total, int)
                    or declared_total < 0
                    or declared_total != observed_total
                )
            ):
                raise ValueError(
                    "Salesforce query record-count mismatch: "
                    f"declared {declared_total}, "
                    f"found {observed_total}."
                )

    if root_event == "start_array":
        prefix = "item"
    elif has_records_array:
        prefix = "records.item"
    else:
        # A single Salesforce object is one logical record.
        # It is parsed individually rather than materializing
        # a collection of records.
        with source_path.open("rb") as handle:
            if handle.read(3) != bytes((0xEF, 0xBB, 0xBF)):
                handle.seek(0)
            payload = next(ijson.items(handle, ""))
        yield from _top_records(payload)
        return

    with source_path.open("rb") as handle:
        if handle.read(3) != bytes((0xEF, 0xBB, 0xBF)):
            handle.seek(0)
        for index, record in enumerate(
            ijson.items(handle, prefix)
        ):
            if not isinstance(record, dict):
                raise ValueError(
                    "Salesforce record must be an object."
                )
            if not _is_record(record):
                raise ValueError(
                    "Unrecognized Salesforce record at "
                    f"index {index}."
                )
            yield record



def normalize_salesforce_json_to_csv(
    *,
    source_path: Path,
    output_path: Path,
    package_id: str | None = None,
) -> StructuredNormalizationResult:
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == output_path:
        raise ValueError("Source and CSV output must differ.")
    if output_path.exists():
        raise FileExistsError(output_path)

    # Preflight each top-level record before creating
    # normalized CSV output.
    _validate_record_event_budget(source_path)

    # One record at a time; no full-export json.load().
    records = _iter_salesforce_records(source_path)
    columns = list(META_COLUMNS)
    seen = set(columns)
    count = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="insyt_sf_", dir=output_path.parent
    ) as temp:
        spool = Path(temp) / "records.jsonl"

        with spool.open("w", encoding="utf-8") as handle:
            for index, record in enumerate(records):
                for row in _rows_for_record(
                    record, path=f"/records/{index}"
                ):
                    count += 1
                    for key in row:
                        if key not in seen:
                            seen.add(key)
                            columns.append(key)
                    handle.write(
                        json.dumps(row, ensure_ascii=False)
                        + "\n"
                    )

        temporary_csv = Path(temp) / "output.csv"

        with temporary_csv.open(
            "w", encoding="utf-8-sig", newline=""
        ) as target:
            writer = csv.DictWriter(
                target, fieldnames=columns,
                extrasaction="raise"
            )
            writer.writeheader()
            with spool.open("r", encoding="utf-8") as handle:
                for line in handle:
                    writer.writerow(json.loads(line))

        temporary_csv.replace(output_path)

    package = StructuredPackageInfo(
        source_family="structured",
        source_format="json",
        source_profile="salesforce",
        source_path=source_path,
        source_filename=source_path.name,
        package_id=package_id,
        record_count=count,
        normalized_format="csv",
        normalized_csv_path=output_path,
        metadata={
            "adapter": "json_salesforce",
            "original_source_preserved": True,
            "record_boundary": "salesforce_record",
            "column_count": len(columns),
        },
    )

    return StructuredNormalizationResult(
        package=package,
        normalized_csv_paths=[output_path],
        group_counts={},
        metadata={
            "columns": columns,
            "record_count": count,
        },
    )
