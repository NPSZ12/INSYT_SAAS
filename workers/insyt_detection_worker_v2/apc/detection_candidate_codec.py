from __future__ import annotations

import json
from dataclasses import asdict, fields
from typing import Any

from .detection.models import DetectionCandidate


CANDIDATE_CODEC_VERSION = 1

CANDIDATE_FIELDS = frozenset(
    field.name for field in fields(DetectionCandidate)
)


def serialize_detection_candidate(
    candidate: DetectionCandidate,
    *,
    chunk_length: int,
) -> dict[str, Any]:
    """
    Serialize one validated candidate with chunk-local offsets.

    All DetectionCandidate fields are retained.
    """
    if not isinstance(candidate, DetectionCandidate):
        raise TypeError("Expected DetectionCandidate.")

    if chunk_length < 0:
        raise ValueError("Invalid chunk length.")

    if (
        type(candidate.start_offset) is not int
        or type(candidate.end_offset) is not int
        or candidate.start_offset < 0
        or candidate.end_offset <= candidate.start_offset
        or candidate.end_offset > chunk_length
    ):
        raise ValueError(
            "Candidate offsets are outside the worksheet chunk."
        )

    record = asdict(candidate)

    if set(record) != CANDIDATE_FIELDS:
        raise ValueError("Candidate field schema mismatch.")

    # Round-trip through strict JSON to prevent silent
    # serialization of unsupported metadata types.
    encoded = json.dumps(
        record,
        allow_nan=False,
        ensure_ascii=False,
    )

    return json.loads(encoded)


def deserialize_detection_candidate(
    record: dict[str, Any],
    *,
    chunk_length: int,
) -> DetectionCandidate:
    """
    Restore a candidate using the existing INSYT model.

    Reject missing, additional or malformed fields instead
    of silently producing incomplete detection evidence.
    """
    if not isinstance(record, dict):
        raise ValueError("Candidate record must be an object.")

    if set(record) != CANDIDATE_FIELDS:
        raise ValueError("Candidate field schema mismatch.")

    if (
        type(record["start_offset"]) is not int
        or type(record["end_offset"]) is not int
        or record["start_offset"] < 0
        or record["end_offset"] <= record["start_offset"]
        or record["end_offset"] > chunk_length
    ):
        raise ValueError("Invalid candidate offsets.")

    if (
        not isinstance(record["entity_type"], str)
        or not isinstance(record["detected_value"], str)
        or not isinstance(record["methods"], list)
        or not all(
            isinstance(item, str)
            for item in record["methods"]
        )
        or not isinstance(record["context_terms"], list)
        or not all(
            isinstance(item, str)
            for item in record["context_terms"]
        )
        or not isinstance(record["metadata"], dict)
    ):
        raise ValueError("Malformed candidate fields.")

    if (
        record["page_number"] is not None
        and type(record["page_number"]) is not int
    ):
        raise ValueError("Invalid candidate page number.")

    if (
        isinstance(record["confidence"], bool)
        or not isinstance(
            record["confidence"], (int, float)
        )
    ):
        raise ValueError("Invalid candidate confidence.")

    candidate = DetectionCandidate(**record)

    # Verify JSON compatibility and schema one more time.
    serialize_detection_candidate(
        candidate,
        chunk_length=chunk_length,
    )

    return candidate


def serialize_candidate_batch(
    candidates: list[DetectionCandidate],
    *,
    chunk_length: int,
) -> dict[str, Any]:
    return {
        "codec_version": CANDIDATE_CODEC_VERSION,
        "candidates": [
            serialize_detection_candidate(
                candidate,
                chunk_length=chunk_length,
            )
            for candidate in candidates
        ],
    }


def deserialize_candidate_batch(
    payload: dict[str, Any],
    *,
    chunk_length: int,
) -> list[DetectionCandidate]:
    if not isinstance(payload, dict):
        raise ValueError("Candidate batch must be an object.")

    if set(payload) != {"codec_version", "candidates"}:
        raise ValueError("Candidate batch schema mismatch.")

    if payload["codec_version"] != CANDIDATE_CODEC_VERSION:
        raise ValueError("Unsupported candidate codec version.")

    if not isinstance(payload["candidates"], list):
        raise ValueError("Candidates must be a list.")

    return [
        deserialize_detection_candidate(
            record,
            chunk_length=chunk_length,
        )
        for record in payload["candidates"]
    ]