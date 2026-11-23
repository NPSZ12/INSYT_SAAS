"""Read-only, protocol-restricted JSON mapped-row preview.

Never writes CSV or changes native JSON. No AI inference.
"""

import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from json_header_evidence import (
    JsonEvidenceError,
    _decode,
    discover_json_header_evidence,
)
from json_duplicate_headers import (
    DuplicateHeaderError,
    assign_json_output_headers,
)


class JsonTransformError(ValueError):
    pass


def _unescape(part):
    if re.search(r"~(?![01])", part):
        raise JsonTransformError("Invalid JSON pointer escape.")
    return part.replace("~1", "/").replace("~0", "~")


def _values(record, pointer):
    """Return values at a normalized, record-relative JSON path."""

    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise JsonTransformError("Invalid JSON pointer.")

    parts = [_unescape(p) for p in pointer[1:].split("/")]
    current = [record]

    for part in parts:
        next_values = []

        for value in current:
            if part == "[]":
                if isinstance(value, list):
                    next_values.extend(value)
            elif isinstance(value, dict) and part in value:
                next_values.append(value[part])

        current = next_values

    return current


def _nonempty(value):
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict)):
        return any(_nonempty(v) for v in value) if isinstance(
            value, list
        ) else any(_nonempty(v) for v in value.values())
    return True


def _scalar(value):
    if isinstance(value, (dict, list)):
        raise JsonTransformError(
            "Structured data requires a scalar child path "
            "or Yes if Present."
        )
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _treat(values, treatment):
    qualifying = [v for v in values if _nonempty(v)]

    if treatment == "yes_if_present":
        return "Yes" if qualifying else ""

    if not qualifying:
        return ""

    if treatment == "mask":
        # Deliberately redact the entire qualifying value.
        return "****"

    if treatment == "text":
        texts = [_scalar(value) for value in qualifying]
        if len(texts) != 1:
            raise JsonTransformError(
                "Text treatment would lose repeated values. "
                "Select Concatenate or another treatment."
            )
        return texts[0]

    if treatment == "concatenate":
        texts = []
        seen = set()
        for value in qualifying:
            text = _scalar(value)
            if text not in seen:
                seen.add(text)
                texts.append(text)
        return "; ".join(texts)

    if treatment == "maximum":
        try:
            numbers = [
                Decimal(_scalar(value).strip())
                for value in qualifying
            ]
            if not all(number.is_finite() for number in numbers):
                raise InvalidOperation
        except (InvalidOperation, ValueError) as exc:
            raise JsonTransformError(
                "Maximum treatment requires numeric values."
            ) from exc
        return format(max(numbers), "f")

    if treatment == "latest":
        parsed = []
        for value in qualifying:
            text = _scalar(value).strip()
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                    parsed.append(
                        datetime.combine(
                            date.fromisoformat(text),
                            datetime.min.time(),
                            timezone.utc,
                        )
                    )
                else:
                    parsed.append(
                        datetime.fromisoformat(
                            text.replace("Z", "+00:00")
                        ).astimezone(timezone.utc)
                    )
            except (ValueError, OverflowError) as exc:
                raise JsonTransformError(
                    "Latest treatment requires ISO dates."
                ) from exc
        return max(parsed).isoformat()

    raise JsonTransformError("Unsupported data treatment.")


