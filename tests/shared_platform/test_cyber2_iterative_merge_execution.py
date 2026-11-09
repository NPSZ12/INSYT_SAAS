from copy import deepcopy

from app.services.cyber2.iterative_merge_execution import (
    build_iterative_child,
)
from app.services.cyber2.merge_set_store import (
    Cyber2MergeSetStore,
)
from test_cyber2_iterative_merge_input import parent


def test_child_preserves_all_sources_when_merge_is_safe():
    source = parent()
    original = deepcopy(source)

    record = source["working_records"][1]
    record["cells"]["SSN"] = "111"

    for entry in record["field_provenance"]["SSN"]:
        entry["original_value"] = "111"

    original = deepcopy(source)

    child = build_iterative_child(
        source, ["First Name", "DOB"], ["SSN", "DOB"]
    )

    assert child["parent_merge_set_id"] == source["merge_set_id"]
    assert child["pass_number"] == 2
    assert child["input_working_record_count"] == 2
    assert child["raw_record_count"] == 4
    assert child["working_record_count"] == 1
    assert child["merged_group_count"] == 1

    row = child["working_records"][0]
    assert row["source_ucids"] == ["R1", "R2", "R3", "R4"]
    assert len(row["field_provenance"]["SSN"]) == 4
    assert row["cells"]["SSN"] == "111"

    Cyber2MergeSetStore._validate_working_set(child)
    assert source == original


def test_conflicting_identifiers_never_merge():
    source = parent()
    original = deepcopy(source)

    child = build_iterative_child(
        source, ["First Name", "DOB"], ["SSN", "DOB"]
    )

    assert child["working_record_count"] == 2
    assert child["merged_group_count"] == 0
    assert child["conflict_group_count"] == 1

    assert all(
        row["classification"] == "qc_conflict"
        for row in child["working_records"]
    )

    Cyber2MergeSetStore._validate_working_set(child)
    assert source == original


def test_child_can_become_parent_of_next_pass():
    source = parent()

    child = build_iterative_child(
        source, ["First Name", "DOB"], ["SSN"]
    )

    child["status"] = "completed"
    child["merge_set_id"] = "MSET-" + "B" * 32

    grandchild = build_iterative_child(
        child, ["First Name", "SSN"], ["DOB"]
    )

    assert grandchild["parent_merge_set_id"] == child["merge_set_id"]
    assert grandchild["pass_number"] == 3
    assert grandchild["raw_record_count"] == 4
    assert grandchild["input_working_record_count"] == 2

    Cyber2MergeSetStore._validate_working_set(grandchild)
