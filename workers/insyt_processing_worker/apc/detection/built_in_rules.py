from __future__ import annotations

from .rules import DetectionRule


BUILT_IN_RULES: tuple[DetectionRule, ...] = (
    DetectionRule(
        rule_id="US_SSN",
        entity_type="USSocialSecurityNumber",
        regex_pattern=r"\b\d{3}-\d{2}-\d{4}\b",
        context_terms=(
            "ssn",
            "social security",
            "social security number",
        ),
        validator="us_ssn",
        base_confidence=0.82,
        country="US",
        framework=(
            "PII",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
            "validator",
        ),
    ),

    DetectionRule(
        rule_id="EMAIL_ADDRESS",
        entity_type="Email",
        regex_pattern=(
            r"\b"
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
            r"@[A-Za-z0-9]"
            r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9]"
            r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
            r"\b"
        ),
        context_terms=(
            "email",
            "e-mail",
            "email address",
        ),
        validator="email",
        base_confidence=0.80,
        framework=(
            "PII",
            "GDPR",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
            "validator",
        ),
    ),

    DetectionRule(
        rule_id="US_PHONE",
        entity_type="PhoneNumber",
        regex_pattern=(
            r"(?<!\d)"
            r"(?:\+?1[\s.\-]?)?"
            r"(?:\(\d{3}\)|\d{3})"
            r"[\s.\-]?"
            r"\d{3}"
            r"[\s.\-]?"
            r"\d{4}"
            r"(?!\d)"
        ),
        context_terms=(
            "phone",
            "telephone",
            "mobile",
            "cell",
            "contact",
        ),
        validator="phone",
        base_confidence=0.76,
        country="US",
        framework=(
            "PII",
            "GDPR",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
            "validator",
        ),
    ),

    DetectionRule(
        rule_id="MEDICAL_RECORD_NUMBER_LABELED",
        entity_type="MedicalRecordNumber",
        regex_pattern=(
            r"(?i)"
            r"(?:(?:mrn)|(?:medical[ \t_-]+record(?:[ \t_-]+number)?))"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,24})"
        ),
        context_terms=(
            "mrn",
            "medical record",
            "medical record number",
        ),
        base_confidence=0.90,
        framework=(
            "PHI",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="CLAIM_NUMBER_LABELED",
        entity_type="ClaimNumber",
        regex_pattern=(
            r"(?i)"
            r"(?:claim(?:[ \t_-]+number)?|claim[\s_-]*#)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "claim",
            "claim number",
            "claim #",
        ),
        base_confidence=0.88,
        framework=(
            "PII",
            "PHI",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="MEMBER_ID_LABELED",
        entity_type="MemberId",
        regex_pattern=(
            r"(?i)"
            r"(?:member[ \t_-]+id|member[ \t_-]+number)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "member id",
            "member number",
        ),
        base_confidence=0.88,
        framework=(
            "PII",
            "PHI",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="POLICY_NUMBER_LABELED",
        entity_type="PolicyNumber",
        regex_pattern=(
            r"(?i)"
            r"(?:policy[ \t_-]+number|policy[\s_-]*#)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "policy number",
            "policy #",
        ),
        base_confidence=0.88,
        framework=(
            "PII",
            "PHI",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="PATIENT_ID_LABELED",
        entity_type="PatientId",
        regex_pattern=(
            r"(?i)"
            r"(?:patient[ \t_-]+id|patient[ \t_-]+number)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "patient id",
            "patient number",
        ),
        base_confidence=0.90,
        framework=(
            "PHI",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="INSURANCE_ID_LABELED",
        entity_type="InsuranceId",
        regex_pattern=(
            r"(?i)"
            r"(?:insurance[ \t_-]+id|insurance[ \t_-]+number)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "insurance id",
            "insurance number",
        ),
        base_confidence=0.88,
        framework=(
            "PII",
            "PHI",
            "HIPAA",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),

    DetectionRule(
        rule_id="ACCOUNT_NUMBER_LABELED",
        entity_type="AccountNumber",
        regex_pattern=(
            r"(?i)"
            r"(?:account[ \t_-]+number|account[\s_-]*#|acct[\s_-]*#?)"
            r"[ \t]*[:#\-]?[ \t]*"
            r"([A-Z0-9][A-Z0-9\-]{3,30})"
        ),
        context_terms=(
            "account number",
            "account #",
            "acct",
        ),
        base_confidence=0.84,
        framework=(
            "PII",
            "GDPR",
        ),
        methods=(
            "regex",
            "context",
        ),
        metadata={
            "capture_group": 1,
        },
    ),
)


def get_built_in_rules() -> tuple[DetectionRule, ...]:
    return tuple(
        rule
        for rule in BUILT_IN_RULES
        if rule.enabled
    )