def decisions_from_approved_json_mapping(
    approved_document, evidence, protocol_headers
):
    """Adapt trusted, saved approval to existing JSON decisions.

    The caller must first verify the approved mapping status,
    project scope, native source identity, and source hash.
    This function never approves data or changes source bytes.
    """
    if not isinstance(approved_document, dict):
        raise JsonTransformError("Invalid approved document.")

    fields = evidence.get("fields") if isinstance(evidence, dict) else None
    columns = approved_document.get("columns")

    if not isinstance(fields, list) or not isinstance(columns, list):
        raise JsonTransformError("Approved JSON evidence is incomplete.")

    if not isinstance(protocol_headers, list) or not protocol_headers:
        raise JsonTransformError("Approved protocol is required.")

    protocol = {
        str(header).strip().casefold(): str(header).strip()
        for header in protocol_headers
        if isinstance(header, str) and header.strip()
    }

    expected_scalars = {
        field["json_pointer"]
        for field in fields
        if field.get("kind") == "scalar"
    }

    approved_by_path = {}

    for column in columns:
        if not isinstance(column, dict):
            raise JsonTransformError("Invalid approved column.")

        pointer = column.get("json_pointer")

        if pointer not in expected_scalars or pointer in approved_by_path:
            raise JsonTransformError(
                "Unknown, structural, or duplicate approved field."
            )

        approved_by_path[pointer] = column

    if set(approved_by_path) != expected_scalars:
        raise JsonTransformError(
            "Every scalar field requires an approved disposition."
        )

    decisions = []

    for field in fields:
        pointer = field["json_pointer"]

        if field.get("kind") != "scalar":
            decisions.append({
                "json_pointer": pointer,
                "action": "discard",
                "header": "",
                "treatment": "discard",
                "reviewed": True,
            })
            continue

        column = approved_by_path[pointer]
        disposition = str(column.get("disposition") or "").lower()
        header = str(column.get("final_header") or "").strip()
        deleted = column.get("delete_column") is True

        if disposition == "delete":
            if not deleted or header:
                raise JsonTransformError("Inconsistent deleted column.")
            action = "discard"
            treatment = "discard"

        elif disposition in {"approve", "map"}:
            if deleted or header.casefold() not in protocol:
                raise JsonTransformError(
                    "Protocol mapping is not authorized."
                )
            header = protocol[header.casefold()]
            action = disposition
            treatment = "text"

        elif disposition in {"keep", "rename"}:
            if deleted or not header:
                raise JsonTransformError(
                    "Invalid retained source header."
                )
            action = disposition
            treatment = "text"

        else:
            raise JsonTransformError(
                "Unsupported approved disposition."
            )

        decisions.append({
            "json_pointer": pointer,
            "action": action,
            "header": header,
            "treatment": treatment,
            "reviewed": True,
        })

    return decisions


