from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .context_detector import find_context_matches, get_context_terms
from .models import DetectionCandidate
from .validators import (
    run_validator,
    validate_email_candidate,
    validate_phone_candidate,
    validate_us_ssn,
)


STRUCTURED_ENTITY_TYPES = {
    "phonenumber",
    "ussocialsecuritynumber",
    "drugenforcementagencynumber",
    "email",
    "nationalprovideridentifier",
    "iban",
    "creditcardnumber",
    "bankaccountnumber",

    # INSYT labeled identifiers
    "medicalrecordnumber",
    "claimnumber",
    "memberid",
    "policynumber",
    "patientid",
    "insuranceid",
    "accountnumber",
}


#
# Canonical INSYT clinical entity types.
#
# These are semantic PHI categories rather than deterministic
# identifiers, so they intentionally do not belong in
# STRUCTURED_ENTITY_TYPES.
#
CLINICAL_ENTITY_TYPES = {
    "medicalcondition",
    "medication",
    "healthcareprovider",
    "healthcarefacility",
}


#
# Broad Azure NER categories that may need clinical
# contextual reclassification.
#
AZURE_BROAD_CLINICAL_TYPES = {
    "person",
    "persontype",
    "organization",
    "location",
}


CONDITION_CONTEXT_TERMS = (
    "known condition",
    "known conditions",
    "condition",
    "conditions",
    "diagnosis",
    "diagnoses",
    "diagnostic impression",
    "problem",
    "problem list",
    "medical history",
    "past medical history",
    "pmh",
    "assessment",
)


MEDICATION_CONTEXT_TERMS = (
    "medication",
    "medications",
    "med",
    "meds",
    "current medication",
    "current medications",
    "prescription",
    "prescriptions",
    "drug",
    "drugs",
    "rx",
)


PROVIDER_CONTEXT_TERMS = (
    "provider",
    "provider name",
    "physician",
    "doctor",
    "clinician",
    "attending",
    "attending physician",
    "ordering provider",
    "ordering physician",
    "prescriber",
    "practitioner",
)


FACILITY_CONTEXT_TERMS = (
    "facility",
    "facility name",
    "hospital",
    "clinic",
    "medical center",
    "health center",
    "healthcare center",
    "practice",
    "health system",
)


