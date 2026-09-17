from __future__ import annotations

from .built_in_rules import get_built_in_rules
from .regex_detector import detect_regex_entities


TEST_TEXT = """
INSYT DEMO MEDICAL RECORD

Patient: Ahmed109 O'Reilly797
DOB: 2013-06-12
Address: 857 Kling Arcade, Worcester, MA, 01604
Phone: 555-768-4657
Email: o.reilly@example.test

SSN: 464-12-1234
MRN: MRN-882199
Insurance ID: INS-551122
Claim Number: CLM-443829
Member ID: MEM-332211
Policy Number: POL-998877
Patient ID: PAT-112233
Account Number: ACCT-778899

Provider: Emily Jones
"""


def main() -> None:
    rules = get_built_in_rules()

    candidates = detect_regex_entities(
        TEST_TEXT,
        rules=rules,
        protocol_name="HIPAA",
        protocol_version="test",
    )

    print()
    print("INSYT STRUCTURED DETECTION TEST")
    print("=" * 80)

    for candidate in candidates:
        print(
            f"{candidate.entity_type:28} "
            f"{candidate.start_offset:4}-{candidate.end_offset:<4} "
            f"{candidate.confidence:.2f} "
            f"{candidate.detected_value!r} "
            f"rule={candidate.detection_rule} "
            f"context={candidate.context_terms} "
            f"validation={candidate.validation_status}"
        )

    print()
    print(f"TOTAL CANDIDATES: {len(candidates)}")
    print()

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
            f"Missing expected entity types: {sorted(missing)}"
        )

    ssn_hits = [
        candidate
        for candidate in candidates
        if candidate.entity_type == "USSocialSecurityNumber"
    ]

    if not ssn_hits:
        raise AssertionError("SSN was not detected.")

    if ssn_hits[0].detected_value != "464-12-1234":
        raise AssertionError(
            "SSN detected value was incorrect."
        )

    mrn_hits = [
        candidate
        for candidate in candidates
        if candidate.entity_type == "MedicalRecordNumber"
    ]

    if not mrn_hits:
        raise AssertionError("MRN was not detected.")

    if mrn_hits[0].detected_value != "MRN-882199":
        raise AssertionError(
            "MRN capture group did not isolate the value correctly."
        )

    print("PASS: structured detector returned all expected entity types.")


if __name__ == "__main__":
    main()