def preview_json_mapped_rows(
    data,
    extension,
    decisions,
    protocol_headers,
    expected_sha256,
    *,
    preview_limit=25,
    record_array_path=None,
    include_all_rows=False,
):
    """Validate every record; return bounded output-row preview."""

    if not isinstance(preview_limit, int) or not 1 <= preview_limit <= 100:
        raise JsonTransformError("Invalid preview limit.")

    if not isinstance(expected_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha256
    ):
        raise JsonTransformError("Invalid expected source hash.")

    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise JsonTransformError("Source integrity mismatch.")

    try:
        evidence = discover_json_header_evidence(data, extension)
        rows, base = _decode(data, extension)
    except JsonEvidenceError as exc:
        raise JsonTransformError(str(exc)) from exc

    expected_paths = {
        field["json_pointer"] for field in evidence["fields"]
    }

    if not isinstance(decisions, list):
        raise JsonTransformError("Invalid reviewer decisions.")

    supplied_paths = [d.get("json_pointer") for d in decisions
                      if isinstance(d, dict)]

    if (
        len(supplied_paths) != len(decisions)
        or len(supplied_paths) != len(expected_paths)
        or set(supplied_paths) != expected_paths
    ):
        raise JsonTransformError(
            "Every discovered JSON field must have one review decision."
        )

    try:
        plan = assign_json_output_headers(
            decisions, protocol_headers
        )
    except DuplicateHeaderError as exc:
        raise JsonTransformError(str(exc)) from exc

    # Do not rely on client-supplied ordering for suffix assignment.
    order = {
        field["json_pointer"]: index
        for index, field in enumerate(evidence["fields"])
    }
    sorted_decisions = sorted(
        decisions, key=lambda item: order[item["json_pointer"]]
    )
    try:
        plan = assign_json_output_headers(
            sorted_decisions, protocol_headers
        )
    except DuplicateHeaderError as exc:
        raise JsonTransformError(str(exc)) from exc

    if not plan["columns"]:
        raise JsonTransformError(
            "At least one approved reportable field is required."
        )

    # Explicit record boundaries; never flatten arbitrary arrays.
    logical_records = []

    if record_array_path is None:
        for index, record in enumerate(rows):
            logical_records.append(
                (record, record, f"{base}/{index}", None)
            )
    else:
        if (
            not isinstance(record_array_path, str)
            or not record_array_path.startswith("/")
            or record_array_path == "/"
        ):
            raise JsonTransformError("Invalid record array path.")

        parts = record_array_path[1:].split("/")
        if any(not part or part == "[]" for part in parts):
            raise JsonTransformError("Invalid record array path.")

        decoded_parts = [_unescape(part) for part in parts]
        record_prefix = record_array_path + "/[]"

        single_root = (
            str(extension).lower().lstrip(".") == "json"
            and base == ""
            and data.decode("utf-8-sig").lstrip().startswith("{")
        )

        for root_index, root_record in enumerate(rows):
            current = root_record

            for part in decoded_parts:
                if not isinstance(current, dict) or part not in current:
                    raise JsonTransformError(
                        "Approved record array path not found."
                    )
                current = current[part]

            if not isinstance(current, list):
                raise JsonTransformError(
                    "Approved record path is not an array."
                )

            root_pointer = (
                "" if single_root else f"{base}/{root_index}"
            )

            for child_index, child in enumerate(current):
                if not isinstance(child, dict):
                    raise JsonTransformError(
                        "Logical record array must contain objects."
                    )

                logical_records.append((
                    root_record,
                    child,
                    f"{root_pointer}{record_array_path}/{child_index}",
                    record_prefix,
                ))

                if len(logical_records) > 100000:
                    raise JsonTransformError(
                        "Logical record limit exceeded."
                    )

        if not logical_records:
            raise JsonTransformError(
                "Approved record array contains no records."
            )

    if not isinstance(include_all_rows, bool):
        raise JsonTransformError("Invalid full-row request.")

    # Bound in-memory generation until the existing Azure
    # processing expansion supports partitioned CSV writes.
    if include_all_rows and len(logical_records) > 10000:
        raise JsonTransformError(
            "Full-row construction exceeds bounded limit."
        )

    preview = []
    all_rows = []
    row_source_pointers = []

    for index, (root, record, source_pointer, prefix) in enumerate(
        logical_records
    ):
        mapped = {}

        for column in plan["columns"]:
            pointer = column["json_pointer"]

            if prefix is not None and pointer.startswith(prefix + "/"):
                values = _values(record, pointer[len(prefix):])
            elif prefix is not None and pointer.startswith(
                record_array_path + "/"
            ):
                raise JsonTransformError(
                    "Field path cannot be resolved at record boundary."
                )
            else:
                values = _values(root, pointer)

            mapped[column["output_header"]] = _treat(
                values,
                column["data_treatment"],
            )

        if include_all_rows:
            all_rows.append([
                mapped[header] for header in plan["output_headers"]
            ])
            row_source_pointers.append(source_pointer)

        if index < preview_limit:
            preview.append({
                "record_index": index,
                "source_pointer": source_pointer,
                "values": mapped,
            })

    return {
        "source_sha256": expected_sha256,
        "record_count": len(logical_records),
        "validated_record_count": len(logical_records),
        "source_container_record_count": len(rows),
        "record_array_path": record_array_path,
        "validation_complete": True,
        "output_headers": plan["output_headers"],
        "columns": plan["columns"],
        "preview": preview,
        "preview_truncated": len(logical_records) > len(preview),
        "all_rows": (
            [list(plan["output_headers"])] + all_rows
            if include_all_rows else None
        ),
        "row_source_pointers": (
            row_source_pointers if include_all_rows else None
        ),
        "source_modified": False,
        "csv_generated": False,
        "mapping_saved": False,
    }

