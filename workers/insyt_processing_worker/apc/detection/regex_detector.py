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
DETECTOR_VERSION = "v1"


def _clamp_confidence(value: float) -> float:
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


def detect_regex_entities(
    text: str,
    *,
    rules: Iterable[DetectionRule],
    protocol_name: str | None = None,
    protocol_version: str | None = None,
) -> list[DetectionCandidate]:
    """
    Run configured structured-data regex rules against full document text.

    Candidate confidence can be adjusted by:
      - nearby context terms
      - named validator/checksum results

    Results use global character offsets into the original text.
    """

    value = str(text or "")

    if not value:
        return []

    candidates: list[DetectionCandidate] = []

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
                f"Invalid regex for rule {rule.rule_id}: {exc}"
            ) from exc

        for match in pattern.finditer(value):
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
                        match.group(capture_group)
                        or ""
                    )

                    start_offset = int(
                        match.start(capture_group)
                    )

                    end_offset = int(
                        match.end(capture_group)
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
                continue

            if end_offset <= start_offset:
                continue

            context_matches = find_context_matches(
                value,
                candidate_start=start_offset,
                candidate_end=end_offset,
                context_terms=rule.context_terms,
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

            validation_result: bool | None = None

            if rule.validator:
                validation_result = run_validator(
                    rule.validator,
                    detected_value,
                )

            confidence = (
                float(rule.base_confidence)
                + context_boost
                + _validation_adjustment(
                    validation_result
                )
            )

            confidence = _clamp_confidence(
                confidence
            )

            validation_status = ""

            if validation_result is True:
                validation_status = "valid"

            elif validation_result is False:
                validation_status = "invalid"

            elif rule.validator:
                validation_status = "unknown"

            #
            # A configured validator that explicitly rejects a value
            # is treated as a rejected candidate by default.
            #
            if (
                rule.validator
                and validation_result is False
            ):
                continue

            methods = list(
                rule.methods
            )

            if (
                matched_context_terms
                and "context" not in methods
            ):
                methods.append(
                    "context"
                )

            if (
                rule.validator
                and "validator" not in methods
            ):
                methods.append(
                    "validator"
                )

            candidates.append(
                DetectionCandidate(
                    entity_type=rule.entity_type,
                    entity_subtype=rule.entity_subtype,
                    detected_value=detected_value,
                    normalized_value=detected_value.strip(),
                    start_offset=start_offset,
                    end_offset=end_offset,
                    confidence=confidence,
                    detector_name=DETECTOR_NAME,
                    detector_version=DETECTOR_VERSION,
                    detection_rule=rule.rule_id,
                    protocol_name=str(
                        protocol_name
                        or ""
                    ),
                    protocol_version=str(
                        protocol_version
                        or ""
                    ),
                    reportability="UNCLASSIFIED",
                    methods=methods,
                    context_terms=matched_context_terms,
                    validation_status=validation_status,
                    validation_method=rule.validator,
                    metadata={
                        "framework": list(
                            rule.framework
                        ),
                        "country": rule.country,
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
                        "capture_group": capture_group,
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