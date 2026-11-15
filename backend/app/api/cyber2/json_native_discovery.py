"""Read-only, bounded native JSON discovery for Cyber2.

No Azure access, CSV creation, promotion, or source mutation.
"""

import hashlib
import json
from collections import Counter


class JsonDiscoveryError(ValueError):
    pass


def _field_values(value, path="", depth=0):
    if depth > 12:
        raise JsonDiscoveryError("JSON nesting exceeds preview limit.")

    if isinstance(value, dict):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            child_path = path + "/" + escaped
            yield from _field_values(child, child_path, depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _field_values(
                child, path + "/" + str(index), depth + 1
            )
    else:
        yield path or "/", value


def discover_json_native(
    data: bytes,
    extension: str,
    *,
    max_bytes: int = 4 * 1024 * 1024,
    max_preview_records: int = 25,
    max_fields: int = 500,
):
    """Return structural metadata and a bounded preview only."""
    ext = str(extension).lower().lstrip(".")

    if ext not in {"json", "jsonl", "ndjson"}:
        raise JsonDiscoveryError("Unsupported JSON extension.")

    if not isinstance(data, bytes) or not data:
        raise JsonDiscoveryError("Native JSON is missing or empty.")

    if len(data) > max_bytes:
        raise JsonDiscoveryError(
            "JSON exceeds bounded preview size; no partial "
            "result has been classified as complete."
        )

    try:
        source = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise JsonDiscoveryError("Invalid UTF-8 JSON.") from exc

    try:
        if ext in {"jsonl", "ndjson"}:
            records = [
                json.loads(line)
                for line in source.splitlines()
                if line.strip()
            ]
            container_path = "/"
        else:
            root = json.loads(source)
            if isinstance(root, list):
                records = root
                container_path = "/"
            elif (
                isinstance(root, dict)
                and isinstance(root.get("records"), list)
            ):
                records = root["records"]
                container_path = "/records"
            else:
                records = [root]
                container_path = "/"
    except (ValueError, TypeError) as exc:
        raise JsonDiscoveryError(
            "Malformed JSON; preview not generated."
        ) from exc

    if not records:
        raise JsonDiscoveryError(
            "No records found; no classification inferred."
        )

    field_counts = Counter()
    preview = []

    for index, record in enumerate(records):
        if index >= max_preview_records:
            break

        values = {}
        for path, value in _field_values(record):
            if path not in field_counts and len(field_counts) >= max_fields:
                raise JsonDiscoveryError(
                    "Too many fields for bounded preview."
                )
            field_counts[path] += 1
            values[path] = value

        preview.append({
            "record_index": index,
            "source_pointer": (
                f"{container_path.rstrip('/')}/{index}"
            ),
            "values": values,
        })

    return {
        "source_format": ext,
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_bytes": len(data),
        "record_count": len(records),
        "preview_record_count": len(preview),
        "preview_truncated": len(records) > len(preview),
        "fields": [
            {"json_pointer": path, "preview_occurrences": count}
            for path, count in sorted(field_counts.items())
        ],
        "preview": preview,
        "csv_generated": False,
        "source_modified": False,
    }