def _normalized_type(
    candidate: DetectionCandidate,
) -> str:
    return (
        str(
            candidate.entity_type
            or ""
        )
        .strip()
        .casefold()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _digits_only(value: str) -> str:
    return "".join(
        char
        for char in str(value or "")
        if char.isdigit()
    )


def _has_line_break(value: str) -> bool:
    text = str(value or "")
    return "\n" in text or "\r" in text

def _immediate_clinical_context(
    text: str,
    candidate: DetectionCandidate,
) -> str:
    """
    Return only the local line context that can reasonably
    describe this candidate.

    We intentionally avoid using a large paragraph-wide window.
    Clinical records contain many unrelated labels close together,
    and a broad window could incorrectly make one heading control
    several unrelated entities.
    """

    value = str(
        text or ""
    )

    start_offset = max(
        0,
        int(
            candidate.start_offset
        ),
    )

    before = value[
        max(
            0,
            start_offset - 180,
        ):
        start_offset
    ]

    lines = before.splitlines()

    if not lines:
        return ""

    current_line_prefix = (
        lines[-1].strip()
        if lines
        else ""
    )

    previous_line = (
        lines[-2].strip()
        if len(lines) >= 2
        else ""
    )

    return " ".join(
        part
        for part in (
            previous_line,
            current_line_prefix,
        )
        if part
    ).casefold()


def _context_contains_any(
    context: str,
    terms: tuple[str, ...],
) -> list[str]:
    value = str(
        context or ""
    ).casefold()

    matched: list[str] = []

    for term in terms:
        normalized_term = str(
            term or ""
        ).strip().casefold()

        if (
            normalized_term
            and normalized_term
            in value
        ):
            matched.append(
                normalized_term
            )

    return matched


def _clinical_reclassification(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate:
    """
    Correct broad Azure semantic categories using strong,
    immediate clinical labels.

    Examples:

        Known Conditions: Gout
            Person -> MedicalCondition

        Medications: Lisinopril
            Person -> Medication

        Provider: Jane Smith, MD
            Person -> HealthcareProvider

        Facility: Boston Regional Medical Center
            Organization -> HealthcareFacility

    This does not create new candidates. It only corrects a
    candidate Azure has already emitted.
    """

    if not candidate.detector_name.startswith(
        "azure"
    ):
        return candidate

    entity_type = _normalized_type(
        candidate
    )

    if entity_type not in (
        AZURE_BROAD_CLINICAL_TYPES
        | CLINICAL_ENTITY_TYPES
    ):
        return candidate

    #
    # Candidates already normalized upstream should remain
    # canonical here.
    #
    if entity_type in CLINICAL_ENTITY_TYPES:
        return _copy_candidate(
            candidate,
            validation_status="valid",
            validation_method=(
                candidate.validation_method
                or "clinical_entity_normalization"
            ),
            metadata_updates={
                "post_validation": (
                    "accepted"
                ),
                "clinical_entity": True,
            },
        )

    context = (
        _immediate_clinical_context(
            text,
            candidate,
        )
    )

    condition_terms = (
        _context_contains_any(
            context,
            CONDITION_CONTEXT_TERMS,
        )
    )

    medication_terms = (
        _context_contains_any(
            context,
            MEDICATION_CONTEXT_TERMS,
        )
    )

    provider_terms = (
        _context_contains_any(
            context,
            PROVIDER_CONTEXT_TERMS,
        )
    )

    facility_terms = (
        _context_contains_any(
            context,
            FACILITY_CONTEXT_TERMS,
        )
    )

    original_type = (
        candidate.entity_type
    )

    original_subtype = (
        candidate.entity_subtype
    )

    confidence = float(
        candidate.confidence
        or 0.0
    )

    #
    # Conditions and medications can occasionally be emitted by
    # Azure as Person or PersonType in PHI-domain processing.
    #
    if (
        entity_type
        in {
            "person",
            "persontype",
        }
        and condition_terms
    ):
        return _copy_candidate(
            candidate,
            entity_type=(
                "MedicalCondition"
            ),
            entity_subtype=(
                "ClinicalCondition"
            ),
            confidence=max(
                confidence,
                0.88,
            ),
            validation_status="valid",
            validation_method=(
                "clinical_condition_context"
            ),
            metadata_updates={
                "post_validation": (
                    "reclassified"
                ),
                "clinical_entity": True,
                "clinical_reclassification_reason": (
                    "condition_context"
                ),
                "clinical_context_terms": (
                    condition_terms
                ),
                "reclassified_from_entity_type": (
                    original_type
                ),
                "reclassified_from_entity_subtype": (
                    original_subtype
                ),
                "reclassified_to_entity_type": (
                    "MedicalCondition"
                ),
            },
        )

    if (
        entity_type
        in {
            "person",
            "persontype",
        }
        and medication_terms
    ):
        return _copy_candidate(
            candidate,
            entity_type="Medication",
            entity_subtype=(
                "MedicationName"
            ),
            confidence=max(
                confidence,
                0.88,
            ),
            validation_status="valid",
            validation_method=(
                "medication_context"
            ),
            metadata_updates={
                "post_validation": (
                    "reclassified"
                ),
                "clinical_entity": True,
                "clinical_reclassification_reason": (
                    "medication_context"
                ),
                "clinical_context_terms": (
                    medication_terms
                ),
                "reclassified_from_entity_type": (
                    original_type
                ),
                "reclassified_from_entity_subtype": (
                    original_subtype
                ),
                "reclassified_to_entity_type": (
                    "Medication"
                ),
            },
        )

    #
    # Provider names remain clinically meaningful even though
    # Azure's base category is generally Person.
    #
    if (
        entity_type
        in {
            "person",
            "persontype",
        }
        and provider_terms
    ):
        return _copy_candidate(
            candidate,
            entity_type=(
                "HealthcareProvider"
            ),
            entity_subtype=(
                "ProviderName"
            ),
            confidence=max(
                confidence,
                0.90,
            ),
            validation_status="valid",
            validation_method=(
                "healthcare_provider_context"
            ),
            metadata_updates={
                "post_validation": (
                    "reclassified"
                ),
                "clinical_entity": True,
                "clinical_reclassification_reason": (
                    "provider_context"
                ),
                "clinical_context_terms": (
                    provider_terms
                ),
                "reclassified_from_entity_type": (
                    original_type
                ),
                "reclassified_from_entity_subtype": (
                    original_subtype
                ),
                "reclassified_to_entity_type": (
                    "HealthcareProvider"
                ),
            },
        )

    #
    # Clinical organizations and locations need to survive when
    # the source clearly identifies them as the care facility.
    #
    if (
        entity_type
        in {
            "organization",
            "location",
        }
        and facility_terms
    ):
        return _copy_candidate(
            candidate,
            entity_type=(
                "HealthcareFacility"
            ),
            entity_subtype=(
                "FacilityName"
            ),
            confidence=max(
                confidence,
                0.90,
            ),
            validation_status="valid",
            validation_method=(
                "healthcare_facility_context"
            ),
            metadata_updates={
                "post_validation": (
                    "reclassified"
                ),
                "clinical_entity": True,
                "clinical_reclassification_reason": (
                    "facility_context"
                ),
                "clinical_context_terms": (
                    facility_terms
                ),
                "reclassified_from_entity_type": (
                    original_type
                ),
                "reclassified_from_entity_subtype": (
                    original_subtype
                ),
                "reclassified_to_entity_type": (
                    "HealthcareFacility"
                ),
            },
        )

    return candidate

def _copy_candidate(
    candidate: DetectionCandidate,
    *,
    confidence: float | None = None,
    validation_status: str | None = None,
    validation_method: str | None = None,
    entity_type: str | None = None,
    entity_subtype: str | None = None,
    metadata_updates: dict | None = None,
) -> DetectionCandidate:
    metadata = {
        **dict(
            candidate.metadata
            or {}
        ),
        **dict(
            metadata_updates
            or {}
        ),
    }

    return replace(
        candidate,
        confidence=(
            candidate.confidence
            if confidence is None
            else max(
                0.0,
                min(
                    1.0,
                    float(confidence),
                ),
            )
        ),
        validation_status=(
            candidate.validation_status
            if validation_status is None
            else validation_status
        ),
        validation_method=(
            candidate.validation_method
            if validation_method is None
            else validation_method
        ),
        entity_type=(
            candidate.entity_type
            if entity_type is None
            else entity_type
        ),
        entity_subtype=(
            candidate.entity_subtype
            if entity_subtype is None
            else entity_subtype
        ),
        metadata=metadata,
    )


def _validate_phone(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate | None:
    value = str(
        candidate.detected_value or ""
    )

    digits = _digits_only(value)

    if _has_line_break(value):
        return None

    #
    # U.S.-style phone acceptance:
    #   - 10 digits
    #   - 11 digits only when country code = 1
    #
    if len(digits) == 11:
        if not digits.startswith("1"):
            return None

    elif len(digits) != 10:
        return None

    if not validate_phone_candidate(value):
        return None

    context_matches = find_context_matches(
        text,
        candidate_start=candidate.start_offset,
        candidate_end=candidate.end_offset,
        context_terms=(
            "phone",
            "telephone",
            "mobile",
            "cell",
            "contact",
        ),
        window_chars=80,
    )

    context_terms = get_context_terms(
        context_matches
    )

    confidence = float(
        candidate.confidence or 0.0
    )

    if context_terms:
        confidence = max(
            confidence,
            0.90,
        )

    elif candidate.detector_name.startswith(
        "azure"
    ):
        confidence = min(
            confidence,
            0.80,
        )

    return _copy_candidate(
        candidate,
        confidence=confidence,
        validation_status="valid",
        validation_method="phone_post_validation",
        metadata_updates={
            "post_validation": "accepted",
            "post_validation_context_terms": context_terms,
            "post_validation_digit_count": len(digits),
        },
    )


def _validate_ssn(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate | None:
    value = str(
        candidate.detected_value or ""
    )

    digits = _digits_only(value)

    if len(digits) != 9:
        return None

    if not validate_us_ssn(value):
        return None

    context_matches = find_context_matches(
        text,
        candidate_start=candidate.start_offset,
        candidate_end=candidate.end_offset,
        context_terms=(
            "ssn",
            "social security",
            "social security number",
        ),
        window_chars=80,
    )

    context_terms = get_context_terms(
        context_matches
    )

    has_separators = (
        "-" in value
        or " " in value
    )

    confidence = float(
        candidate.confidence or 0.0
    )

    #
    # Delimited SSNs are structurally stronger.
    #
    if has_separators:
        confidence = max(
            confidence,
            0.90,
        )

    #
    # Undelimited SSNs need either context or a strong model score.
    #
    elif context_terms:
        confidence = max(
            confidence,
            0.85,
        )

    elif confidence < 0.80:
        return None

    return _copy_candidate(
        candidate,
        confidence=confidence,
        validation_status="valid",
        validation_method="us_ssn",
        metadata_updates={
            "post_validation": "accepted",
            "post_validation_context_terms": context_terms,
            "post_validation_digit_count": len(digits),
            "post_validation_has_separators": has_separators,
        },
    )


def _validate_email(
    candidate: DetectionCandidate,
) -> DetectionCandidate | None:
    value = str(
        candidate.detected_value or ""
    ).strip()

    if not validate_email_candidate(value):
        return None

    return _copy_candidate(
        candidate,
        confidence=max(
            float(candidate.confidence or 0.0),
            0.85,
        ),
        validation_status="valid",
        validation_method="email",
        metadata_updates={
            "post_validation": "accepted",
        },
    )


def _dea_checksum_valid(
    value: str,
) -> bool:
    """
    Basic DEA number validation.

    Traditional DEA numbers:
      - 2 letters
      - 7 digits
      - checksum on first 6 digits

    Check digit:
      (d1 + d3 + d5) +
      2 * (d2 + d4 + d6)
      final digit of result == d7
    """
    clean = "".join(
        char
        for char in str(value or "").upper()
        if char.isalnum()
    )

    if len(clean) != 9:
        return False

    if not clean[:2].isalpha():
        return False

    if not clean[2:].isdigit():
        return False

    digits = [
        int(char)
        for char in clean[2:]
    ]

    checksum_total = (
        digits[0]
        + digits[2]
        + digits[4]
        + 2
        * (
            digits[1]
            + digits[3]
            + digits[5]
        )
    )

    return (
        checksum_total % 10
        == digits[6]
    )


def _validate_dea(
    candidate: DetectionCandidate,
) -> DetectionCandidate | None:
    value = str(
        candidate.detected_value or ""
    )

    if not _dea_checksum_valid(value):
        return None

    return _copy_candidate(
        candidate,
        confidence=max(
            float(candidate.confidence or 0.0),
            0.90,
        ),
        validation_status="valid",
        validation_method="dea_checksum",
        metadata_updates={
            "post_validation": "accepted",
        },
    )


def _validate_generic_named_validator(
    candidate: DetectionCandidate,
    validator_name: str,
) -> DetectionCandidate | None:
    result = run_validator(
        validator_name,
        candidate.detected_value,
    )

    if result is not True:
        return None

    return _copy_candidate(
        candidate,
        confidence=max(
            float(candidate.confidence or 0.0),
            0.90,
        ),
        validation_status="valid",
        validation_method=validator_name,
        metadata_updates={
            "post_validation": "accepted",
        },
    )

def _validate_labeled_identifier(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate | None:
    value = str(
        candidate.detected_value or ""
    ).strip()

    if not value:
        return None

    if _has_line_break(value):
        return None

    #
    # Labeled identifiers are intentionally broad because
    # legitimate client identifiers may contain letters,
    # digits, and hyphens in many combinations.
    #
    if len(value) < 4 or len(value) > 32:
        return None

    allowed = all(
        char.isalnum() or char in "-_/"
        for char in value
    )

    if not allowed:
        return None

    has_alpha = any(
        char.isalpha()
        for char in value
    )

    has_digit = any(
        char.isdigit()
        for char in value
    )

    #
    # Require at least one digit. This prevents ordinary
    # words after labels from becoming identifiers.
    #
    if not has_digit:
        return None

    entity_type = _normalized_type(
        candidate
    )

    context_terms_by_type = {
        "medicalrecordnumber": (
            "mrn",
            "medical record",
            "medical record number",
        ),
        "claimnumber": (
            "claim",
            "claim number",
            "claim #",
        ),
        "memberid": (
            "member id",
            "member number",
        ),
        "policynumber": (
            "policy number",
            "policy #",
        ),
        "patientid": (
            "patient id",
            "patient number",
        ),
        "insuranceid": (
            "insurance id",
            "insurance number",
        ),
        "accountnumber": (
            "account number",
            "account #",
            "acct",
        ),
    }

    context_matches = find_context_matches(
        text,
        candidate_start=candidate.start_offset,
        candidate_end=candidate.end_offset,
        context_terms=context_terms_by_type.get(
            entity_type,
            (),
        ),
        window_chars=80,
    )

    context_terms = get_context_terms(
        context_matches
    )

    confidence = float(
        candidate.confidence or 0.0
    )

    #
    # These identifiers do not have deterministic checksum
    # validation. Do not allow context alone to imply 1.00.
    #
    confidence = min(
        confidence,
        0.97,
    )

    #
    # Mixed alpha/numeric tokens are structurally stronger.
    #
    if has_alpha and has_digit:
        confidence = max(
            confidence,
            0.90,
        )

    if context_terms:
        confidence = max(
            confidence,
            0.92,
        )

    metadata_updates = {
        "post_validation": "accepted",
        "post_validation_context_terms": (
            context_terms
        ),
        "post_validation_identifier_length": (
            len(value)
        ),
        "post_validation_has_alpha": (
            has_alpha
        ),
        "post_validation_has_digit": (
            has_digit
        ),
    }

    return _copy_candidate(
        candidate,
        confidence=confidence,
        validation_status="valid",
        validation_method=(
            "labeled_identifier_post_validation"
        ),
        metadata_updates=metadata_updates,
    )

def post_validate_candidate(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate | None:
    #
    # First allow strong clinical source context to correct
    # broad Azure semantic categories.
    #
    candidate = (
        _clinical_reclassification(
            candidate,
            text=text,
        )
    )

    entity_type = _normalized_type(
        candidate
    )

    #
    # Canonical clinical entities are meaningful PHI/clinical
    # data elements and should survive post-validation.
    #
    if entity_type in CLINICAL_ENTITY_TYPES:
        return candidate

    #
    # Azure categories that remain too broad after contextual
    # clinical normalization should not become standalone
    # reportable Capture elements.
    #
    if (
        candidate.detector_name.startswith(
            "azure"
        )
        and entity_type
        in {
            "persontype",
            "organization",
        }
    ):
        return None

    #
    # Other contextual NER entities remain available.
    #
    if (
        entity_type
        not in STRUCTURED_ENTITY_TYPES
    ):
        return candidate

    if entity_type == "phonenumber":
        return _validate_phone(
            candidate,
            text=text,
        )

    if (
        entity_type
        == "ussocialsecuritynumber"
    ):
        return _validate_ssn(
            candidate,
            text=text,
        )

    if entity_type == "email":
        return _validate_email(
            candidate
        )

    if (
        entity_type
        == "drugenforcementagencynumber"
    ):
        return _validate_dea(
            candidate
        )

    if entity_type in {
        "medicalrecordnumber",
        "claimnumber",
        "memberid",
        "policynumber",
        "patientid",
        "insuranceid",
        "accountnumber",
    }:
        return (
            _validate_labeled_identifier(
                candidate,
                text=text,
            )
        )

    if (
        entity_type
        == "nationalprovideridentifier"
    ):
        return (
            _validate_generic_named_validator(
                candidate,
                "us_npi",
            )
        )

    if entity_type == "iban":
        return (
            _validate_generic_named_validator(
                candidate,
                "iban_mod97",
            )
        )

    if (
        entity_type
        == "creditcardnumber"
    ):
        return (
            _validate_generic_named_validator(
                candidate,
                "luhn",
            )
        )

    #
    # Unknown structured types remain available for future
    # validators rather than being silently discarded.
    #
    return candidate


def post_validate_candidates(
    candidates: Iterable[
        DetectionCandidate
    ],
    *,
    text: str,
) -> list[DetectionCandidate]:
    """
    Validate structured identifiers after candidate generation.

    Contextual NER entities such as Person and Organization pass
    through unchanged.

    Structured values may be:
      - accepted
      - confidence-adjusted
      - rejected
    """

    validated: list[
        DetectionCandidate
    ] = []

    for candidate in candidates:
        result = post_validate_candidate(
            candidate,
            text=text,
        )

        if result is None:
            continue

        validated.append(
            result
        )

    validated.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
        )
    )

    return validated