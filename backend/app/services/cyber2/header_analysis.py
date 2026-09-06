from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any


EMAIL_RE = re.compile(
    r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$",
    re.IGNORECASE,
)

SSN_RE = re.compile(
    r"^\d{3}[- ]?\d{2}[- ]?\d{4}$"
)

PHONE_RE = re.compile(
    r"^(?:\+?1[\s.\-]?)?"
    r"(?:\(?\d{3}\)?[\s.\-]?)"
    r"\d{3}[\s.\-]?\d{4}$"
)

ZIP_RE = re.compile(
    r"^\d{5}(?:-\d{4})?$"
)

IPV4_RE = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}$"
)

DATE_RE = re.compile(
    r"^(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r")$"
)

INTEGER_RE = re.compile(
    r"^[+-]?\d+$"
)

DECIMAL_RE = re.compile(
    r"^[+-]?\d+(?:\.\d+)?$"
)


def normalize_text(
    value: Any,
) -> str:
    text = str(
        value
        if value is not None
        else ""
    ).strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9 ]+",
        "",
        text,
    )

    return text.strip()


def clamp_confidence(
    value: float,
) -> float:
    return round(
        max(
            0.0,
            min(
                1.0,
                float(value),
            ),
        ),
        4,
    )


def nonblank_values(
    values: list[Any],
) -> list[str]:
    return [
        str(value).strip()
        for value in values
        if str(
            value
            if value is not None
            else ""
        ).strip()
    ]


