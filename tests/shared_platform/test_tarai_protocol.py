import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ai.tarai_protocol import (
    TARaiProtocolError,
    resolve_privilege_fields,
)


def field(section, label, fmt="Tag"):
    return {
        "section": section,
        "data_element": label,
        "format": fmt,
    }


DISCOVERY_FIELDS = [
    field("Document Coding", "Responsive"),
    field("Privilege Status", "Not Privileged"),
    field("Privilege Status", "Privileged"),
    field("Confidentiality", "Confidential"),
    field("Responsiveness", "Responsive"),
    field("Responsiveness", "Responsive Family"),
    field("Responsiveness", "Non-Responsive"),
    field("Responsiveness", "Tech Issue"),
    field("Privilege", "Privileged"),
    field("Privilege", "Not Privileged"),
    field("Confidentiality", "AEO"),
    field("Confidentiality", "Confidential"),
    field("Confidentiality", "Not Confidential (Public)"),
    field("Issues", "Request 1"),
    field("Issues", "Request 2"),
    field("Issues", "Request 3"),
]


def test_actual_discovery_protocol():
    result = resolve_privilege_fields(DISCOVERY_FIELDS)

    assert result["section"] == "privilege"
    assert result["privileged"] == "Privileged"
    assert result["not_privileged"] == "Not Privileged"
    assert result["available_sections"] == [
        "privilege",
        "privilege status",
    ]
    assert result["requires_reviewer_approval"] is True


def test_single_valid_privilege_section():
    fields = [
        field("Privilege", "Privileged"),
        field("Privilege", "Not Privileged"),
    ]

    result = resolve_privilege_fields(fields)
    assert result["section"] == "privilege"


def test_missing_privilege_section():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("Responsiveness", "Responsive"),
        ])


def test_incomplete_privilege_section():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("Privilege", "Privileged"),
        ])


def test_duplicate_privilege_field():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("Privilege", "Privileged"),
            field("Privilege", "Privileged"),
            field("Privilege", "Not Privileged"),
        ])


def test_conflicting_privilege_sections():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("Privilege", "Privileged"),
            field("Privilege", "Not Privileged"),
            field("Privilege Status", "Privileged"),
            field("Privilege Status", "Needs Counsel Review"),
        ])


def test_invalid_privilege_format():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("Privilege", "Privileged", "Text"),
            field("Privilege", "Not Privileged"),
        ])


def test_no_capture_fallback():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields([
            field("PII", "Social Security Number"),
            field("PHI", "Medical Record"),
        ])


def test_reject_non_list_input():
    with pytest.raises(TARaiProtocolError):
        resolve_privilege_fields(None)