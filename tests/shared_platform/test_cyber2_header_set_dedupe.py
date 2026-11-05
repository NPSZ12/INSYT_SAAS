"""Tests for approved INSYT Cyber2 Header Set deduplication."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.cyber2.exact_dedupe import ExactDedupeError
from app.services.cyber2.header_set_dedupe import preview_header_set_dedupe


def mapping():
    return {
        "status": "approved",
        "header_set_id": "HDR-1",
        "canonical_column_order": ["First Name", "Last Name", "SSN"],
        "documents": [{"doc_id": "D1"}, {"doc_id": "D2"}],
    }


def record(ucid, doc, ssn="900-12-0001", header_set="HDR-1"):
    return {
        "ucid": ucid,
        "doc_id": doc,
        "metadata": {
            "First Name": "Jordan",
            "Last Name": "Sample",
            "SSN": ssn,
        },
        "provenance": {
            "header_set_id": header_set,
            "source_row_number": 2,
        },
    }


def preview(rows, approved=None):
    return preview_header_set_dedupe(
        header_set_id="HDR-1",
        approved_mapping=approved if approved is not None else mapping(),
        raw_records=rows,
        merge_index=["First Name", "Last Name", "SSN"],
        conflict_headers=["SSN"],
    )


def test_approved_header_set_exact_matches():
    result = preview([record("R1", "D1"), record("R2", "D2")])
    assert result["duplicate_group_count"] == 1
    assert result["working_record_count"] == 1
    assert result["header_set_id"] == "HDR-1"


def test_unapproved_header_set_rejected():
    approved = mapping()
    approved["status"] = "pending"

    with pytest.raises(ExactDedupeError, match="not approved"):
        preview([record("R1", "D1"), record("R2", "D2")], approved)


def test_wrong_header_set_rejected():
    approved = mapping()
    approved["header_set_id"] = "HDR-OTHER"

    with pytest.raises(ExactDedupeError, match="mismatch"):
        preview([record("R1", "D1"), record("R2", "D2")], approved)


def test_unapproved_document_rejected():
    with pytest.raises(ExactDedupeError, match="outside approved"):
        preview([
            record("R1", "D1"),
            record("R2", "D2"),
            record("R3", "D3"),
        ])


def test_mixed_header_set_records_rejected():
    with pytest.raises(ExactDedupeError, match="another Header Set"):
        preview([
            record("R1", "D1"),
            record("R2", "D2", header_set="HDR-OTHER"),
        ])


def test_missing_approved_document_rejected():
    with pytest.raises(ExactDedupeError, match="missing RAW"):
        preview([record("R1", "D1")])


def test_raw_population_unchanged():
    import copy

    rows = [record("R1", "D1"), record("R2", "D2")]
    before = copy.deepcopy(rows)

    preview(rows)

    assert rows == before


def test_unapproved_merge_header_rejected():
    with pytest.raises(ExactDedupeError, match="unapproved"):
        preview_header_set_dedupe(
            header_set_id="HDR-1",
            approved_mapping=mapping(),
            raw_records=[record("R1", "D1"), record("R2", "D2")],
            merge_index=["Unknown Header"],
            conflict_headers=["SSN"],
        )