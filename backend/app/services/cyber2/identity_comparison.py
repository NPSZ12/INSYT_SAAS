"""Comparison-only normalization of approved identity evidence.

Never transforms stored RAW or source field provenance.
"""
import re
from datetime import date


_DOB_HEADERS = frozenset({
    "dob",
    "date of birth",
    "date of birth (dob)",
    "birth date",
})


def normalize_identity_comparison(field: str, value: str) -> str:
    """Normalize only equivalent DOB text for QC comparisons."""
    if not isinstance(value, str):
        raise ValueError("Identity comparison value must be text")

    clean = value.strip()
    label = re.sub(
        r"_([2-9][0-9]*)$",
        "",
        field.strip().casefold(),
    )

    if label not in _DOB_HEADERS:
        return clean

    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})"
        r"(?:[ T]00:00:00(?:\.0+)?)?",
        clean,
    )

    if match is None:
        return clean

    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return clean

    return match.group(1)
