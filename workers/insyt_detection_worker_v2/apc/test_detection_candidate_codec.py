import json
from dataclasses import asdict

import pytest

from apc.detection.models import DetectionCandidate
from apc.detection_candidate_codec import (
    serialize_detection_candidate,
    deserialize_detection_candidate,
    serialize_candidate_batch,
    deserialize_candidate_batch,
)


def _candidate():
    return DetectionCandidate(
        entity_type="IdentificationNumber",
        entity_subtype="SSN",
        detected_value="123-45-6789",
        normalized_value="123456789",
        masked_value="***-**-6789",
        start_offset=8,
        end_offset=19,
        confidence=0.98,
        detector_name="synthetic_detector",
        detector_version="test-v1",
        detection_rule="test-rule",
        protocol_name="Capture Rules",
        protocol_version="test-protocol",
        reportability="REPORTABLE",
        page_number=None,
        methods=["regex", "validation"],
        context_terms=["SSN"],
        validation_status="validated",
        validation_method="synthetic",
        metadata={
            "worksheet_profile": True,
            "profile_first_hit_row": 25,
            "nested": {"source": "synthetic"},
        },
    )


def test_candidate_roundtrip_preserves_every_field():
    original = _candidate()

    record = serialize_detection_candidate(
        original,
        chunk_length=100,
    )

    restored = deserialize_detection_candidate(
        record,
        chunk_length=100,
    )

    assert asdict(restored) == asdict(original)


def test_json_roundtrip_preserves_metadata():
    candidate = _candidate()

    payload = serialize_candidate_batch(
        [candidate],
        chunk_length=100,
    )

    restored = deserialize_candidate_batch(
        json.loads(json.dumps(payload)),
        chunk_length=100,
    )

    assert restored == [candidate]


def test_multiple_candidates_preserved():
    first = _candidate()

    second = DetectionCandidate(
        entity_type="Email",
        detected_value="a@example.test",
        start_offset=30,
        end_offset=44,
        methods=["regex"],
    )

    payload = serialize_candidate_batch(
        [first, second],
        chunk_length=100,
    )

    restored = deserialize_candidate_batch(
        payload,
        chunk_length=100,
    )

    assert restored == [first, second]


def test_empty_candidate_batch_roundtrip():
    payload = serialize_candidate_batch(
        [],
        chunk_length=0,
    )

    assert deserialize_candidate_batch(
        payload,
        chunk_length=0,
    ) == []


def test_out_of_bounds_candidate_rejected():
    candidate = _candidate()

    with pytest.raises(ValueError):
        serialize_detection_candidate(
            candidate,
            chunk_length=10,
        )


def test_missing_candidate_field_rejected():
    record = serialize_detection_candidate(
        _candidate(),
        chunk_length=100,
    )

    del record["entity_subtype"]

    with pytest.raises(ValueError):
        deserialize_detection_candidate(
            record,
            chunk_length=100,
        )


def test_extra_candidate_field_rejected():
    record = serialize_detection_candidate(
        _candidate(),
        chunk_length=100,
    )

    record["unexpected_field"] = "invalid"

    with pytest.raises(ValueError):
        deserialize_detection_candidate(
            record,
            chunk_length=100,
        )


def test_unsupported_codec_version_rejected():
    payload = serialize_candidate_batch(
        [_candidate()],
        chunk_length=100,
    )

    payload["codec_version"] = 999

    with pytest.raises(ValueError):
        deserialize_candidate_batch(
            payload,
            chunk_length=100,
        )


def test_malformed_metadata_rejected():
    record = serialize_detection_candidate(
        _candidate(),
        chunk_length=100,
    )

    record["metadata"] = "not-a-dictionary"

    with pytest.raises(ValueError):
        deserialize_detection_candidate(
            record,
            chunk_length=100,
        )


def test_non_json_metadata_rejected():
    candidate = _candidate()
    candidate.metadata["invalid"] = {1, 2, 3}

    with pytest.raises(TypeError):
        serialize_detection_candidate(
            candidate,
            chunk_length=100,
        )