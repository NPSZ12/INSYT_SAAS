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


@pytest.mark.parametrize(
    "source,protocol,method,confidence",
    [
        ("employee.first_name", "First Name", "protocol_leaf", 1.0),
        ("employee.date_of_birth", "Date of Birth", "protocol_leaf", 1.0),
        ("employee.ssn", "Social Security Number", "protocol_alias", 0.95),
    ],
)
def test_deterministic_mapping_confidence(
    source, protocol, method, confidence
):
    review = build_json_header_review(
        make_evidence(source), [protocol]
    )
    column = review["columns"][0]

    assert column["recommended_protocol_header"] == protocol
    assert column["match_method"] == method
    assert column["mapping_confidence"] == confidence
    assert column["ai_confidence"] is None
    assert column["ai_invoked"] is False
    assert column["ai_review_required"] is False
    assert column["approved"] is False
    assert review["mapping_approved"] is False
    assert review["csv_generated"] is False


@pytest.mark.parametrize(
    "source",
    ["employee.fname", "employee.social"],
)
def test_unmatched_field_needs_ai_review(source):
    review = build_json_header_review(
        make_evidence(source),
        ["First Name", "Social Security Number"],
    )
    column = review["columns"][0]

    assert column["recommended_protocol_header"] is None
    assert column["mapping_confidence"] is None
    assert column["ai_review_required"] is True
    assert column["approved"] is False
    assert review["csv_generated"] is False


@pytest.mark.parametrize(
    "source,protocol",
    [
        ("employee.first_name", "First Name (or Initial)"),
        ("employee.fname", "First Name (or Initial)"),
        ("employee.last_name", "Last Name (FULL)"),
        ("employee.lname", "Last Name (FULL)"),
        ("employee.date_of_birth", "Date of Birth (DOB)"),
        ("employee.dob", "Date of Birth (DOB)"),
        ("employee.birth_dt", "Date of Birth (DOB)"),
        ("employee.ssn", "Social Security number (SSN)"),
        ("employee.social", "Social Security number (SSN)"),
    ],
)
def test_long_form_client_protocol_aliases(source, protocol):
    review = build_json_header_review(
        make_evidence(source),
        [protocol],
    )
    column = review["columns"][0]

    assert column["recommended_protocol_header"] == protocol
    assert column["match_method"] == "protocol_alias"
    assert column["mapping_confidence"] == 0.95
    assert column["ai_invoked"] is False
    assert column["approved"] is False
    assert review["mapping_approved"] is False
    assert review["csv_generated"] is False


@pytest.mark.parametrize(
    "source",
    [
        "employee.email",
        "employee.phone",
        "employee.full_name",
        "collection.batch_key",
        "__insyt_test_metadata.case",
    ],
)
def test_unapproved_json_headers_remain_unmatched(source):
    protocol = [
        "First Name (or Initial)",
        "Last Name (FULL)",
        "Date of Birth (DOB)",
        "Social Security number (SSN)",
    ]

    review = build_json_header_review(
        make_evidence(source),
        protocol,
    )

    column = review["columns"][0]

    assert not column["recommended_protocol_header"]
    assert column["mapping_confidence"] is None
    assert column["approved"] is False
    assert review["csv_generated"] is False


def test_multiple_valid_protocol_targets_remain_ambiguous():
    review = build_json_header_review(
        make_evidence("employee.ssn"),
        [
            "SSN",
            "Social Security Number",
            "Social Security number (SSN)",
        ],
    )

    column = review["columns"][0]

    assert not column["recommended_protocol_header"]
    assert column["mapping_confidence"] is None
    assert column["approved"] is False


def test_structural_json_parent_remains_unmatched_with_alias():
    evidence = make_evidence("employee.fname")
    evidence["fields"][0]["kind"] = "object"

    review = build_json_header_review(
        evidence,
        ["First Name (or Initial)"],
    )

    assert not review["columns"][0]["recommended_protocol_header"]
