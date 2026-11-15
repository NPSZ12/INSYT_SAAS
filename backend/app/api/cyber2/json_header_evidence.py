"""Read-only structured JSON evidence for Cyber2 header creation.

No AI inference, mapping approval, or CSV generation occurs here.
"""

import hashlib
import json


MAX_BYTES = 4 * 1024 * 1024
MAX_FIELDS = 2000
MAX_NODES = 200000
MAX_RECORDS = 100000
MAX_SAMPLES = 3


class JsonEvidenceError(ValueError):
    pass


def _escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _decode(data, extension):
    ext = str(extension).lower().lstrip(".")

    if ext not in ("json", "jsonl", "ndjson"):
        raise JsonEvidenceError("Unsupported JSON format.")

    if not isinstance(data, bytes) or not data:
        raise JsonEvidenceError("JSON source is empty.")

    if len(data) > MAX_BYTES:
        raise JsonEvidenceError("JSON source exceeds evidence limit.")

    try:
        text = data.decode("utf-8-sig")
        if ext in ("jsonl", "ndjson"):
            records = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
            base = ""
        else:
            root = json.loads(text)
            if isinstance(root, list):
                records, base = root, ""
            elif (
                isinstance(root, dict)
                and isinstance(root.get("records"), list)
            ):
                records, base = root["records"], "/records"
            else:
                records, base = [root], ""
    except (UnicodeError, ValueError, TypeError) as exc:
        raise JsonEvidenceError("Invalid JSON source.") from exc

    if not records or len(records) > MAX_RECORDS:
        raise JsonEvidenceError("Invalid record count.")

    if not all(isinstance(row, dict) for row in records):
        raise JsonEvidenceError("Object records are required.")

    return records, base


def discover_json_header_evidence(
    data, extension, *, sample_limit=MAX_SAMPLES
):
    """Discover all bounded structural paths, not only preview rows."""

    if not isinstance(sample_limit, int) or not 1 <= sample_limit <= 10:
        raise JsonEvidenceError("Invalid sample limit.")

    records, base = _decode(data, extension)
    evidence = {}
    node_count = 0

    def visit(value, normalized, actual, record_index, depth):
        nonlocal node_count

        node_count += 1
        if node_count > MAX_NODES or depth > 40:
            raise JsonEvidenceError(
                "JSON structure exceeds safe traversal limits."
            )

        if normalized:
            kind = (
                "array" if isinstance(value, list)
                else "object" if isinstance(value, dict)
                else "scalar"
            )

            entry = evidence.get(normalized)
            if entry is None:
                if len(evidence) >= MAX_FIELDS:
                    raise JsonEvidenceError("Field limit exceeded.")
                entry = {
                    "json_pointer": normalized,
                    "source_path": normalized[1:].replace("/", "."),
                    "kind": kind,
                    "record_indices": set(),
                    "occurrence_count": 0,
                    "nonempty_count": 0,
                    "sample_values": [],
                    "sample_source_pointers": [],
                }
                evidence[normalized] = entry

            if entry["kind"] != kind:
                entry["kind"] = "mixed"

            entry["record_indices"].add(record_index)
            entry["occurrence_count"] += 1

            present = (
                value is not None
                and value != ""
                and value != []
                and value != {}
            )

            if present:
                entry["nonempty_count"] += 1

            if (
                present
                and len(entry["sample_values"]) < sample_limit
            ):
                if isinstance(value, (list, dict)):
                    sample = (
                        f"{len(value)} entries"
                        if isinstance(value, list)
                        else f"{len(value)} fields"
                    )
                else:
                    sample = str(value)

                entry["sample_values"].append(sample[:300])
                entry["sample_source_pointers"].append(actual)

        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or not key:
                    raise JsonEvidenceError(
                        "Empty JSON field names require manual handling."
                    )
                escaped = _escape(key)
                visit(
                    child,
                    normalized + "/" + escaped,
                    actual + "/" + escaped,
                    record_index,
                    depth + 1,
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(
                    child,
                    normalized + "/[]",
                    actual + f"/{index}",
                    record_index,
                    depth + 1,
                )

    for index, record in enumerate(records):
        visit(record, "", f"{base}/{index}", index, 0)

    fields = []
    for pointer, entry in sorted(evidence.items()):
        distinct_record_count = len(entry.pop("record_indices"))
        entry["record_count_with_field"] = distinct_record_count
        entry["record_count_without_field"] = (
            len(records) - distinct_record_count
        )
        fields.append(entry)

    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_format": str(extension).lower().lstrip("."),
        "record_count": len(records),
        "structure_scan_complete": True,
        "field_count": len(fields),
        "fields": fields,
        "ai_invoked": False,
        "mapping_approved": False,
        "csv_generated": False,
        "source_modified": False,
    }