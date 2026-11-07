from dataclasses import replace

import pytest

from apc.detection_checkpoint import (
    CHECKPOINT_COMPLETED,
    DetectionCheckpoint,
    checkpoint_is_reusable_for,
)
from apc.detection_unit_identity import (
    worksheet_detection_fingerprint,
)
from apc.worksheet_work_units import (
    iter_worksheet_work_units,
)


def _unit(tmp_path):
    path = tmp_path / "worksheet.csv"
    path.write_text(
        "name,email\nJane,jane@example.test\n",
        encoding="utf-8",
        newline="\n",
    )

    return next(
        iter_worksheet_work_units(path)
    )


def _fingerprint(unit, **overrides):
    options = {
        "protocol_fingerprint": "sha256:protocol-v1",
        "detection_mode": "worksheet_triage",
        "include_phi": True,
        "enable_azure": True,
        "enable_structured_rules": True,
    }
    options.update(overrides)

    return worksheet_detection_fingerprint(
        unit,
        **options,
    )


def test_identity_is_deterministic(tmp_path):
    unit = _unit(tmp_path)

    assert _fingerprint(unit) == _fingerprint(unit)


def test_changed_protocol_invalidates_identity(tmp_path):
    unit = _unit(tmp_path)

    assert _fingerprint(unit) != _fingerprint(
        unit,
        protocol_fingerprint="sha256:protocol-v2",
    )


def test_changed_detection_settings_invalidate_identity(tmp_path):
    unit = _unit(tmp_path)
    original = _fingerprint(unit)

    for setting, changed in (
        ("include_phi", False),
        ("enable_azure", False),
        ("enable_structured_rules", False),
        ("detection_mode", "full"),
    ):
        assert original != _fingerprint(
            unit,
            **{setting: changed},
        )


def test_changed_source_text_invalidates_identity(tmp_path):
    unit = _unit(tmp_path)

    changed_text = unit.text.replace(
        "Jane",
        "Joan",
    )

    import hashlib

    changed_unit = replace(
        unit,
        text=changed_text,
        text_sha256=hashlib.sha256(
            changed_text.encode("utf-8")
        ).hexdigest(),
    )

    assert _fingerprint(unit) != _fingerprint(
        changed_unit
    )


def test_tampered_chunk_hash_is_rejected(tmp_path):
    unit = _unit(tmp_path)

    with pytest.raises(ValueError):
        _fingerprint(
            replace(unit, text_sha256="invalid")
        )


def test_changed_chunk_position_invalidates_identity(tmp_path):
    unit = _unit(tmp_path)

    shifted = replace(
        unit,
        start_row=unit.start_row + 10,
        end_row=unit.end_row + 10,
        start_offset=unit.start_offset + 100,
        end_offset=unit.end_offset + 100,
    )

    assert _fingerprint(unit) != _fingerprint(
        shifted
    )


def test_checkpoint_reuse_rejects_changed_input(tmp_path):
    unit = _unit(tmp_path)

    original_fingerprint = _fingerprint(unit)

    checkpoint = DetectionCheckpoint(
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id=unit.unit_id,
        protocol_fingerprint=original_fingerprint,
        state=CHECKPOINT_COMPLETED,
        result_blob_path="synthetic/result.json",
        completed_at="2026-11-06T12:00:00Z",
    )

    assert checkpoint_is_reusable_for(
        checkpoint,
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id=unit.unit_id,
        protocol_fingerprint=original_fingerprint,
        artifact_exists=True,
    )

    assert not checkpoint_is_reusable_for(
        checkpoint,
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id=unit.unit_id,
        protocol_fingerprint=_fingerprint(
            unit,
            include_phi=False,
        ),
        artifact_exists=True,
    )