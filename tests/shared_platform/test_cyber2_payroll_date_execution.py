"""Payroll DOB comparison, display, and source provenance."""

from copy import deepcopy

import pytest

from app.services.cyber2.exact_dedupe import preview_exact_dedupe
from app.services.cyber2.merge_execution import (
    MergeExecutionError,
    build_merged_working_population,
)

HEADERS = [
    "First Name", "Last Name", "SSN",
    "DOB", "Pay Date", "Gross Pay",
]
INDEX = ["First Name", "Last Name", "SSN"]
HEADER_SET = "HDRSET-SYNTHETIC"


def raw(ucid, doc, dob, pay_date, amount):
    return {
        "ucid": ucid,
        "doc_id": doc,
        "metadata": {
            "First Name": "Alex",
            "Last Name": "Bennett",
            "SSN": "900-10-1000",
            "DOB": dob,
            "Pay Date": pay_date,
            "Gross Pay": amount,
        },
        "provenance": {
            "header_set_id": HEADER_SET,
            "source_row_number": 2,
            "column_lineage": [],
        },
    }


def preview_and_execute(records):
    docs = [record["doc_id"] for record in records]
    preview = preview_exact_dedupe(
        records,
        set_doc_ids=docs,
        approved_headers=HEADERS,
        merge_index=INDEX,
        conflict_headers=["DOB"],
    )
    preview["header_set_id"] = HEADER_SET

    derived = build_merged_working_population(
        header_set_id=HEADER_SET,
        approved_headers=HEADERS,
        approved_doc_ids=docs,
        merge_index=INDEX,
        raw_records=records,
        preview=preview,
        conflict_headers=["DOB"],
    )
    return preview, derived


def test_equivalent_dob_executes_with_short_date_and_source_pairs():
    records = [
        raw("R1", "D1", "1973-01-01", "2026-01-09", "1450.00"),
        raw(
            "R2", "D2", "1973-01-01 00:00:00",
            "2026-01-23", "1512.42",
        ),
    ]
    before = deepcopy(records)

    preview, derived = preview_and_execute(records)

    assert preview["duplicate_group_count"] == 1
    assert preview["conflict_group_count"] == 0
    assert derived["working_record_count"] == 1
    assert derived["raw_record_count"] == 2

    merged = derived["working_records"][0]

    assert merged["cells"]["DOB"] == "1973-01-01"
    assert merged["source_ucids"] == ["R1", "R2"]

    dob = {
        p["ucid"]: p["original_value"]
        for p in merged["field_provenance"]["DOB"]
    }
    assert dob == {
        "R1": "1973-01-01",
        "R2": "1973-01-01 00:00:00",
    }

    dates = {
        p["ucid"]: p["original_value"]
        for p in merged["field_provenance"]["Pay Date"]
    }
    amounts = {
        p["ucid"]: p["original_value"]
        for p in merged["field_provenance"]["Gross Pay"]
    }

    assert {
        ucid: (dates[ucid], amounts[ucid])
        for ucid in dates
    } == {
        "R1": ("2026-01-09", "1450.00"),
        "R2": ("2026-01-23", "1512.42"),
    }

    assert records == before


@pytest.mark.parametrize(
    "other_dob",
    ["1973-01-02", "", "1973-01-01 12:30:00"],
)
def test_different_missing_or_nonmidnight_dob_stays_separate(other_dob):
    records = [
        raw("R1", "D1", "1973-01-01", "2026-01-09", "1450.00"),
        raw("R2", "D2", other_dob, "2026-01-23", "1512.42"),
    ]

    preview, derived = preview_and_execute(records)

    assert preview["duplicate_group_count"] == 0
    assert preview["conflict_group_count"] == 1
    assert derived["working_record_count"] == 2


def test_execution_rejects_forged_group_with_different_dob():
    records = [
        raw("R1", "D1", "1973-01-01", "2026-01-09", "1450.00"),
        raw("R2", "D2", "1973-01-02", "2026-01-23", "1512.42"),
    ]

    preview, _ = preview_and_execute(records)
    preview["groups"] = [{
        "members": [
            {"ucid": "R1", "doc_id": "D1"},
            {"ucid": "R2", "doc_id": "D2"},
        ]
    }]
    preview["conflicts"] = []

    with pytest.raises(
        MergeExecutionError,
        match="Conflicting strong identifiers",
    ):
        build_merged_working_population(
            header_set_id=HEADER_SET,
            approved_headers=HEADERS,
            approved_doc_ids=["D1", "D2"],
            merge_index=INDEX,
            raw_records=records,
            preview=preview,
            conflict_headers=["DOB"],
        )
