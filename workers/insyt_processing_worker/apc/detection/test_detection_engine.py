from __future__ import annotations

from .engine import run_detection_engine


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
    print("INSYT DETECTION ENGINE TEST")
    print("=" * 90)

    print(
        f"Azure candidates:      "
        f"{result['azure_candidate_count']}"
    )

    print(
        f"Structured candidates: "
        f"{result['structured_candidate_count']}"
    )

    print(
        f"Merged candidates:     "
        f"{result['merged_candidate_count']}"
    )

    print(
        f"Detectors:             "
        f"{result['detectors']}"
    )

    print("-" * 90)

    for candidate in candidates:
        print(
            f"{candidate.entity_type:28} "
            f"{candidate.start_offset:4}-"
            f"{candidate.end_offset:<4} "
            f"{candidate.confidence:.2f} "
            f"{candidate.detected_value!r} "
            f"detector={candidate.detector_name} "
            f"rule={candidate.detection_rule}"
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

    if result["structured_candidate_count"] != 10:
        raise AssertionError(
            "Expected exactly 10 structured candidates."
        )

    if result["merged_candidate_count"] != 10:
        raise AssertionError(
            "Expected exactly 10 merged candidates "
            "with Azure disabled."
        )

    print()
    print(
        "PASS: unified engine returned all expected "
        "structured entities."
    )


if __name__ == "__main__":
    main()