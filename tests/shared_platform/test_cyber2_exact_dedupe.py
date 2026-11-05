"""Synthetic INSYT exact set dedupe preview tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.cyber2.exact_dedupe import (
    ExactDedupeError,
    preview_exact_dedupe,
)


HEADERS = ["First Name", "Last Name", "SSN", "DOB", "Street 1"]


def raw(ucid, doc, first, last, ssn, **extra):
    return {
        "ucid": ucid,
        "doc_id": doc,
        "metadata": {
            "First Name": first,
            "Last Name": last,
            "SSN": ssn,
            **extra,
        },
        "provenance": {"source_row_number": 2},
    }


def preview(rows, index=None, docs=None):
    return preview_exact_dedupe(
        rows,
        set_doc_ids=docs or ["D1", "D2"],
        approved_headers=HEADERS,
        merge_index=index or ["First Name", "Last Name", "SSN"],
    )


def test_exact_cross_document_match():
    result = preview([
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Charles", "Smith", "900-12-0001"),
    ])
    assert result["duplicate_group_count"] == 1
    assert result["working_record_count"] == 1
    assert {x["ucid"] for x in result["groups"][0]["members"]} == {"R1", "R2"}


def test_name_variant_is_not_exact():
    result = preview([
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Chuck", "Smith", "900-12-0001"),
    ])
    assert result["duplicate_group_count"] == 0
    assert result["working_record_count"] == 2


def test_conflicting_index_value_stays_separate():
    result = preview([
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Charles", "Smith", "900-12-0002"),
    ])
    assert result["duplicate_group_count"] == 0


def test_alternative_protocol_index_without_ssn():
    result = preview([
        raw("R1", "D1", "Charles", "Smith", "",
            DOB="1980-01-15", **{"Street 1": "123 Main"}),
        raw("R2", "D2", "Charles", "Smith", "",
            DOB="1980-01-15", **{"Street 1": "123 Main"}),
    ], index=["First Name", "Last Name", "DOB", "Street 1"])
    assert result["duplicate_group_count"] == 1


def test_missing_index_values_excluded():
    result = preview([
        raw("R1", "D1", "Charles", "Smith", ""),
        raw("R2", "D2", "Charles", "Smith", ""),
    ])
    assert len(result["excluded"]) == 2
    assert result["duplicate_group_count"] == 0


def test_unapproved_header_rejected():
    with pytest.raises(ExactDedupeError, match="unapproved"):
        preview_exact_dedupe(
            [],
            set_doc_ids=["D1"],
            approved_headers=HEADERS,
            merge_index=["Unapproved Column"],
        )


def test_missing_document_fails_closed():
    with pytest.raises(ExactDedupeError, match="missing RAW"):
        preview([
            raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        ])


def test_duplicate_ucid_rejected():
    row = raw("R1", "D1", "Charles", "Smith", "900-12-0001")
    with pytest.raises(ExactDedupeError, match="Duplicate RAW UCID"):
        preview([row, row, raw("R2", "D2", "Charles", "Smith", "900-12-0001")])


def test_raw_records_unchanged():
    import copy
    rows = [
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Charles", "Smith", "900-12-0001"),
    ]
    before = copy.deepcopy(rows)
    preview(rows)
    assert rows == before


def test_large_set_1000_records():
    rows = [
        raw(f"R{i}", f"D{i}", "Charles", "Smith", "900-12-0001")
        for i in range(1000)
    ]
    result = preview(rows, docs=[f"D{i}" for i in range(1000)])
    assert result["raw_record_count"] == 1000
    assert result["duplicate_group_count"] == 1
    assert result["working_record_count"] == 1
    assert result["groups"][0]["member_count"] == 1000

def test_unselected_conflicting_ssns_flagged():
    rows = [
        raw("R1", "D1", "Charles", "Smith", "900-12-0001",
            DOB="1980-01-15", **{"Street 1": "123 Main"}),
        raw("R2", "D2", "Charles", "Smith", "900-12-0002",
            DOB="1980-01-15", **{"Street 1": "123 Main"}),
    ]

    result = preview_exact_dedupe(
        rows,
        set_doc_ids=["D1", "D2"],
        approved_headers=HEADERS,
        merge_index=["First Name", "Last Name", "DOB", "Street 1"],
        conflict_headers=["SSN"],
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert result["working_record_count"] == 2
    assert result["conflicts"][0]["conflict_fields"] == ["SSN"]
    assert "900-12-0001" not in str(result)


def test_matching_strong_identifier_passes():
    rows = [
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Charles", "Smith", "900-12-0001"),
    ]

    result = preview_exact_dedupe(
        rows,
        set_doc_ids=["D1", "D2"],
        approved_headers=HEADERS,
        merge_index=["First Name", "Last Name"],
        conflict_headers=["SSN"],
    )

    assert result["duplicate_group_count"] == 1
    assert result["conflict_group_count"] == 0


def test_missing_strong_identifier_flagged():
    rows = [
        raw("R1", "D1", "Charles", "Smith", "900-12-0001"),
        raw("R2", "D2", "Charles", "Smith", ""),
    ]

    result = preview_exact_dedupe(
        rows,
        set_doc_ids=["D1", "D2"],
        approved_headers=HEADERS,
        merge_index=["First Name", "Last Name"],
        conflict_headers=["SSN"],
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1


def test_unapproved_conflict_header_rejected():
    with pytest.raises(ExactDedupeError, match="conflict headers"):
        preview_exact_dedupe(
            [],
            set_doc_ids=["D1"],
            approved_headers=HEADERS,
            merge_index=["First Name"],
            conflict_headers=["Unknown Field"],
        )