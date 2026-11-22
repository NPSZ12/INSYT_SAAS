"""Adapt JSON evidence to Cyber2 Headers & Schema review rows.

This module does not invoke AI, approve mappings, or create CSV.
"""

import re

TREATMENTS = (
    "text",
    "concatenate",
    "mask",
    "yes_if_present",
    "maximum",
    "latest",
    "discard",
)


class JsonHeaderReviewError(ValueError):
    pass


def _normalized_header(value):
    return re.sub(
        r"[\s_-]+", " ", str(value).strip()
    ).casefold()


def build_json_header_review(
    evidence,
    protocol_headers,
):
    """Produce review columns compatible with existing CSV evidence."""

    if not isinstance(evidence, dict):
        raise JsonHeaderReviewError("Invalid JSON evidence.")

    if evidence.get("structure_scan_complete") is not True:
        raise JsonHeaderReviewError(
            "Complete JSON structure evidence is required."
        )

    source_hash = str(evidence.get("source_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise JsonHeaderReviewError("Invalid source hash.")

    fields = evidence.get("fields")

    if not isinstance(fields, list) or not fields:
        raise JsonHeaderReviewError("No JSON fields available.")

    if not isinstance(protocol_headers, list):
        raise JsonHeaderReviewError("Invalid protocol headers.")

    if not protocol_headers:
        raise JsonHeaderReviewError(
            "Approved client protocol headers are required."
        )

    if len(protocol_headers) > 1000:
        raise JsonHeaderReviewError("Protocol header limit exceeded.")

    approved = {}
    ordered_headers = []

    for value in protocol_headers:
        if not isinstance(value, str):
            raise JsonHeaderReviewError(
                "Protocol headers must be strings."
            )

        header = value.strip()
        normalized = _normalized_header(header)

        if (
            not header
            or len(header) > 128
            or any(ch in header for ch in "\r\n\x00")
            or normalized in approved
        ):
            raise JsonHeaderReviewError(
                "Invalid or duplicate approved protocol header."
            )

        approved[normalized] = header
        ordered_headers.append(header)

    rows = []
    used_paths = set()

    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise JsonHeaderReviewError("Invalid field evidence.")

        pointer = field.get("json_pointer")
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise JsonHeaderReviewError("Invalid JSON field path.")

        if pointer in used_paths:
            raise JsonHeaderReviewError(
                "Duplicate JSON field path."
            )
        used_paths.add(pointer)

        kind = field.get("kind")
        if kind not in {"scalar", "array", "object", "mixed"}:
            raise JsonHeaderReviewError("Invalid field kind.")

        source_path = str(
            field.get("source_path") or pointer
        )

        samples = field.get("sample_values")
        if not isinstance(samples, list):
            raise JsonHeaderReviewError("Invalid sample data.")

        if len(samples) > 10:
            raise JsonHeaderReviewError(
                "Sample count exceeds allowed limit."
            )

        # Only exact approved protocol names get a lexical suggestion.
        # Structural JSON parents are never silently treated as CSV text.
        exact = None
        match_method = "needs_ai_review"

        if kind == "scalar":
            # Match the full path first, then the final JSON field.
            # Keep source_path and json_pointer unchanged.
            full_key = _normalized_header(source_path)
            leaf = source_path.rsplit(".", 1)[-1]
            leaf_key = _normalized_header(leaf)

            candidate_keys = {full_key, leaf_key}

            # Common unambiguous abbreviation.
            if leaf_key == "ssn":
                candidate_keys.add("social security number")

            matches = {
                approved[key]
                for key in candidate_keys
                if key in approved
            }

            # Never arbitrarily select between protocol headers.
            if len(matches) == 1:
                exact = next(iter(matches))
                if approved.get(full_key) == exact:
                    match_method = "protocol_exact"
                elif approved.get(leaf_key) == exact:
                    match_method = "protocol_leaf"
                else:
                    match_method = "protocol_alias"

        # Deterministic recommendations are not approval decisions.
        if match_method in {"protocol_exact", "protocol_leaf"}:
            deterministic_confidence = 1.0
        elif match_method == "protocol_alias":
            deterministic_confidence = 0.95
        else:
            deterministic_confidence = None

        rows.append({
            "column_index": index,
            "column_number": index + 1,
            "source_header": source_path,
            "json_pointer": pointer,
            "json_kind": kind,
            "sample_values": [
                str(value) for value in samples
            ],
            "sample_count": len(samples),
            "source_pointers": list(
                field.get("sample_source_pointers") or []
            ),
            "record_count_with_field": int(
                field.get("record_count_with_field") or 0
            ),
            "record_count_without_field": int(
                field.get("record_count_without_field") or 0
            ),
            "occurrence_count": int(
                field.get("occurrence_count") or 0
            ),
            "recommended_protocol_header": exact,
            "match_method": (
                match_method
            ),
            "mapping_confidence": deterministic_confidence,
            "ai_confidence": None,
            "ai_invoked": False,
            "ai_review_required": exact is None,
            "default_disposition": "delete",
            "proposed_final_header": exact or "",
            "approved": False,
            "data_treatment": None,
            "allowed_data_treatments": list(TREATMENTS),
        })

    return {
        "source_kind": "native_json",
        "source_sha256": source_hash,
        "protocol_headers": ordered_headers,
        "record_count": evidence.get("record_count"),
        "columns": rows,
        "field_count": len(rows),
        "requires_reviewer_approval": True,
        "ai_invoked": False,
        "mapping_approved": False,
        "csv_generated": False,
    }