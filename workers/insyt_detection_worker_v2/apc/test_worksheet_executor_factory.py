from dataclasses import replace

import pytest

from apc.detection.rules import DetectionRule
from apc.worksheet_executor_factory import (
    make_worksheet_executor_factory,
)


def rules():
    return [
        DetectionRule(
            rule_id="TEST_EMAIL",
            entity_type="Email",
            regex_pattern=r"\b\S+@\S+\b",
        )
    ]


def build_factory():
    return make_worksheet_executor_factory(
        store=object(),
        detection_job_id="DET-TEST001",
        engine=lambda text, **kwargs: {
            "candidates": [],
            "azure_candidate_count": 0,
            "structured_candidate_count": 0,
            "merged_candidate_count": 0,
        },
    )


def make_executor(factory, **changes):
    options = {
        "doc_id": "INSYT000000001",
        "workspace": "capture",
        "structured_rules": rules(),
        "rule_source": "capture/test_rules.xlsx",
        "selected_sheets": ("PII",),
        "include_phi": True,
        "enable_azure": True,
        "protocol_name": "Capture Rules",
        "protocol_version": "v1",
    }

    options.update(changes)
    return factory(**options)


def test_factory_preserves_document_identity():
    executor = make_executor(build_factory())

    assert executor.detection_job_id == "DET-TEST001"
    assert executor.doc_id == "INSYT000000001"
    assert executor.detection_mode == "worksheet_triage"


def test_factory_preserves_protocol_and_settings():
    executor = make_executor(build_factory())

    assert executor.protocol_name == "Capture Rules"
    assert executor.protocol_version == "v1"
    assert executor.include_phi is True
    assert executor.enable_azure is True


def test_same_effective_rules_have_same_identity():
    factory = build_factory()

    first = make_executor(factory)
    second = make_executor(factory)

    assert (
        first.protocol_fingerprint
        == second.protocol_fingerprint
    )


def test_rule_change_invalidates_identity():
    factory = build_factory()

    original = make_executor(factory)

    changed_rules = rules()
    changed_rules[0] = replace(
        changed_rules[0],
        regex_pattern=r"\bchanged@\S+\b",
    )

    changed = make_executor(
        factory,
        structured_rules=changed_rules,
    )

    assert (
        original.protocol_fingerprint
        != changed.protocol_fingerprint
    )


def test_capture_fallback_uses_builtin_rules():
    executor = make_executor(
        build_factory(),
        structured_rules=None,
        rule_source="built_in_rules_fallback",
    )

    assert executor.structured_rules is None
    assert executor.protocol_fingerprint.startswith("sha256:")


def test_discovery_rejects_capture_fallback():
    with pytest.raises(ValueError):
        make_executor(
            build_factory(),
            workspace="discovery",
            structured_rules=None,
            rule_source="built_in_rules_fallback",
        )


def test_discovery_retains_own_detection_settings():
    executor = make_executor(
        build_factory(),
        workspace="discovery",
        rule_source="discovery/test_rules.xlsx",
        include_phi=False,
        enable_azure=False,
    )

    assert executor.include_phi is False
    assert executor.enable_azure is False


def test_missing_document_id_rejected():
    with pytest.raises(ValueError):
        make_executor(
            build_factory(),
            doc_id="",
        )


def test_missing_job_id_rejected():
    with pytest.raises(ValueError):
        make_worksheet_executor_factory(
            store=object(),
            detection_job_id="",
        )


def test_rules_are_materialized_once():
    factory = build_factory()

    supplied = (rule for rule in rules())

    executor = make_executor(
        factory,
        structured_rules=supplied,
    )

    assert len(executor.structured_rules) == 1