"""TARai criteria approval integrity regression tests."""

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ai.tarai_criteria import (
    TARaiCriteriaApprovalError,
    validate_criteria_approval,
)

CRITERIA = b"Synthetic project-specific privilege criteria."


def approval():
    return {
        "status": "approved",
        "client": "INSYT_DEMO",
        "project": "Project_Ingestion",
        "approved_by": "authorized-test-reviewer",
        "approved_at": "2026-11-01T15:00:00Z",
        "sha256": hashlib.sha256(CRITERIA).hexdigest(),
    }


def check(content=CRITERIA, record=None):
    return validate_criteria_approval(
        criteria_bytes=content,
        approval=approval() if record is None else record,
        client="INSYT_DEMO",
        project="Project_Ingestion",
    )


def test_valid_approved_version():
    assert check() == CRITERIA.decode()


@pytest.mark.parametrize("change", [
    {"status": "draft"},
    {"client": "OTHER_CLIENT"},
    {"project": "Other_Project"},
    {"approved_by": ""},
    {"approved_at": ""},
    {"approved_at": "2026-11-01T15:00:00"},
    {"sha256": "0" * 64},
])
def test_reject_invalid_approval(change):
    record = approval()
    record.update(change)
    with pytest.raises(TARaiCriteriaApprovalError):
        check(record=record)


def test_reject_modified_content():
    with pytest.raises(TARaiCriteriaApprovalError):
        check(content=CRITERIA + b" Changed.")


def test_reject_invalid_utf8():
    record = approval()
    record["sha256"] = hashlib.sha256(b"\xff").hexdigest()
    with pytest.raises(TARaiCriteriaApprovalError):
        check(content=b"\xff", record=record)


def test_reject_missing_record():
    with pytest.raises(TARaiCriteriaApprovalError):
        check(record={})