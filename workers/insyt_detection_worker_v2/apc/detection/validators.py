from __future__ import annotations

import re
from datetime import datetime


def normalize_digits(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def validate_luhn(value: str) -> bool:
    """
    Validate payment-card-style identifiers using the Luhn algorithm.
    """
    digits = normalize_digits(value)

    if len(digits) < 12:
        return False

    total = 0
    parity = len(digits) % 2

    for index, char in enumerate(digits):
        digit = int(char)

        if index % 2 == parity:
            digit *= 2

            if digit > 9:
                digit -= 9

        total += digit

    return total % 10 == 0


def validate_iban(value: str) -> bool:
    """
    Validate an IBAN using the ISO 13616 MOD-97 check.
    """
    iban = re.sub(
        r"\s+",
        "",
        str(value or ""),
    ).upper()

    if not re.fullmatch(
        r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
        iban,
    ):
        return False

    rearranged = iban[4:] + iban[:4]

    numeric = ""

    for char in rearranged:
        if char.isdigit():
            numeric += char
        elif "A" <= char <= "Z":
            numeric += str(
                ord(char) - ord("A") + 10
            )
        else:
            return False

    remainder = 0

    for char in numeric:
        remainder = (
            remainder * 10 + int(char)
        ) % 97

    return remainder == 1


def validate_us_ssn(value: str) -> bool:
    """
    Structural validation for U.S. SSNs.

    This does not determine whether the SSN was actually issued
    to a real person. It only rejects impossible/reserved formats.
    """
    digits = normalize_digits(value)

    if len(digits) != 9:
        return False

    area = int(digits[0:3])
    group = int(digits[3:5])
    serial = int(digits[5:9])

    if area == 0:
        return False

    if area == 666:
        return False

    if 900 <= area <= 999:
        return False

    if group == 0:
        return False

    if serial == 0:
        return False

    if digits in {
        "078051120",
        "219099999",
    }:
        return False

    return True


def validate_us_npi(value: str) -> bool:
    """
    Validate a U.S. National Provider Identifier.

    NPI uses the Luhn algorithm with the CMS prefix 80840.
    """
    digits = normalize_digits(value)

    if len(digits) != 10:
        return False

    prefixed = "80840" + digits

    return validate_luhn(prefixed)


def validate_date_candidate(value: str) -> bool:
    """
    Validate common date formats and reject impossible dates.
    """
    text = str(value or "").strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%m-%d-%y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            datetime.strptime(
                text,
                fmt,
            )

            return True

        except ValueError:
            continue

    return False


def validate_phone_candidate(value: str) -> bool:
    """
    Conservative structural phone-number validation.
    """
    digits = normalize_digits(value)

    if len(digits) < 7:
        return False

    if len(digits) > 15:
        return False

    if len(set(digits)) == 1:
        return False

    return True


def validate_email_candidate(value: str) -> bool:
    """
    Basic structural email validation.
    """
    text = str(value or "").strip()

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
            r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
            text,
        )
    )


VALIDATORS = {
    "luhn": validate_luhn,
    "iban_mod97": validate_iban,
    "us_ssn": validate_us_ssn,
    "us_npi": validate_us_npi,
    "date": validate_date_candidate,
    "phone": validate_phone_candidate,
    "email": validate_email_candidate,
}


def run_validator(
    validator_name: str,
    value: str,
) -> bool | None:
    """
    Run a named validator.

    Returns:
      True  -> valid
      False -> invalid
      None  -> validator not found
    """
    validator = VALIDATORS.get(
        str(validator_name or "").strip()
    )

    if validator is None:
        return None

    return bool(
        validator(value)
    )