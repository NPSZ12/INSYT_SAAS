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


def preview_json_mapped_rows(
    data,
    extension,
    decisions,
    protocol_headers,
    expected_sha256,
    *,
    preview_limit=25,
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

    preview = []
    for index, record in enumerate(rows):
        mapped = {}
        for column in plan["columns"]:
            mapped[column["output_header"]] = _treat(
                _values(record, column["json_pointer"]),
                column["data_treatment"],
            )
        if index < preview_limit:
            preview.append({
                "record_index": index,
                "source_pointer": f"{base}/{index}",
                "values": mapped,
            })

    return {
        "source_sha256": expected_sha256,
        "record_count": len(rows),
        "validated_record_count": len(rows),
        "validation_complete": True,
        "output_headers": plan["output_headers"],
        "columns": plan["columns"],
        "preview": preview,
        "preview_truncated": len(rows) > len(preview),
        "source_modified": False,
        "csv_generated": False,
        "mapping_saved": False,
    }