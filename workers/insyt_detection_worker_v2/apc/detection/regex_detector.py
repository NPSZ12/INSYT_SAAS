from __future__ import annotations

import re
from typing import Iterable

from .context_detector import (
    context_confidence_boost,
    find_context_matches,
    get_context_terms,
)
from .models import DetectionCandidate
from .rules import DetectionRule
from .validators import run_validator


DETECTOR_NAME = "insyt_regex"
DETECTOR_VERSION = "v2"


def _clamp_confidence(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(value),
        ),
    )


def _validation_adjustment(
    result: bool | None,
) -> float:
    if result is True:
        return 0.10

    if result is False:
        return -0.35

    return 0.0


def _split_captured_values(
    captured_value: str,
    *,
    absolute_start: int,
    separators: tuple[str, ...],
) -> list[tuple[str, int, int]]:
    """
    Split one regex capture into multiple candidate values while
    preserving correct absolute offsets into the original document.

    Example:

        Captured text:
            "Gout, Hypertension, Asthma"

        Result:
            ("Gout", ...)
            ("Hypertension", ...)
            ("Asthma", ...)

    Separators are treated as literal strings.
    """

    value = str(
        captured_value
        or ""
    )

    if not value:
        return []

    clean_separators = tuple(
        separator
        for separator in separators
        if str(separator or "")
    )

    if not clean_separators:
        return [
            (
                value,
                absolute_start,
                absolute_start
                + len(value),
            )
        ]

    separator_pattern = (
        "|".join(
            re.escape(
                separator
            )
            for separator
            in sorted(
                clean_separators,
                key=len,
                reverse=True,
            )
        )
    )

    if not separator_pattern:
        return [
            (
                value,
                absolute_start,
                absolute_start
                + len(value),
            )
        ]

    results: list[
        tuple[str, int, int]
    ] = []

    cursor = 0

    for separator_match in re.finditer(
        separator_pattern,
        value,
    ):
        raw_piece = value[
            cursor:
            separator_match.start()
        ]

        left_trimmed = len(
            raw_piece
        ) - len(
            raw_piece.lstrip()
        )

        right_trimmed_piece = (
            raw_piece.rstrip()
        )

        if right_trimmed_piece.strip():
            piece_start = (
                absolute_start
                + cursor
                + left_trimmed
            )

            piece_end = (
                piece_start
                + len(
                    right_trimmed_piece[
                        left_trimmed:
                    ]
                )
            )

            piece_value = value[
                piece_start
                - absolute_start:
                piece_end
                - absolute_start
            ]

            if piece_value.strip():
                results.append(
                    (
                        piece_value,
                        piece_start,
                        piece_end,
                    )
                )

        cursor = (
            separator_match.end()
        )

    raw_piece = value[
        cursor:
    ]

    left_trimmed = len(
        raw_piece
    ) - len(
        raw_piece.lstrip()
    )

    right_trimmed_piece = (
        raw_piece.rstrip()
    )

    if right_trimmed_piece.strip():
        piece_start = (
            absolute_start
            + cursor
            + left_trimmed
        )

        piece_end = (
            piece_start
            + len(
                right_trimmed_piece[
                    left_trimmed:
                ]
            )
        )

        piece_value = value[
            piece_start
            - absolute_start:
            piece_end
            - absolute_start
        ]

        if piece_value.strip():
            results.append(
                (
                    piece_value,
                    piece_start,
                    piece_end,
                )
            )

    return results


def _candidate_segments_for_match(
    match: re.Match,
    rule: DetectionRule,
) -> list[tuple[str, int, int, int]]:
    """
    Convert one regex match into one or more candidate segments.

    Normal structured rules continue to return exactly one candidate.

    Rules may opt into list expansion with:

        metadata={
            "capture_group": 1,
            "split_capture": True,
            "split_separators": [",", ";", "|"],
        }

    Returned tuple:
        detected_value,
        start_offset,
        end_offset,
        capture_group
    """

    capture_group = int(
        rule.metadata.get(
            "capture_group",
            0,
        )
        or 0
    )

    if capture_group:
        try:
            detected_value = str(
                match.group(
                    capture_group
                )
                or ""
            )

            start_offset = int(
                match.start(
                    capture_group
                )
            )

            end_offset = int(
                match.end(
                    capture_group
                )
            )

        except IndexError as exc:
            raise RuntimeError(
                f"Rule {rule.rule_id} requested "
                f"capture group {capture_group}, "
                "but that group does not exist."
            ) from exc

    else:
        detected_value = str(
            match.group(0)
            or ""
        )

        start_offset = int(
            match.start()
        )

        end_offset = int(
            match.end()
        )

    if not detected_value:
        return []

    if end_offset <= start_offset:
        return []

    split_capture = bool(
        rule.metadata.get(
            "split_capture",
            False,
        )
    )

    if not split_capture:
        return [
            (
                detected_value,
                start_offset,
                end_offset,
                capture_group,
            )
        ]

    raw_separators = (
        rule.metadata.get(
            "split_separators",
            [
                ",",
                ";",
                "|",
            ],
        )
    )

    if isinstance(
        raw_separators,
        str,
    ):
        separators = (
            raw_separators,
        )
    else:
        separators = tuple(
            str(
                separator
            )
            for separator
            in (
                raw_separators
                or []
            )
            if str(
                separator
                or ""
            )
        )

    split_values = (
        _split_captured_values(
            detected_value,
            absolute_start=(
                start_offset
            ),
            separators=(
                separators
            ),
        )
    )

    return [
        (
            split_value,
            split_start,
            split_end,
            capture_group,
        )
        for (
            split_value,
            split_start,
            split_end,
        )
        in split_values
        if split_end
        > split_start
        and split_value.strip()
    ]


