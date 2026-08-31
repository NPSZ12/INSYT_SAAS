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
}


def _normalized_type(
    candidate: DetectionCandidate,
) -> str:
    return str(
        candidate.entity_type or ""
    ).strip().casefold()


def _digits_only(value: str) -> str:
    return "".join(
        char
        for char in str(value or "")
        if char.isdigit()
    )


def _has_line_break(value: str) -> bool:
    text = str(value or "")
    return "\n" in text or "\r" in text


def _copy_candidate(
    candidate: DetectionCandidate,
    *,
    confidence: float | None = None,
    validation_status: str | None = None,
    validation_method: str | None = None,
    entity_type: str | None = None,
    metadata_updates: dict | None = None,
) -> DetectionCandidate:
    metadata = {
        **dict(candidate.metadata or {}),
        **dict(metadata_updates or {}),
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


def post_validate_candidate(
    candidate: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate | None:
    entity_type = _normalized_type(
        candidate
    )

    #
    # Contextual NER entities are generally left alone.
    #
    if entity_type not in STRUCTURED_ENTITY_TYPES:
        return candidate

    if entity_type == "phonenumber":
        return _validate_phone(
            candidate,
            text=text,
        )

    if entity_type == "ussocialsecuritynumber":
        return _validate_ssn(
            candidate,
            text=text,
        )

    if entity_type == "email":
        return _validate_email(
            candidate
        )

    if entity_type == "drugenforcementagencynumber":
        return _validate_dea(
            candidate
        )

    if entity_type == "nationalprovideridentifier":
        return _validate_generic_named_validator(
            candidate,
            "us_npi",
        )

    if entity_type == "iban":
        return _validate_generic_named_validator(
            candidate,
            "iban_mod97",
        )

    if entity_type == "creditcardnumber":
        return _validate_generic_named_validator(
            candidate,
            "luhn",
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