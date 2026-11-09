"""Strong-identifier conflict screening for iterative Cyber2 merges."""

import re

_STRONG = frozenset({
    "ssn",
    "social security number",
    "social security number (ssn)",
    "social security #",
    "dob",
    "date of birth",
    "date of birth (dob)",
    "birth date",
    "employee id",
    "employee number",
    "employee identifier",
    "medical record number",
    "medical record #",
    "mrn",
    "patient id",
    "patient identifier",
    "health insurance policy number",
    "health insurance policy #",
    "insurance policy number",
    "insurance policy #",
    "policy number",
    "member id",
    "member number",
    "subscriber id",
    "account number",
    "account #",
    "bank account number",
    "passport number",
    "driver license number",
    "drivers license number",
    "national id",
    "tax id",
    "tax identification number",
})


def iterative_conflict_headers(headers):
    """Recognize approved strong identifiers, including suffixed columns."""
    if not isinstance(headers, list) or any(
        not isinstance(field, str) or not field.strip()
        for field in headers
    ):
        raise ValueError("Invalid approved identifier headers")

    result = []

    for field in headers:
        label = field.strip().casefold()
        # Header mapping uses _2, _3 ... for duplicate canonical fields.
        label = re.sub(r"_([2-9][0-9]*)$", "", label)

        if label in _STRONG:
            result.append(field)

    return result
