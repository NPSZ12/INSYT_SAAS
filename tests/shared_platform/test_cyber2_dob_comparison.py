"""Cyber2 DOB QC comparison regressions.

Comparison normalization must never mutate source evidence.
"""

from copy import deepcopy

from app.services.cyber2.identity_comparison import (
    normalize_identity_comparison,
)
from app.services.cyber2.exact_dedupe import preview_exact_dedupe


HEADERS = ["First Name", "Last Name", "SSN", "DOB", "Pay Date", "Gross Pay"]


def raw(ucid, dob, pay_date, gross_pay):
    return {
        "ucid": ucid,
        "doc_id": "DOC-1",
        "metadata": {
            "First Name": "Alex",
            "Last Name": "Bennett",
            "SSN": "123-45-6789",
            "DOB": dob,
            "Pay Date": pay_date,
            "Gross Pay": gross_pay,
        },
        "provenance": {"source_row_number": 2},
    }


def preview(records):
    return preview_exact_dedupe(
        records,
        set_doc_ids=["DOC-1"],
        approved_headers=HEADERS,
        merge_index=["First Name", "Last Name", "SSN"],
        conflict_headers=["DOB"],
    )


def test_equivalent_dob_format_allows_exact_identity_group():
    records = [
        raw("UCID-1", "1973-01-01", "2026-01-09", "1450.00"),
        raw("UCID-2", "1973-01-01 00:00:00", "2026-01-23", "1512.42"),
    ]
    before = deepcopy(records)

    result = preview(records)

    assert result["duplicate_group_count"] == 1
    assert result["conflict_group_count"] == 0
    assert result["working_record_count"] == 1
    assert result["groups"][0]["member_count"] == 2
    assert records == before


def test_different_dob_remains_qc_conflict():
    records = [
        raw("UCID-1", "1973-01-01", "2026-01-09", "1450.00"),
        raw("UCID-2", "1973-01-02", "2026-01-23", "1512.42"),
    ]

    result = preview(records)

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert result["working_record_count"] == 2
    assert result["conflicts"][0]["conflict_fields"] == ["DOB"]


def test_missing_dob_remains_qc_conflict():
    records = [
        raw("UCID-1", "1973-01-01", "2026-01-09", "1450.00"),
        raw("UCID-2", "", "2026-01-23", "1512.42"),
    ]

    result = preview(records)

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert result["conflicts"][0]["conflict_fields"] == ["DOB"]


def test_only_dob_is_normalized():
    compare = normalize_identity_comparison

    assert compare("DOB", "1973-01-01T00:00:00") == "1973-01-01"
    assert compare("DOB_2", "1973-01-01 00:00:00") == "1973-01-01"
    assert compare("DOB", "1973-01-02") == "1973-01-02"
    assert compare("DOB", "1973-02-30") == "1973-02-30"
    assert compare("Pay Date", "2026-01-09 00:00:00") == "2026-01-09 00:00:00"
    assert compare("Gross Pay", "1450.00") == "1450.00"
    assert compare("SSN", "123-45-6789") == "123-45-6789"


def test_iterative_preview_uses_same_comparison_helper():
    from pathlib import Path
    import ast

    path = (
        Path(__file__).resolve().parents[2]
        / "backend/app/services/cyber2/iterative_merge_preview.py"
    )

    tree = ast.parse(path.read_text(encoding="utf-8-sig"))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "normalize_identity_comparison"
    ]

    assert len(calls) == 1
    assert len(calls[0].args) == 2