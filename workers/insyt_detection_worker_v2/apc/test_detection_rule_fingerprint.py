from dataclasses import replace

import pytest

from apc.detection.rules import DetectionRule
from apc.detection_rule_fingerprint import (
    effective_rule_fingerprint,
)


def _rules():
    return [
        DetectionRule(
            rule_id="TEST_EMAIL",
            entity_type="Email",
            regex_pattern=r"\b\S+@\S+\b",
            context_terms=("email",),
            validator="email",
        ),
        DetectionRule(
            rule_id="TEST_SSN",
            entity_type="IdentificationNumber",
            entity_subtype="SSN",
            regex_pattern=r"\b\d{3}-\d{2}-\d{4}\b",
            validator="us_ssn",
        ),
    ]


def _fingerprint(**overrides):
    values = {
        "workspace": "capture",
        "structured_rules": _rules(),
        "rule_source": "capture/test_rules.xlsx",
        "selected_sheets": ["PII"],
    }

    values.update(overrides)

    return effective_rule_fingerprint(**values)


def test_fingerprint_is_deterministic():
    assert _fingerprint() == _fingerprint()


def test_regex_change_invalidates_fingerprint():
    rules = _rules()
    rules[0] = replace(
        rules[0],
        regex_pattern=r"\bupdated@\S+\b",
    )

    assert _fingerprint() != _fingerprint(
        structured_rules=rules
    )


def test_validator_and_enabled_changes_invalidate():
    original = _fingerprint()

    for change in (
        {"validator": "different"},
        {"enabled": False},
        {"base_confidence": 0.91},
        {"metadata": {"revision": 2}},
    ):
        rules = _rules()
        rules[0] = replace(rules[0], **change)

        assert original != _fingerprint(
            structured_rules=rules
        )


def test_rule_order_changes_fingerprint():
    assert _fingerprint() != _fingerprint(
        structured_rules=list(reversed(_rules()))
    )


def test_workspace_and_sheet_selection_are_isolated():
    original = _fingerprint()

    assert original != _fingerprint(
        workspace="discovery",
        rule_source="discovery/test_rules.xlsx",
    )

    assert original != _fingerprint(
        selected_sheets=["PHI"]
    )


def test_capture_builtin_fallback_is_deterministic():
    options = {
        "workspace": "capture",
        "structured_rules": None,
        "rule_source": "built_in_rules_fallback",
    }

    first = effective_rule_fingerprint(**options)
    second = effective_rule_fingerprint(**options)

    assert first == second
    assert first.startswith("sha256:")


def test_discovery_cannot_use_capture_fallback():
    with pytest.raises(ValueError):
        effective_rule_fingerprint(
            workspace="discovery",
            structured_rules=None,
            rule_source="built_in_rules_fallback",
        )


def test_missing_capture_rules_cannot_silently_fallback():
    with pytest.raises(ValueError):
        _fingerprint(structured_rules=None)


def test_discovery_rejects_empty_rules():
    with pytest.raises(ValueError):
        effective_rule_fingerprint(
            workspace="discovery",
            structured_rules=[],
            rule_source="discovery/test_rules.xlsx",
        )


def test_invalid_rule_metadata_is_rejected():
    rules = _rules()
    rules[0] = replace(
        rules[0],
        metadata={"invalid": {1, 2, 3}},
    )

    with pytest.raises(TypeError):
        _fingerprint(structured_rules=rules)