def construct_approved_json_csv_rows(
    data,
    extension,
    approved_document,
    protocol_headers,
    expected_sha256,
    *,
    record_array_path=None,
):
    """Prepare verified JSON-derived rows for the existing CSV writer.

    The caller must verify the approved mapping status, project
    authorization, and registered native source path before calling.
    No storage or approval operations occur here.
    """
    if not isinstance(approved_document, dict):
        raise JsonTransformError("Invalid approved JSON document.")

    if approved_document.get("source_kind") != "native_json":
        raise JsonTransformError("Native JSON source required.")

    doc_id = str(approved_document.get("doc_id") or "").strip()
    native_path = str(
        approved_document.get("source_native_path") or ""
    ).strip()

    source_hash = str(
        approved_document.get("source_sha256") or ""
    ).lower()

    source_format = str(
        approved_document.get("source_format") or ""
    ).lower().lstrip(".")

    extension = str(extension).lower().lstrip(".")

    if not doc_id or not native_path:
        raise JsonTransformError("Native source identity missing.")

    if (
        source_format != extension
        or extension not in {"json", "jsonl", "ndjson"}
    ):
        raise JsonTransformError("Native source format mismatch.")

    if (
        not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or source_hash != expected_sha256
        or hashlib.sha256(data).hexdigest() != expected_sha256
    ):
        raise JsonTransformError("Native source integrity mismatch.")

    try:
        evidence = discover_json_header_evidence(data, extension)
    except JsonEvidenceError as exc:
        raise JsonTransformError(str(exc)) from exc

    decisions = decisions_from_approved_json_mapping(
        approved_document,
        evidence,
        protocol_headers,
    )

    retained_paths = [
        item["json_pointer"]
        for item in decisions
        if item["action"] != "discard"
    ]

    if record_array_path is None and any(
        "/[]/" in path for path in retained_paths
    ):
        raise JsonTransformError(
            "Nested array fields require an explicit record boundary."
        )

    result = preview_json_mapped_rows(
        data,
        extension,
        decisions,
        protocol_headers,
        expected_sha256,
        record_array_path=record_array_path,
        include_all_rows=True,
    )

    rows = result["all_rows"]
    headers = result["output_headers"]
    pointers = result["row_source_pointers"]

    if (
        not result["validation_complete"]
        or not isinstance(rows, list)
        or len(rows) != result["validated_record_count"] + 1
        or rows[0] != headers
        or len(pointers) != result["validated_record_count"]
        or any(len(row) != len(headers) for row in rows)
    ):
        raise JsonTransformError("Incomplete constructed CSV rows.")

    approved_columns = approved_document.get("columns")
    if not isinstance(approved_columns, list):
        raise JsonTransformError("Approved column lineage missing.")

    by_pointer = {}

    for column in approved_columns:
        if not isinstance(column, dict):
            raise JsonTransformError("Invalid column lineage.")

        pointer = column.get("json_pointer")
        index = column.get("column_index")

        if (
            not isinstance(pointer, str)
            or not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or pointer in by_pointer
        ):
            raise JsonTransformError("Invalid source column identity.")

        by_pointer[pointer] = column

    lineage = []

    for output_index, output_column in enumerate(result["columns"]):
        pointer = output_column["json_pointer"]
        original = by_pointer.get(pointer)

        if original is None:
            raise JsonTransformError("Missing approved column lineage.")

        lineage.append({
            "output_column_index": output_index,
            "source_column_index": original["column_index"],
            "source_header": str(original.get("source_header") or ""),
            "canonical_header": str(
                original.get("final_header") or ""
            ),
            "output_header": output_column["output_header"],
            "mapped_to_protocol": bool(
                original.get("mapped_to_protocol", False)
            ),
            "json_pointer": pointer,
        })

    return {
        "doc_id": doc_id,
        "source_kind": "native_json",
        "source_native_path": native_path,
        "source_sha256": source_hash,
        "source_format": source_format,
        "record_array_path": record_array_path,
        "rows": rows,
        "output_headers": headers,
        "column_lineage": lineage,
        "row_source_pointers": pointers,
        "source_row_count": result["record_count"],
        "mapped_row_count": result["validated_record_count"],
        "source_column_count": len(approved_columns),
        "mapped_column_count": len(headers),
        "source_modified": False,
    }
