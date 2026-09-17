from __future__ import annotations

from .engine import run_detection_engine


TEST_TEXT = """
INSYT DEMO MEDICAL RECORD

Patient: Mickey Mouse
Email: mickey.mouse@example.com

Phone: 423-555-1212
Bad Phone: 56412346
Bad 11 Digit Phone: 84545616654

SSN: 464-12-1234
Bad SSN: 654651654

MRN: MRN-882199
Insurance ID: INS-551122
Claim Number: CLM-443829
Member ID: MEM-332211
Policy Number: POL-998877
Patient ID: PAT-112233
Account Number: ACCT-778899
"""


def main() -> None:
    result = run_detection_engine(
        TEST_TEXT,
        include_phi=True,
        protocol_name="HIPAA",
        protocol_version="test",
        enable_azure=False,
        enable_structured_rules=True,
    )

    candidates = result["candidates"]

    print()
    print("INSYT DETECTION ENGINE POST-VALIDATION TEST")
    print("=" * 100)

    print(
        f"Azure candidates:        "
        f"{result['azure_candidate_count']}"
    )

    print(
        f"Structured candidates:   "
        f"{result['structured_candidate_count']}"
    )

    print(
        f"Validated candidates:    "
        f"{result['validated_candidate_count']}"
    )

    print(
        f"Merged candidates:       "
        f"{result['merged_candidate_count']}"
    )

    print(
        f"Detectors:               "
        f"{result['detectors']}"
    )

    print("-" * 100)

    for candidate in candidates:
        print(
            f"{candidate.entity_type:28} "
            f"{candidate.start_offset:4}-"
            f"{candidate.end_offset:<4} "
            f"{candidate.confidence:.2f} "
            f"{candidate.detected_value!r} "
            f"detector={candidate.detector_name} "
            f"rule={candidate.detection_rule} "
            f"validation={candidate.validation_status}"
        )

    expected_types = {
        "USSocialSecurityNumber",
        "MedicalRecordNumber",
        "InsuranceId",
        "ClaimNumber",
        "MemberId",
        "PolicyNumber",
        "PatientId",
        "AccountNumber",
        "Email",
        "PhoneNumber",
    }

    actual_types = {
        candidate.entity_type
        for candidate in candidates
    }

    missing = expected_types - actual_types

    if missing:
        raise AssertionError(
            f"Missing expected entity types: "
            f"{sorted(missing)}"
        )

    #
    # Valid phone should survive.
    #
    valid_phone_hits = [
        candidate
        for candidate in candidates
        if (
            candidate.entity_type == "PhoneNumber"
            and candidate.detected_value == "423-555-1212"
        )
    ]

    if not valid_phone_hits:
        raise AssertionError(
            "Valid phone number was not retained."
        )

    #
    # Bad phone candidates must not survive post-validation.
    #
    bad_phone_values = {
        "56412346",
        "84545616654",
    }

    surviving_bad_phones = [
        candidate.detected_value
        for candidate in candidates
        if (
            candidate.entity_type == "PhoneNumber"
            and candidate.detected_value in bad_phone_values
        )
    ]

    if surviving_bad_phones:
        raise AssertionError(
            f"Invalid phone values survived: "
            f"{surviving_bad_phones}"
        )

    #
    # Valid SSN should survive.
    #
    valid_ssn_hits = [
        candidate
        for candidate in candidates
        if (
            candidate.entity_type
            == "USSocialSecurityNumber"
            and candidate.detected_value
            == "464-12-1234"
        )
    ]

    if not valid_ssn_hits:
        raise AssertionError(
            "Valid SSN was not retained."
        )

    #
    # The unlabeled/invalid low-confidence-looking SSN
    # should not become a structured SSN from our rules.
    #
    invalid_ssn_hits = [
        candidate
        for candidate in candidates
        if (
            candidate.entity_type
            == "USSocialSecurityNumber"
            and candidate.detected_value
            == "654651654"
        )
    ]

    if invalid_ssn_hits:
        raise AssertionError(
            "Invalid SSN survived post-validation."
        )

    print()
    print(
        "PASS: post-validation retained valid structured "
        "entities and rejected invalid phone/SSN candidates."
    )


if __name__ == "__main__":
    main()