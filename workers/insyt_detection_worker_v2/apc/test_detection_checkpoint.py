import pytest

from apc.detection_checkpoint import (
    CHECKPOINT_COMPLETED,
    CHECKPOINT_PENDING,
    DetectionCheckpoint,
)


def _checkpoint(**overrides):
    values = {
        "detection_job_id": "DET-TEST001",
        "doc_id": "INSYT000000001",
        "unit_id": "chunk-000001",
        "protocol_fingerprint": "sha256:test",
    }
    values.update(overrides)
    return DetectionCheckpoint(**values)


def test_pending_checkpoint_is_not_reusable():
    checkpoint = _checkpoint(
        state=CHECKPOINT_PENDING,
    )
    assert checkpoint.reusable is False


def test_completed_checkpoint_requires_artifact():
    with pytest.raises(ValueError):
        _checkpoint(
            state=CHECKPOINT_COMPLETED,
            completed_at="2026-11-06T12:00:00Z",
        )


def test_completed_checkpoint_is_reusable():
    checkpoint = _checkpoint(
        state=CHECKPOINT_COMPLETED,
        result_blob_path="results/chunk-000001.json",
        completed_at="2026-11-06T12:00:00Z",
    )

    assert checkpoint.reusable is True


def test_checkpoint_json_roundtrip():
    original = _checkpoint(
        state=CHECKPOINT_COMPLETED,
        attempt=2,
        result_blob_path="results/chunk-000001.json",
        completed_at="2026-11-06T12:00:00Z",
    )

    restored = DetectionCheckpoint.from_dict(
        original.to_dict()
    )

    assert restored == original


def test_invalid_checkpoint_state_rejected():
    with pytest.raises(ValueError):
        _checkpoint(state="unknown")


def test_missing_protocol_fingerprint_rejected():
    with pytest.raises(ValueError):
        _checkpoint(protocol_fingerprint="")


def test_unsupported_schema_version_rejected():
    value = _checkpoint().to_dict()
    value["schema_version"] = 999

    with pytest.raises(ValueError):
        DetectionCheckpoint.from_dict(value)

def test_checkpoint_reuse_requires_matching_identity():
    from apc.detection_checkpoint import checkpoint_is_reusable_for

    checkpoint = _checkpoint(
        state=CHECKPOINT_COMPLETED,
        result_blob_path="results/chunk-000001.json",
        completed_at="2026-11-06T12:00:00Z",
    )

    expected = {
        "detection_job_id": "DET-TEST001",
        "doc_id": "INSYT000000001",
        "unit_id": "chunk-000001",
        "protocol_fingerprint": "sha256:test",
        "artifact_exists": True,
    }

    assert checkpoint_is_reusable_for(
        checkpoint, **expected
    )

    for field, wrong_value in (
        ("detection_job_id", "DET-OTHER"),
        ("doc_id", "INSYT000000002"),
        ("unit_id", "chunk-000002"),
        ("protocol_fingerprint", "sha256:changed"),
        ("artifact_exists", False),
    ):
        invalid = dict(expected)
        invalid[field] = wrong_value

        assert not checkpoint_is_reusable_for(
            checkpoint, **invalid
        )


def test_pending_checkpoint_cannot_be_reused():
    from apc.detection_checkpoint import checkpoint_is_reusable_for

    checkpoint = _checkpoint(state=CHECKPOINT_PENDING)

    assert not checkpoint_is_reusable_for(
        checkpoint,
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id="chunk-000001",
        protocol_fingerprint="sha256:test",
        artifact_exists=True,
    )