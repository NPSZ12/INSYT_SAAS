import pytest

from json_header_review_contract import build_json_header_review


def make_evidence(path):
    return {
        "structure_scan_complete": True,
        "source_sha256": "a" * 64,
        "record_count": 1,
        "fields": [{
            "json_pointer": "/" + path.replace(".", "/"),
            "source_path": path,
            "kind": "scalar",
            "sample_values": ["SYNTHETIC"],
        }],
    }


@pytest.mark.parametrize(
    "source,protocol",
    [
        ("employee.date_of_birth", "Date of Birth"),
        ("employee.first_name", "First Name"),
        ("employee.last_name", "Last Name"),
        ("employee.ssn", "Social Security Number"),
        ("employee.email", "Email"),
    ],
)
def test_obvious_json_protocol_matches(source, protocol):
    review = build_json_header_review(
        make_evidence(source), [protocol]
    )
    column = review["columns"][0]

    assert column["recommended_protocol_header"] == protocol
    assert column["source_header"] == source
    assert column["json_pointer"] == "/" + source.replace(".", "/")
    assert column["approved"] is False
    assert review["mapping_approved"] is False
    assert review["csv_generated"] is False


def test_unrelated_header_remains_unmatched():
    review = build_json_header_review(
        make_evidence("employee.internal_code"),
        ["Date of Birth", "First Name"],
    )
    assert not review["columns"][0]["recommended_protocol_header"]


def test_ambiguous_ssn_protocol_remains_unmatched():
    review = build_json_header_review(
        make_evidence("employee.ssn"),
        ["SSN", "Social Security Number"],
    )
    assert not review["columns"][0]["recommended_protocol_header"]


def test_structural_fields_never_receive_protocol_match():
    evidence = make_evidence("employee.first_name")
    evidence["fields"][0]["kind"] = "object"

    review = build_json_header_review(evidence, ["First Name"])

    assert not review["columns"][0]["recommended_protocol_header"]
