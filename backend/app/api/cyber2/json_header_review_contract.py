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
        exact = (
            approved.get(_normalized_header(source_path))
            if kind == "scalar" else None
        )

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
                "protocol_exact" if exact else "needs_ai_review"
            ),
            "mapping_confidence": None,
            "ai_confidence": None,
            "ai_invoked": False,
            "ai_review_required": True,
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

def _redacted_ai_sample(value):
    """Provide semantic evidence without transmitting source PII."""
    import re

    text = str(value or "").strip()

    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        return "<EMAIL>"

    if re.fullmatch(r"\d{3}-\d{2}-\d{4}", text):
        return "<SSN>"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "<DATE>"

    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return "<NUMBER>"

    return "<REDACTED_TEXT>"


def enrich_json_header_review_with_ai(
    review,
    *,
    ai_resolver,
    max_fields=50,
):
    """Attach protocol-bound AI suggestions; never approve or save."""
    if not isinstance(review, dict):
        raise JsonHeaderReviewError("Invalid JSON header review.")

    columns = review.get("columns")
    protocol = review.get("protocol_headers")

    if not isinstance(columns, list) or not isinstance(protocol, list):
        raise JsonHeaderReviewError("Invalid JSON mapping evidence.")

    if len(columns) > max_fields:
        raise JsonHeaderReviewError(
            "Too many JSON fields for one bounded AI suggestion request."
        )

    approved = set(protocol)
    invoked = 0

    for column in columns:
        if column.get("json_kind") != "scalar":
            continue

        # Exact protocol matches already have a deterministic suggestion.
        if column.get("recommended_protocol_header"):
            continue

        samples = [
            _redacted_ai_sample(value)
            for value in (column.get("sample_values") or [])[:3]
        ]

        semantic_type = ""
        if "<EMAIL>" in samples:
            semantic_type = "email"
        elif "<SSN>" in samples:
            semantic_type = "ssn"
        elif "<DATE>" in samples:
            semantic_type = "date"

        result = ai_resolver(
            source_header=str(
                column.get("source_header") or ""
            ),
            sample_values=samples,
            semantic_type=semantic_type,
            deterministic_recommendation="",
            deterministic_confidence=0.0,
            protocol_headers=list(protocol),
        )

        invoked += 1

        recommendation = str(
            result.get("ai_recommendation") or ""
        ).strip()

        confidence = result.get("ai_confidence")
        status = str(result.get("ai_status") or "")

        # The protocol remains authoritative, even if the AI
        # provider returned an unexpected recommendation.
        if recommendation not in approved:
            recommendation = ""

        column["ai_invoked"] = bool(
            result.get("ai_invoked")
        )
        column["ai_status"] = status
        column["ai_recommendation"] = recommendation
        column["ai_confidence"] = confidence
        column["ai_reason"] = str(
            result.get("ai_reason") or ""
        )

        if (
            status == "completed"
            and recommendation
            and isinstance(confidence, (float, int))
            and not isinstance(confidence, bool)
            and 0.70 <= confidence <= 1.0
        ):
            column["recommended_protocol_header"] = recommendation
            column["mapping_confidence"] = float(confidence)
            column["match_method"] = "ai_assisted"

        # Every field remains unapproved, regardless of confidence.
        column["approved"] = False

    review["ai_invoked"] = invoked > 0
    review["ai_suggestion_fields_evaluated"] = invoked
    review["mapping_approved"] = False
    review["csv_generated"] = False

    return review
