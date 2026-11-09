from copy import deepcopy

from app.services.cyber2.iterative_conflict_policy import (
    iterative_conflict_headers,
)
from app.services.cyber2.iterative_merge_preview import (
    preview_iterative_merge,
)
from test_cyber2_iterative_merge_input import parent


def test_suffixed_identifiers_recognized():
    headers = [
        "First Name",
        "DOB",
        "Employee ID",
        "Employee ID_2",
        "Health Insurance Policy Number",
        "Health Insurance Policy Number_2",
        "Medical Record Number_3",
        "Street 1",
    ]
    assert iterative_conflict_headers(headers) == headers[1:7]


def test_nonidentifier_custom_columns_not_assumed_strong():
    assert iterative_conflict_headers(
        ["First Name", "Favorite Color", "Street 1"]
    ) == []


def test_conflicting_insurance_policy_numbers_block_merge():
    source = deepcopy(parent())
    field = "Health Insurance Policy Number_2"
    source["approved_headers"].append(field)

    for record, policy_number in zip(
        source["working_records"], ["POLICY-111", "POLICY-222"]
    ):
        record["cells"][field] = policy_number
        record["field_provenance"][field] = [
            {"ucid": ucid, "original_value": policy_number}
            for ucid in record["source_ucids"]
        ]

    # Remove the original SSN conflict to isolate policy-number screening.
    for record in source["working_records"]:
        record["cells"]["SSN"] = "111"
        for evidence in record["field_provenance"]["SSN"]:
            evidence["original_value"] = "111"

    unchanged = deepcopy(source)
    checked = iterative_conflict_headers(source["approved_headers"])

    result = preview_iterative_merge(
        source, ["First Name", "DOB"], checked
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert field in result["conflicts"][0]["conflict_fields"]
    assert source == unchanged
