from copy import deepcopy

from app.services.cyber2.iterative_merge_preview import (
    preview_iterative_merge,
)
from test_cyber2_iterative_merge_input import parent


def test_different_ssns_remain_qc_conflicts():
    source = parent()
    unchanged = deepcopy(source)

    result = preview_iterative_merge(
        source, ["First Name", "DOB"], ["SSN", "DOB"]
    )

    assert result["input_working_record_count"] == 2
    assert result["original_source_record_count"] == 4
    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert result["projected_working_record_count"] == 2
    assert result["conflicts"][0]["conflict_fields"] == ["SSN"]
    assert source == unchanged


def test_consistent_strong_identifiers_allow_exact_group():
    source = parent()
    record = source["working_records"][1]

    record["cells"]["SSN"] = "111"
    for evidence in record["field_provenance"]["SSN"]:
        evidence["original_value"] = "111"

    result = preview_iterative_merge(
        source, ["First Name", "DOB"], ["SSN", "DOB"]
    )

    assert result["duplicate_group_count"] == 1
    assert result["conflict_group_count"] == 0
    assert result["projected_working_record_count"] == 1

    members = result["groups"][0]["members"]
    assert {
        ucid for member in members
        for ucid in member["source_ucids"]
    } == {"R1", "R2", "R3", "R4"}


def test_missing_strong_identifier_is_qc_conflict():
    source = parent()
    record = source["working_records"][1]

    record["cells"]["SSN"] = ""
    for evidence in record["field_provenance"]["SSN"]:
        evidence["original_value"] = ""

    result = preview_iterative_merge(
        source, ["First Name", "DOB"], ["SSN"]
    )

    assert result["conflict_group_count"] == 1
    assert result["duplicate_group_count"] == 0


def test_multi_value_merge_index_is_excluded():
    result = preview_iterative_merge(
        parent(), ["First Name", "SSN"], ["DOB"]
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 0
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == (
        "multiple_identifier_values"
    )
    assert result["projected_working_record_count"] == 2