def detect_regex_entities(
    text: str,
    *,
    rules: Iterable[
        DetectionRule
    ],
    protocol_name: str | None = None,
    protocol_version: str | None = None,
) -> list[DetectionCandidate]:
    """
    Run configured structured-data regex rules against
    full document text.

    Candidate confidence can be adjusted by:
      - nearby context terms
      - named validator/checksum results

    Rules may optionally expand a captured list into
    multiple independent candidates.

    Results use global character offsets into the
    original text.
    """

    value = str(
        text or ""
    )

    if not value:
        return []

    candidates: list[
        DetectionCandidate
    ] = []

    for rule in rules:
        if not rule.enabled:
            continue

        if not rule.regex_pattern:
            continue

        try:
            pattern = re.compile(
                rule.regex_pattern,
                re.IGNORECASE,
            )

        except re.error as exc:
            raise RuntimeError(
                "Invalid regex for rule "
                f"{rule.rule_id}: {exc}"
            ) from exc

        for match in pattern.finditer(
            value
        ):
            segments = (
                _candidate_segments_for_match(
                    match,
                    rule,
                )
            )

            for (
                detected_value,
                start_offset,
                end_offset,
                capture_group,
            ) in segments:
                if not detected_value:
                    continue

                if (
                    end_offset
                    <= start_offset
                ):
                    continue

                context_matches = (
                    find_context_matches(
                        value,
                        candidate_start=(
                            start_offset
                        ),
                        candidate_end=(
                            end_offset
                        ),
                        context_terms=(
                            rule.context_terms
                        ),
                    )
                )

                matched_context_terms = (
                    get_context_terms(
                        context_matches
                    )
                )

                context_boost = (
                    context_confidence_boost(
                        context_matches
                    )
                    if rule.context_terms
                    else 0.0
                )

                validation_result: (
                    bool
                    | None
                ) = None

                if rule.validator:
                    validation_result = (
                        run_validator(
                            rule.validator,
                            detected_value,
                        )
                    )

                confidence = (
                    float(
                        rule.base_confidence
                    )
                    + context_boost
                    + _validation_adjustment(
                        validation_result
                    )
                )

                confidence = (
                    _clamp_confidence(
                        confidence
                    )
                )

                validation_status = ""

                if (
                    validation_result
                    is True
                ):
                    validation_status = (
                        "valid"
                    )

                elif (
                    validation_result
                    is False
                ):
                    validation_status = (
                        "invalid"
                    )

                elif rule.validator:
                    validation_status = (
                        "unknown"
                    )

                #
                # A configured validator that explicitly
                # rejects a value is rejected by default.
                #
                if (
                    rule.validator
                    and validation_result
                    is False
                ):
                    continue

                methods = list(
                    rule.methods
                )

                if (
                    matched_context_terms
                    and "context"
                    not in methods
                ):
                    methods.append(
                        "context"
                    )

                if (
                    rule.validator
                    and "validator"
                    not in methods
                ):
                    methods.append(
                        "validator"
                    )

                if (
                    rule.metadata.get(
                        "split_capture",
                        False,
                    )
                    and "list_split"
                    not in methods
                ):
                    methods.append(
                        "list_split"
                    )

                candidates.append(
                    DetectionCandidate(
                        entity_type=(
                            rule.entity_type
                        ),
                        entity_subtype=(
                            rule.entity_subtype
                        ),
                        detected_value=(
                            detected_value
                        ),
                        normalized_value=(
                            detected_value
                            .strip()
                        ),
                        start_offset=(
                            start_offset
                        ),
                        end_offset=(
                            end_offset
                        ),
                        confidence=(
                            confidence
                        ),
                        detector_name=(
                            DETECTOR_NAME
                        ),
                        detector_version=(
                            DETECTOR_VERSION
                        ),
                        detection_rule=(
                            rule.rule_id
                        ),
                        protocol_name=str(
                            protocol_name
                            or ""
                        ),
                        protocol_version=str(
                            protocol_version
                            or ""
                        ),
                        reportability=(
                            "UNCLASSIFIED"
                        ),
                        methods=methods,
                        context_terms=(
                            matched_context_terms
                        ),
                        validation_status=(
                            validation_status
                        ),
                        validation_method=(
                            rule.validator
                        ),
                        metadata={
                            "framework": list(
                                rule.framework
                            ),
                            "country": (
                                rule.country
                            ),
                            "base_confidence": (
                                rule.base_confidence
                            ),
                            "context_boost": (
                                context_boost
                            ),
                            "validator_result": (
                                validation_result
                            ),
                            "rule_metadata": dict(
                                rule.metadata
                            ),
                            "capture_group": (
                                capture_group
                            ),
                            "split_capture": bool(
                                rule.metadata.get(
                                    "split_capture",
                                    False,
                                )
                            ),
                        },
                    )
                )

    candidates.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
            candidate.detection_rule,
        )
    )

    return candidates