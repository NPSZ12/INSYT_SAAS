"""Regression tests for immutable, provenance-preserving Cyber2 merge."""

import copy
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.cyber2.merge_execution import (
    MergeExecutionError,
    build_merged_working_population,
)


HEADERS = ["First Name", "Last Name", "SSN", "DOB", "Street 1"]
INDEX = ["First Name", "Last Name", "SSN"]


def raw(ucid, doc, street, ssn="900-12-0001"):
    return {
        "ucid": ucid,
        "doc_id": doc,
        "metadata": {
            "First Name": "Jordan",
            "Last Name": "Sample",
            "SSN": ssn,
            "DOB": "1985-04-12",
            "Street 1": street,
        },
        "provenance": {
            "header_set_id": "HDR-1",
            "source_row_number": 2,
        },
    }


def fixture():
    records = [
        raw("R1", "D1", "100 Main Street"),
        raw("R2", "D2", "200 Main Street"),
        raw("R3", "D2", "300 Main Street", "900-12-0002"),
        raw("R4", "D2", "400 Main Street", "900-12-0003"),
    ]

    preview = {
        "header_set_id": "HDR-1",
        "merge_index": INDEX,
        "groups": [{
            "members": [
                {"ucid": "R1", "doc_id": "D1"},
                {"ucid": "R2", "doc_id": "D2"},
            ]
        }],
        "conflicts": [],
        "unmatched": [
            {"ucid": "R3", "doc_id": "D2"},
            {"ucid": "R4", "doc_id": "D2"},
        ],
        "excluded": [],
    }

    return records, preview


def execute(records, preview):
    return build_merged_working_population(
        header_set_id="HDR-1",
        approved_headers=HEADERS,
        approved_doc_ids=["D1", "D2"],
        merge_index=INDEX,
        raw_records=records,
        preview=preview,
        conflict_headers=["SSN", "DOB"],
    )


def test_four_raw_records_become_three_working_records():
    records, preview = fixture()
    result = execute(records, preview)

    assert result["raw_record_count"] == 4
    assert result["working_record_count"] == 3
    assert result["merged_group_count"] == 1
    assert result["status"] == "derived_not_persisted"


def test_unique_values_concatenate_and_preserve_provenance():
    records, preview = fixture()
    merged = execute(records, preview)["working_records"][0]

    assert merged["source_ucids"] == ["R1", "R2"]
    assert merged["source_doc_ids"] == ["D1", "D2"]
    assert merged["cells"]["Street 1"] == (
        "100 Main Street; 200 Main Street"
    )
    assert len(merged["field_provenance"]["Street 1"]) == 2
    assert merged["field_provenance"]["Street 1"][0][
        "original_value"
    ] == "100 Main Street"
    assert merged["cells"]["SSN"] == "900-12-0001"


def test_raw_records_remain_immutable():
    records, preview = fixture()
    original = copy.deepcopy(records)

    execute(records, preview)

    assert records == original


def test_incomplete_preview_is_rejected():
    records, preview = fixture()
    preview["unmatched"].pop()

    with pytest.raises(MergeExecutionError):
        execute(records, preview)


def test_conflicting_ssn_cannot_be_forced_into_merge():
    records, preview = fixture()
    records[1]["metadata"]["SSN"] = "900-12-9999"

    with pytest.raises(MergeExecutionError):
        execute(records, preview)


def test_conflicting_unselected_dob_cannot_be_merged():
    records, preview = fixture()
    records[1]["metadata"]["DOB"] = "1990-01-01"

    with pytest.raises(MergeExecutionError):
        execute(records, preview)


def test_duplicate_ucid_is_rejected():
    records, preview = fixture()
    records.append(copy.deepcopy(records[0]))

    with pytest.raises(MergeExecutionError):
        execute(records, preview)


def test_qc_conflicts_remain_individual_records():
    records, preview = fixture()

    preview["conflicts"] = [{
        "members": preview["unmatched"]
    }]
    preview["unmatched"] = []

    result = execute(records, preview)
    conflicts = [
        row for row in result["working_records"]
        if row["classification"] == "qc_conflict"
    ]

    assert len(conflicts) == 2
    assert all(len(row["source_ucids"]) == 1 for row in conflicts)
