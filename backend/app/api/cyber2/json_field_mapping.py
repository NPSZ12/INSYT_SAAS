"""Bounded, read-only JSON field mapping for Cyber2.

Mapping is record-relative. No source writes or CSV creation.
"""

import hashlib
import json
import re


class JsonMappingError(ValueError):
    pass


MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 100000
MAX_FIELDS = 200


def _decode_records(data, extension):
    ext = str(extension).lower().lstrip(".")

    if ext not in {"json", "jsonl", "ndjson"}:
        raise JsonMappingError("Unsupported JSON format.")

    if not isinstance(data, bytes) or not data:
        raise JsonMappingError("JSON source is empty.")

    if len(data) > MAX_BYTES:
        raise JsonMappingError(
            "Source exceeds mapping validation limit."
        )

    try:
        text = data.decode("utf-8-sig")

        if ext in {"jsonl", "ndjson"}:
            rows = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
            base = ""
        else:
            root = json.loads(text)

            if isinstance(root, list):
                rows = root
                base = ""
            elif (
                isinstance(root, dict)
                and isinstance(root.get("records"), list)
            ):
                rows = root["records"]
                base = "/records"
            else:
                rows = [root]
                base = ""

    except (UnicodeError, ValueError, TypeError) as exc:
        raise JsonMappingError("Invalid JSON source.") from exc

    if not rows:
        raise JsonMappingError("No records available.")

    if len(rows) > MAX_RECORDS:
        raise JsonMappingError("Record limit exceeded.")

    if not all(isinstance(row, dict) for row in rows):
        raise JsonMappingError(
            "Mapping requires object records."
        )

    return rows, base


def _segments(pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise JsonMappingError(
            "Mapping fields require record-relative JSON pointers."
        )

    if pointer == "/":
        raise JsonMappingError("Root is not a selectable field.")

    parts = pointer[1:].split("/")

    if any(
        not part
        or re.search(r"~(?![01])", part)
        for part in parts
    ):
        raise JsonMappingError("Invalid JSON pointer.")

    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in parts
    ]


def _resolve(record, parts):
    value = record

    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]

    if isinstance(value, (dict, list)):
        raise JsonMappingError(
            "Object and array fields require explicit "
            "source-specific normalization."
        )

    return True, value


def validate_json_field_mapping(
    data,
    extension,
    columns,
    *,
    preview_limit=25,
):
    """Validate all records; return only bounded preview rows."""

    if not isinstance(columns, list) or not columns:
        raise JsonMappingError("Select at least one field.")

    if len(columns) > MAX_FIELDS:
        raise JsonMappingError("Too many mapping columns.")

    if not 1 <= preview_limit <= 100:
        raise JsonMappingError("Invalid preview limit.")

    approved = []
    headers_seen = set()

    for column in columns:
        if not isinstance(column, dict):
            raise JsonMappingError("Invalid mapping column.")

        pointer = column.get("json_pointer")
        header = str(column.get("header") or "").strip()

        if (
            not header
            or len(header) > 128
            or any(ch in header for ch in "\r\n\x00")
        ):
            raise JsonMappingError("Invalid column header.")

        if header.casefold() in headers_seen:
            raise JsonMappingError("Duplicate column header.")

        headers_seen.add(header.casefold())

        approved.append({
            "header": header,
            "json_pointer": pointer,
            "segments": _segments(pointer),
            "present_count": 0,
            "missing_count": 0,
            "null_count": 0,
        })

    rows, base = _decode_records(data, extension)
    preview = []

    for index, record in enumerate(rows):
        mapped = {}

        for column in approved:
            present, value = _resolve(
                record, column["segments"]
            )

            if not present:
                column["missing_count"] += 1
                mapped[column["header"]] = None
            else:
                column["present_count"] += 1

                if value is None:
                    column["null_count"] += 1

                mapped[column["header"]] = value

        if index < preview_limit:
            preview.append({
                "record_index": index,
                "source_pointer": f"{base}/{index}",
                "values": mapped,
            })

    fields = [
        {
            key: value
            for key, value in column.items()
            if key != "segments"
        }
        for column in approved
    ]

    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_format": str(extension).lower().lstrip("."),
        "record_count": len(rows),
        "validated_record_count": len(rows),
        "validation_complete": True,
        "preview_count": len(preview),
        "preview_truncated": len(rows) > len(preview),
        "columns": fields,
        "preview": preview,
        "mapping_saved": False,
        "mapping_approved": False,
        "csv_generated": False,
        "source_modified": False,
    }