def looks_like_email(
    value: str,
) -> bool:
    return bool(
        EMAIL_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_ssn(
    value: str,
) -> bool:
    return bool(
        SSN_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_phone(
    value: str,
) -> bool:
    return bool(
        PHONE_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_zip(
    value: str,
) -> bool:
    return bool(
        ZIP_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_ipv4(
    value: str,
) -> bool:
    clean = value.strip()

    if not IPV4_RE.fullmatch(
        clean
    ):
        return False

    try:
        parts = [
            int(part)
            for part in clean.split(".")
        ]
    except ValueError:
        return False

    return all(
        0 <= part <= 255
        for part in parts
    )


def looks_like_date(
    value: str,
) -> bool:
    return bool(
        DATE_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_integer(
    value: str,
) -> bool:
    return bool(
        INTEGER_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_decimal(
    value: str,
) -> bool:
    return bool(
        DECIMAL_RE.fullmatch(
            value.strip()
        )
    )


def looks_like_person_name(
    value: str,
) -> bool:
    clean = str(
        value or ""
    ).strip()

    if not clean:
        return False

    if any(
        char.isdigit()
        for char in clean
    ):
        return False

    pieces = [
        piece
        for piece in re.split(
            r"\s+",
            clean,
        )
        if piece
    ]

    if not (
        2 <= len(pieces) <= 5
    ):
        return False

    alpha_pieces = sum(
        1
        for piece in pieces
        if re.search(
            r"[A-Za-z]",
            piece,
        )
    )

    return (
        alpha_pieces
        == len(pieces)
    )


def looks_like_header_text(
    value: str,
) -> bool:
    clean = str(
        value or ""
    ).strip()

    if not clean:
        return False

    normalized = normalize_text(
        clean
    )

    if not normalized:
        return False

    if normalized.isdigit():
        return False

    if looks_like_email(
        clean
    ):
        return False

    if looks_like_ssn(
        clean
    ):
        return False

    if looks_like_phone(
        clean
    ):
        return False

    if looks_like_ipv4(
        clean
    ):
        return False

    if looks_like_date(
        clean
    ):
        return False

    if len(clean) > 100:
        return False

    return any(
        char.isalpha()
        for char in clean
    )


def value_semantic_type(
    value: str,
) -> str:
    clean = str(
        value or ""
    ).strip()

    if not clean:
        return "blank"

    if looks_like_email(
        clean
    ):
        return "email"

    if looks_like_ssn(
        clean
    ):
        return "ssn"

    if looks_like_ipv4(
        clean
    ):
        return "ip_address"

    if looks_like_phone(
        clean
    ):
        return "phone"

    if looks_like_date(
        clean
    ):
        return "date"

    if looks_like_zip(
        clean
    ):
        return "zip_code"

    if looks_like_integer(
        clean
    ):
        return "integer"

    if looks_like_decimal(
        clean
    ):
        return "decimal"

    if looks_like_person_name(
        clean
    ):
        return "person_name"

    if any(
        char.isalpha()
        for char in clean
    ):
        return "text"

    return "unknown"


def profile_column_values(
    values: list[Any],
) -> dict[str, Any]:
    cleaned = nonblank_values(
        values
    )

    if not cleaned:
        return {
            "semantic_type": "blank",
            "semantic_confidence": 0.0,
            "sample_count": 0,
            "type_counts": {},
            "sample_values": [],
        }

    semantic_types = [
        value_semantic_type(
            value
        )
        for value in cleaned
    ]

    counts = Counter(
        semantic_types
    )

    dominant_type, dominant_count = (
        counts.most_common(1)[0]
    )

    confidence = (
        dominant_count
        / len(cleaned)
    )

    #
    # Numeric identifiers are intentionally not
    # treated as ordinary numbers with high certainty.
    #
    if (
        dominant_type
        in {
            "integer",
            "decimal",
        }
        and confidence >= 0.80
    ):
        semantic_type = (
            "numeric"
        )
    else:
        semantic_type = (
            dominant_type
        )

    return {
        "semantic_type": (
            semantic_type
        ),
        "semantic_confidence": (
            clamp_confidence(
                confidence
            )
        ),
        "sample_count": len(
            cleaned
        ),
        "type_counts": dict(
            counts
        ),
        "sample_values": (
            cleaned[:8]
        ),
    }


def score_header_presence(
    rows: list[list[Any]],
) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NEEDS_REVIEW",
            "confidence": 0.0,
            "header_row": [],
            "evidence": [
                "CSV contains no readable rows."
            ],
        }

    first_row = [
        str(
            value
            if value is not None
            else ""
        ).strip()
        for value in rows[0]
    ]

    if not first_row:
        return {
            "status": "NEEDS_REVIEW",
            "confidence": 0.0,
            "header_row": [],
            "evidence": [
                "First row is empty."
            ],
        }

    evidence: list[str] = []

    nonblank_first = [
        value
        for value in first_row
        if value
    ]

    if not nonblank_first:
        return {
            "status": "NO_HEADER",
            "confidence": 0.95,
            "header_row": first_row,
            "evidence": [
                "First row contains no meaningful values."
            ],
        }

    header_like_count = sum(
        1
        for value in nonblank_first
        if looks_like_header_text(
            value
        )
    )

    header_like_ratio = (
        header_like_count
        / len(
            nonblank_first
        )
    )

    first_row_types = [
        value_semantic_type(
            value
        )
        for value in nonblank_first
    ]

    obvious_data_types = {
        "email",
        "ssn",
        "phone",
        "ip_address",
        "date",
        "zip_code",
        "integer",
        "decimal",
        "person_name",
    }

    data_like_count = sum(
        1
        for semantic_type
        in first_row_types
        if semantic_type
        in obvious_data_types
    )

    data_like_ratio = (
        data_like_count
        / len(
            nonblank_first
        )
    )

    later_rows = (
        rows[1:21]
    )

    column_count = max(
        len(first_row),
        max(
            (
                len(row)
                for row in later_rows
            ),
            default=0,
        ),
    )

    semantic_contrast_scores: list[
        float
    ] = []

    for column_index in range(
        column_count
    ):
        first_value = (
            first_row[
                column_index
            ]
            if column_index
            < len(first_row)
            else ""
        )

        later_values = [
            row[column_index]
            for row in later_rows
            if column_index
            < len(row)
            and str(
                row[
                    column_index
                ]
            ).strip()
        ]

        if not later_values:
            continue

        profile = (
            profile_column_values(
                later_values
            )
        )

        first_type = (
            value_semantic_type(
                first_value
            )
        )

        dominant_type = (
            profile[
                "semantic_type"
            ]
        )

        if (
            looks_like_header_text(
                first_value
            )
            and dominant_type
            not in {
                "blank",
                "text",
                "unknown",
            }
        ):
            semantic_contrast_scores.append(
                1.0
            )

        elif (
            first_type
            == dominant_type
            and dominant_type
            not in {
                "blank",
                "unknown",
            }
        ):
            semantic_contrast_scores.append(
                0.0
            )

        else:
            semantic_contrast_scores.append(
                0.5
            )

    semantic_contrast = (
        sum(
            semantic_contrast_scores
        )
        / len(
            semantic_contrast_scores
        )
        if semantic_contrast_scores
        else 0.5
    )

    header_score = (
        0.55
        * header_like_ratio
        + 0.35
        * semantic_contrast
        + 0.10
        * (
            1.0
            - data_like_ratio
        )
    )

    header_score = (
        clamp_confidence(
            header_score
        )
    )

    no_header_score = (
        clamp_confidence(
            1.0
            - header_score
        )
    )

    #
    # Special protection for tiny one-row CSVs.
    # "Mickey Mouse,424-24-1212" should not be
    # classified as a header merely because it
    # contains alphabetic text.
    #
    if len(rows) == 1:
        if (
            data_like_ratio
            >= 0.50
        ):
            return {
                "status": (
                    "NO_HEADER"
                ),
                "confidence": (
                    clamp_confidence(
                        max(
                            0.90,
                            data_like_ratio,
                        )
                    )
                ),
                "header_row": (
                    first_row
                ),
                "evidence": [
                    (
                        "Single-row CSV contains "
                        "data-like values."
                    ),
                    (
                        f"Data-like first-row ratio: "
                        f"{data_like_ratio:.2f}"
                    ),
                ],
            }

        return {
            "status": (
                "NEEDS_REVIEW"
            ),
            "confidence": 0.50,
            "header_row": (
                first_row
            ),
            "evidence": [
                (
                    "Single-row CSV does not provide "
                    "enough evidence to distinguish "
                    "header from data."
                )
            ],
        }

    if header_score >= 0.72:
        status = "HEADER"
        confidence = (
            header_score
        )

    elif no_header_score >= 0.72:
        status = "NO_HEADER"
        confidence = (
            no_header_score
        )

    else:
        status = "NEEDS_REVIEW"

        confidence = (
            clamp_confidence(
                max(
                    header_score,
                    no_header_score,
                )
            )
        )

    evidence.append(
        (
            "First-row header-like ratio: "
            f"{header_like_ratio:.2f}"
        )
    )

    evidence.append(
        (
            "First-row data-like ratio: "
            f"{data_like_ratio:.2f}"
        )
    )

    evidence.append(
        (
            "Row-1 versus later-row semantic "
            f"contrast: {semantic_contrast:.2f}"
        )
    )

    return {
        "status": status,
        "confidence": confidence,
        "header_score": (
            header_score
        ),
        "no_header_score": (
            no_header_score
        ),
        "header_row": (
            first_row
        ),
        "evidence": evidence,
    }


def build_synonym_lookup(
    library: dict[
        str,
        list[str],
    ],
) -> dict[str, str]:
    lookup: dict[
        str,
        str,
    ] = {}

    for (
        canonical,
        variations,
    ) in library.items():
        canonical_clean = str(
            canonical or ""
        ).strip()

        if not canonical_clean:
            continue

        lookup[
            normalize_text(
                canonical_clean
            )
        ] = canonical_clean

        for variation in (
            variations
            or []
        ):
            variation_clean = str(
                variation or ""
            ).strip()

            if not variation_clean:
                continue

            lookup[
                normalize_text(
                    variation_clean
                )
            ] = canonical_clean

    return lookup


def best_protocol_text_match(
    source_header: str,
    library: dict[
        str,
        list[str],
    ],
) -> dict[str, Any]:
    clean_source = str(
        source_header or ""
    ).strip()

    if not clean_source:
        return {
            "canonical": "",
            "confidence": 0.0,
            "method": "none",
        }

    lookup = (
        build_synonym_lookup(
            library
        )
    )

    normalized_source = (
        normalize_text(
            clean_source
        )
    )

    if (
        normalized_source
        in lookup
    ):
        return {
            "canonical": (
                lookup[
                    normalized_source
                ]
            ),
            "confidence": 1.0,
            "method": (
                "exact_or_alias"
            ),
        }

    best_canonical = ""
    best_score = 0.0

    for (
        canonical,
        variations,
    ) in library.items():
        candidates = [
            canonical,
            *(
                variations
                or []
            ),
        ]

        for candidate in (
            candidates
        ):
            score = (
                SequenceMatcher(
                    None,
                    normalized_source,
                    normalize_text(
                        candidate
                    ),
                ).ratio()
            )

            if score > best_score:
                best_score = score
                best_canonical = (
                    canonical
                )

    return {
        "canonical": (
            best_canonical
            if best_score
            >= 0.60
            else ""
        ),
        "confidence": (
            clamp_confidence(
                best_score
            )
        ),
        "method": (
            "fuzzy_header_text"
            if best_score
            >= 0.60
            else "none"
        ),
    }


SEMANTIC_HEADER_ALIASES = {
    "email": [
        "email",
        "email address",
        "e-mail",
    ],

    "ssn": [
        "ssn",
        "social security number",
        "social security",
    ],

    "phone": [
        "phone",
        "phone number",
        "telephone",
        "mobile",
        "cell",
    ],

    "ip_address": [
        "ip address",
        "ip",
    ],

    "date": [
        "date",
        "date of birth",
        "dob",
        "birth date",
        "birthdate",
    ],

    "zip_code": [
        "zip",
        "zip code",
        "zipcode",
        "postal code",
    ],

    "person_name": [
        "full name",
        "name",
        "person name",
        "patient name",
        "member name",
        "individual name",
        "data subject",
    ],

    "numeric": [
        "id",
        "identifier",
        "account number",
        "patient id",
        "member id",
        "record number",
        "medical record number",
        "mrn",
    ],
}

STRICT_SEMANTIC_TYPES = {
    "email",
    "ssn",
    "phone",
    "ip_address",
    "date",
    "zip_code",
}


def protocol_header_is_semantically_compatible(
    *,
    semantic_type: str,
    protocol_header: str,
    variations: list[str] | None = None,
) -> bool:

    semantic_type = str(
        semantic_type or ""
    ).strip().lower()

    if semantic_type not in STRICT_SEMANTIC_TYPES:
        return True

    aliases = (
        SEMANTIC_HEADER_ALIASES.get(
            semantic_type,
            [],
        )
    )

    candidates = [
        protocol_header,
        *(variations or []),
    ]

    normalized_candidates = [
        normalize_text(candidate)
        for candidate in candidates
        if str(candidate or "").strip()
    ]

    for alias in aliases:
        normalized_alias = (
            normalize_text(alias)
        )

        if not normalized_alias:
            continue

        for candidate in normalized_candidates:
            if (
                normalized_alias == candidate
                or normalized_alias in candidate
                or candidate in normalized_alias
            ):
                return True

    return False


def semantic_protocol_match(
    semantic_type: str,
    library: dict[
        str,
        list[str],
    ],
) -> dict[str, Any]:
    aliases = (
        SEMANTIC_HEADER_ALIASES.get(
            semantic_type,
            [],
        )
    )

    if not aliases:
        return {
            "canonical": "",
            "confidence": 0.0,
            "method": "none",
        }

    best_canonical = ""
    best_score = 0.0

    for canonical, variations in (
        library.items()
    ):

        if not protocol_header_is_semantically_compatible(
            semantic_type=semantic_type,
            protocol_header=canonical,
            variations=variations,
        ):
            continue
        normalized_canonical = (
            normalize_text(
                canonical
            )
        )

        for alias in aliases:
            normalized_alias = (
                normalize_text(
                    alias
                )
            )

            score = (
                SequenceMatcher(
                    None,
                    normalized_alias,
                    normalized_canonical,
                ).ratio()
            )

            if (
                normalized_alias
                == normalized_canonical
            ):
                score = 1.0

            elif (
                normalized_alias
                in normalized_canonical
                or normalized_canonical
                in normalized_alias
            ):
                score = max(
                    score,
                    0.90,
                )

            if score > best_score:
                best_score = score
                best_canonical = (
                    canonical
                )

    if best_score < 0.60:
        return {
            "canonical": "",
            "confidence": (
                clamp_confidence(
                    best_score
                )
            ),
            "method": "none",
        }

    return {
        "canonical": (
            best_canonical
        ),
        "confidence": (
            clamp_confidence(
                best_score
            )
        ),
        "method": (
            "column_data_semantics"
        ),
    }


def recommend_protocol_header(
    source_header: str,
    values: list[Any],
    library: dict[
        str,
        list[str],
    ],
) -> dict[str, Any]:

    profile = (
        profile_column_values(
            values
        )
    )

    text_match = (
        best_protocol_text_match(
            source_header,
            library,
        )
    )

    semantic_match = (
        semantic_protocol_match(
            profile[
                "semantic_type"
            ],
            library,
        )
    )

    text_canonical = str(
        text_match.get(
            "canonical"
        )
        or ""
    )

    semantic_canonical = str(
        semantic_match.get(
            "canonical"
        )
        or ""
    )

    text_confidence = float(
        text_match.get(
            "confidence"
        )
        or 0.0
    )

    semantic_match_confidence = (
        float(
            semantic_match.get(
                "confidence"
            )
            or 0.0
        )
    )

    semantic_profile_confidence = (
        float(
            profile.get(
                "semantic_confidence"
            )
            or 0.0
        )
    )

    #
    # Strongest case:
    # header text and underlying data independently
    # point to the same protocol field.
    #
    if (
        text_canonical
        and semantic_canonical
        and normalize_text(
            text_canonical
        )
        == normalize_text(
            semantic_canonical
        )
    ):
        recommended = (
            text_canonical
        )

        combined_confidence = (
            0.55
            * text_confidence
            + 0.30
            * semantic_match_confidence
            + 0.15
            * semantic_profile_confidence
        )

        method = (
            "header_and_data_agree"
        )

    #
    # Existing header text is exact/very strong.
    #
    elif (
        text_canonical
        and text_confidence
        >= 0.88
    ):
        recommended = (
            text_canonical
        )

        combined_confidence = (
            0.75
            * text_confidence
            + 0.25
            * semantic_profile_confidence
        )

        method = (
            text_match.get(
                "method"
            )
            or "header_text"
        )

    #
    # Data is strong enough to identify the field,
    # useful for headerless files.
    #
    elif (
        semantic_canonical
        and semantic_profile_confidence
        >= 0.75
    ):
        recommended = (
            semantic_canonical
        )

        combined_confidence = (
            0.65
            * semantic_match_confidence
            + 0.35
            * semantic_profile_confidence
        )

        method = (
            "data_semantics"
        )

    #
    # Lower-confidence header-text suggestion.
    #
    elif text_canonical:
        recommended = (
            text_canonical
        )

        combined_confidence = (
            0.70
            * text_confidence
            + 0.30
            * semantic_profile_confidence
        )

        method = (
            text_match.get(
                "method"
            )
            or "header_text"
        )

    else:
        recommended = ""
        combined_confidence = 0.0
        method = "unmatched"

    #
    # Strong structured-data semantics must not be
    # overridden by an incompatible fuzzy text match.
    #
    semantic_type = str(
        profile.get(
            "semantic_type"
        )
        or ""
    ).strip().lower()

    if (
        recommended
        and semantic_type
        in STRICT_SEMANTIC_TYPES
        and semantic_profile_confidence
        >= 0.85
        and not protocol_header_is_semantically_compatible(
            semantic_type=semantic_type,
            protocol_header=recommended,
            variations=library.get(
                recommended,
                [],
            ),
        )
    ):
        if semantic_canonical:
            recommended = (
                semantic_canonical
            )

            combined_confidence = (
                0.65
                * semantic_match_confidence
                + 0.35
                * semantic_profile_confidence
            )

            method = (
                "semantic_conflict_override"
            )

        else:
            recommended = ""
            combined_confidence = 0.0
            method = (
                "semantic_conflict_unmatched"
            )

    combined_confidence = (
        clamp_confidence(
            combined_confidence
        )
    )

    matched = bool(
        recommended
    )

    return {
        "source_header": (
            source_header
        ),

        "recommended_protocol_header": (
            recommended
        ),

        "mapping_confidence": (
            combined_confidence
        ),

        "matched": (
            matched
        ),

        "match_method": (
            method
        ),

        "semantic_type": (
            profile[
                "semantic_type"
            ]
        ),

        "semantic_confidence": (
            profile[
                "semantic_confidence"
            ]
        ),

        "sample_count": (
            profile[
                "sample_count"
            ]
        ),

        "sample_values": (
            profile[
                "sample_values"
            ]
        ),

        "type_counts": (
            profile[
                "type_counts"
            ]
        ),

        "header_text_match": (
            text_match
        ),

        "semantic_match": (
            semantic_match
        ),

        "default_disposition": (
            "approve"
            if matched
            else "keep"
        ),

        "allowed_dispositions": [
            "approve",
            "map",
            "keep",
            "rename",
            "delete",
        ],
    }


def analyze_csv_rows(
    rows: list[list[Any]],
    protocol_library: dict[
        str,
        list[str],
    ],
) -> dict[str, Any]:

    presence = (
        score_header_presence(
            rows
        )
    )

    status = str(
        presence.get(
            "status"
        )
        or "NEEDS_REVIEW"
    ).upper()

    if not rows:
        return {
            "header_presence": (
                presence
            ),
            "columns": [],
            "protocol_headers": list(
                protocol_library.keys()
            ),
        }

    column_count = max(
        (
            len(row)
            for row in rows
        ),
        default=0,
    )

    if status == "HEADER":
        source_headers = [
            str(
                rows[0][index]
                if index
                < len(rows[0])
                else ""
            ).strip()
            or f"Column {index + 1}"
            for index in range(
                column_count
            )
        ]

        data_rows = (
            rows[1:]
        )

    else:
        source_headers = [
            f"Column {index + 1}"
            for index in range(
                column_count
            )
        ]

        data_rows = (
            rows
        )

    columns: list[
        dict[str, Any]
    ] = []

    for column_index in range(
        column_count
    ):
        values = [
            row[column_index]
            for row in data_rows
            if column_index
            < len(row)
        ]

        recommendation = (
            recommend_protocol_header(
                source_header=(
                    source_headers[
                        column_index
                    ]
                ),
                values=values,
                library=(
                    protocol_library
                ),
            )
        )

        columns.append(
            {
                "column_index": (
                    column_index
                ),

                "column_number": (
                    column_index + 1
                ),

                **recommendation,
            }
        )

    #
    # Required approval order:
    # matched/recommended fields first,
    # unmatched fields at the end.
    #
    columns.sort(
        key=lambda column: (
            0
            if column.get(
                "matched"
            )
            else 1,

            -float(
                column.get(
                    "mapping_confidence"
                )
                or 0.0
            ),

            int(
                column.get(
                    "column_index"
                )
                or 0
            ),
        )
    )

    matched_count = sum(
        1
        for column in columns
        if column.get(
            "matched"
        )
    )

    unmatched_count = (
        len(columns)
        - matched_count
    )

    return {
        "header_presence": (
            presence
        ),

        "protocol_headers": list(
            protocol_library.keys()
        ),

        "column_count": len(
            columns
        ),

        "matched_column_count": (
            matched_count
        ),

        "unmatched_column_count": (
            unmatched_count
        ),

        "columns": columns,
    }