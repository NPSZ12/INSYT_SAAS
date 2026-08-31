from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import DetectionCandidate


def _normalize_value(value: str) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .casefold()
        .split()
    )


def _candidate_span_key(
    candidate: DetectionCandidate,
) -> tuple[int, int]:
    return (
        int(candidate.start_offset),
        int(candidate.end_offset),
    )


def _exact_key(
    candidate: DetectionCandidate,
) -> tuple:
    return (
        candidate.entity_type.casefold(),
        candidate.entity_subtype.casefold(),
        _normalize_value(
            candidate.detected_value
        ),
        int(candidate.start_offset),
        int(candidate.end_offset),
    )


def _overlap_length(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> int:
    start = max(
        left.start_offset,
        right.start_offset,
    )

    end = min(
        left.end_offset,
        right.end_offset,
    )

    return max(
        0,
        end - start,
    )


def _span_length(
    candidate: DetectionCandidate,
) -> int:
    return max(
        0,
        candidate.end_offset
        - candidate.start_offset,
    )


def _overlap_ratio(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> float:
    overlap = _overlap_length(
        left,
        right,
    )

    if overlap <= 0:
        return 0.0

    smaller = min(
        _span_length(left),
        _span_length(right),
    )

    if smaller <= 0:
        return 0.0

    return overlap / smaller


def _same_semantic_type(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> bool:
    return (
        left.entity_type.casefold()
        == right.entity_type.casefold()
    )


def _prefer_candidate(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> DetectionCandidate:
    """
    Pick the stronger candidate for the primary rendered hit.

    Preference order:
      1. valid structured candidate
      2. higher confidence
      3. more specific/shorter span
      4. INSYT structured detector over Azure on tie
    """

    left_valid = (
        left.validation_status
        == "valid"
    )

    right_valid = (
        right.validation_status
        == "valid"
    )

    if left_valid != right_valid:
        return left if left_valid else right

    if left.confidence != right.confidence:
        return (
            left
            if left.confidence > right.confidence
            else right
        )

    left_span = _span_length(left)
    right_span = _span_length(right)

    if left_span != right_span:
        return (
            left
            if left_span < right_span
            else right
        )

    left_insyt = (
        left.detector_name
        .casefold()
        .startswith("insyt")
    )

    right_insyt = (
        right.detector_name
        .casefold()
        .startswith("insyt")
    )

    if left_insyt != right_insyt:
        return left if left_insyt else right

    return left


def _merge_provenance(
    winner: DetectionCandidate,
    loser: DetectionCandidate,
) -> DetectionCandidate:
    methods = list(
        winner.methods
    )

    for method in loser.methods:
        if method not in methods:
            methods.append(method)

    context_terms = list(
        winner.context_terms
    )

    for term in loser.context_terms:
        if term not in context_terms:
            context_terms.append(term)

    existing_sources = list(
        winner.metadata.get(
            "merged_sources",
            [],
        )
        or []
    )

    winner_source = {
        "detector_name": (
            winner.detector_name
        ),
        "detector_version": (
            winner.detector_version
        ),
        "detection_rule": (
            winner.detection_rule
        ),
        "confidence": (
            winner.confidence
        ),
        "validation_status": (
            winner.validation_status
        ),
    }

    loser_source = {
        "detector_name": (
            loser.detector_name
        ),
        "detector_version": (
            loser.detector_version
        ),
        "detection_rule": (
            loser.detection_rule
        ),
        "confidence": (
            loser.confidence
        ),
        "validation_status": (
            loser.validation_status
        ),
    }

    merged_sources = []

    for source in (
        existing_sources
        + [
            winner_source,
            loser_source,
        ]
    ):
        key = (
            source.get("detector_name"),
            source.get("detection_rule"),
            source.get("confidence"),
        )

        if any(
            (
                item.get("detector_name"),
                item.get("detection_rule"),
                item.get("confidence"),
            )
            == key
            for item in merged_sources
        ):
            continue

        merged_sources.append(
            source
        )

    winner.methods = methods
    winner.context_terms = (
        context_terms
    )

    winner.metadata = {
        **winner.metadata,
        "merged_sources": (
            merged_sources
        ),
        "merged_detector_count": (
            len(merged_sources)
        ),
    }

    return winner


def merge_detection_candidates(
    candidates: Iterable[
        DetectionCandidate
    ],
    *,
    overlap_threshold: float = 0.80,
) -> list[DetectionCandidate]:
    """
    Merge candidates from Azure NER and INSYT structured detectors.

    Behavior:
      - exact duplicates collapse
      - heavily overlapping hits of the same entity type collapse
      - provenance from both detectors is retained
      - unrelated overlapping entity types remain separate
    """

    incoming = [
        candidate
        for candidate in candidates
        if candidate.end_offset
        > candidate.start_offset
    ]

    if not incoming:
        return []

    incoming.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
            -candidate.confidence,
        )
    )

    #
    # First pass: exact duplicates.
    #
    exact_groups: dict[
        tuple,
        list[DetectionCandidate],
    ] = defaultdict(list)

    for candidate in incoming:
        exact_groups[
            _exact_key(candidate)
        ].append(candidate)

    exact_merged: list[
        DetectionCandidate
    ] = []

    for group in exact_groups.values():
        winner = group[0]

        for candidate in group[1:]:
            preferred = _prefer_candidate(
                winner,
                candidate,
            )

            if preferred is winner:
                winner = _merge_provenance(
                    winner,
                    candidate,
                )
            else:
                winner = _merge_provenance(
                    candidate,
                    winner,
                )

        exact_merged.append(
            winner
        )

    exact_merged.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
        )
    )

    #
    # Second pass:
    # collapse strongly overlapping hits of the same entity type.
    #
    final: list[
        DetectionCandidate
    ] = []

    for candidate in exact_merged:
        merged = False

        for index, existing in enumerate(
            final
        ):
            if not _same_semantic_type(
                candidate,
                existing,
            ):
                continue

            ratio = _overlap_ratio(
                candidate,
                existing,
            )

            if ratio < overlap_threshold:
                continue

            preferred = _prefer_candidate(
                existing,
                candidate,
            )

            if preferred is existing:
                final[index] = (
                    _merge_provenance(
                        existing,
                        candidate,
                    )
                )
            else:
                final[index] = (
                    _merge_provenance(
                        candidate,
                        existing,
                    )
                )

            merged = True
            break

        if not merged:
            final.append(
                candidate
            )

    final.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
        )
    )

    return final