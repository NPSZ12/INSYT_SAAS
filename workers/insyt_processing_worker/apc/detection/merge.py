from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
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


def _contains_span(
    outer: DetectionCandidate,
    inner: DetectionCandidate,
) -> bool:
    """
    True when outer fully contains inner.

    Exact same spans are not considered nested here because exact
    duplicates are handled earlier in the merge pipeline.
    """

    if (
        outer.start_offset
        == inner.start_offset
        and outer.end_offset
        == inner.end_offset
    ):
        return False

    return (
        outer.start_offset
        <= inner.start_offset
        and outer.end_offset
        >= inner.end_offset
    )


#
# Entity types that represent highly structured values.
#
# A weaker semantic fragment found inside one of these should generally
# not survive as a separate rendered hit.
#
_STRUCTURED_CONTAINER_TYPES = {
    "address",
    "bankaccountnumber",
    "claimnumber",
    "creditcardnumber",
    "dateofbirth",
    "driverslicensenumber",
    "drugenforcementagencynumber",
    "email",
    "emailaddress",
    "faxnumber",
    "healthplanbeneficiarynumber",
    "insuranceid",
    "ipaddress",
    "medicalrecordnumber",
    "memberid",
    "passportnumber",
    "phonenumber",
    "policynumber",
    "socialsecuritynumber",
    "ussocialsecuritynumber",
    "vehicleidentificationnumber",
    "vin",
}


#
# Broad semantic entity types that Azure NER can sometimes emit for
# fragments contained inside more precise structured entities.
#
# Example:
#
#     amber@example.com
#
# Azure may return:
#
#     Email  -> amber@example.com
#     Person -> amber
#
# The Person fragment must not survive simply because it is a different
# entity type.
#
_BROAD_NESTED_TYPES = {
    "person",
    "persontype",
    "organization",
    "location",
    "datetime",
}


def _normalized_entity_type(
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


def _is_structured_container(
    candidate: DetectionCandidate,
) -> bool:
    return (
        _normalized_entity_type(
            candidate
        )
        in _STRUCTURED_CONTAINER_TYPES
    )


def _is_broad_nested_type(
    candidate: DetectionCandidate,
) -> bool:
    return (
        _normalized_entity_type(
            candidate
        )
        in _BROAD_NESTED_TYPES
    )

def _is_insyt_structured_candidate(
    candidate: DetectionCandidate,
) -> bool:
    return (
        str(
            candidate.detector_name
            or ""
        )
        .strip()
        .casefold()
        .startswith("insyt")
    )


def _is_healthcare_provider(
    candidate: DetectionCandidate,
) -> bool:
    return (
        _normalized_entity_type(
            candidate
        )
        == "healthcareprovider"
    )


def _is_person(
    candidate: DetectionCandidate,
) -> bool:
    return (
        _normalized_entity_type(
            candidate
        )
        == "person"
    )


def _provider_containment_winner(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> DetectionCandidate | None:
    """
    Prefer the full INSYT labeled HealthcareProvider span over
    Azure fragments contained within it.

    Example:

        Dr. Robert Davis    <- INSYT structured provider
        Dr.                <- Azure provider fragment
            Robert Davis   <- Azure provider fragment

    The final rendered hit should be the full labeled provider.
    """

    if not (
        _is_healthcare_provider(left)
        and _is_healthcare_provider(right)
    ):
        return None

    if _contains_span(
        left,
        right,
    ):
        outer = left
        inner = right
    elif _contains_span(
        right,
        left,
    ):
        outer = right
        inner = left
    else:
        return None

    if (
        _is_insyt_structured_candidate(
            outer
        )
        and not _is_insyt_structured_candidate(
            inner
        )
    ):
        return outer

    return None


def _person_candidates_are_adjacent(
    left: DetectionCandidate,
    right: DetectionCandidate,
    *,
    text: str,
) -> bool:
    """
    True when two Person candidates are separated only by whitespace
    and are close enough to plausibly be fragments of one name.
    """

    if not (
        _is_person(left)
        and _is_person(right)
    ):
        return False

    if left.end_offset <= right.start_offset:
        first = left
        second = right
    elif right.end_offset <= left.start_offset:
        first = right
        second = left
    else:
        return False

    gap = str(
        text[
            first.end_offset:
            second.start_offset
        ]
    )

    if len(gap) > 3:
        return False

    return bool(
        gap
        and gap.isspace()
    )


def _combine_adjacent_person_candidates(
    left: DetectionCandidate,
    right: DetectionCandidate,
    *,
    text: str,
) -> DetectionCandidate:
    if left.start_offset <= right.start_offset:
        first = left
        second = right
    else:
        first = right
        second = left

    combined_start = int(
        first.start_offset
    )

    combined_end = int(
        second.end_offset
    )

    combined_value = str(
        text[
            combined_start:
            combined_end
        ]
    ).strip()

    winner = (
        left
        if float(left.confidence or 0.0)
        >= float(right.confidence or 0.0)
        else right
    )

    loser = (
        right
        if winner is left
        else left
    )

    merged = _merge_provenance(
        winner,
        loser,
    )

    metadata = {
        **dict(
            merged.metadata
            or {}
        ),
        "adjacent_person_fragments_combined": True,
        "combined_start_offset": combined_start,
        "combined_end_offset": combined_end,
    }

    return replace(
        merged,
        detected_value=combined_value,
        normalized_value=combined_value,
        start_offset=combined_start,
        end_offset=combined_end,
        confidence=max(
            float(left.confidence or 0.0),
            float(right.confidence or 0.0),
        ),
        metadata=metadata,
    )

def _nested_entity_winner(
    left: DetectionCandidate,
    right: DetectionCandidate,
) -> DetectionCandidate | None:
    """
    Resolve cross-type nested entities.

    This is intentionally narrower than ordinary overlap merging.

    We only suppress a cross-type entity when:

      1. one candidate fully contains the other, and
      2. the outer candidate is a recognized structured entity, and
      3. the inner candidate is a broad semantic entity.

    This prevents cases such as:

        Email:  amber@example.com
        Person: amber

    from producing two user-visible hits.

    It does NOT blindly suppress every differently typed overlapping
    entity. Legitimately related PHI/PII entities can still coexist when
    neither one is merely a nested fragment of the other.
    """

    if _contains_span(
        left,
        right,
    ):
        outer = left
        inner = right
    elif _contains_span(
        right,
        left,
    ):
        outer = right
        inner = left
    else:
        return None

    if not _is_structured_container(
        outer
    ):
        return None

    if not _is_broad_nested_type(
        inner
    ):
        return None

    return outer


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
        "entity_type": (
            winner.entity_type
        ),
        "entity_subtype": (
            winner.entity_subtype
        ),
        "detected_value": (
            winner.detected_value
        ),
        "start_offset": (
            winner.start_offset
        ),
        "end_offset": (
            winner.end_offset
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
        "entity_type": (
            loser.entity_type
        ),
        "entity_subtype": (
            loser.entity_subtype
        ),
        "detected_value": (
            loser.detected_value
        ),
        "start_offset": (
            loser.start_offset
        ),
        "end_offset": (
            loser.end_offset
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
            source.get(
                "detector_name"
            ),
            source.get(
                "detection_rule"
            ),
            source.get(
                "confidence"
            ),
            source.get(
                "entity_type"
            ),
            source.get(
                "start_offset"
            ),
            source.get(
                "end_offset"
            ),
        )

        if any(
            (
                item.get(
                    "detector_name"
                ),
                item.get(
                    "detection_rule"
                ),
                item.get(
                    "confidence"
                ),
                item.get(
                    "entity_type"
                ),
                item.get(
                    "start_offset"
                ),
                item.get(
                    "end_offset"
                ),
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
    text: str = "",
    overlap_threshold: float = 0.80,
) -> list[DetectionCandidate]:
    """
    Merge candidates from Azure NER and INSYT structured detectors.

    Behavior:
      - exact duplicates collapse
      - heavily overlapping hits of the same entity type collapse
      - broad semantic fragments fully nested inside stronger structured
        entities collapse into the structured entity
      - provenance from all merged detectors is retained
      - unrelated cross-type overlaps remain separate
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
    # First pass:
    # exact duplicates.
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
            preferred = (
                _prefer_candidate(
                    winner,
                    candidate,
                )
            )

            if preferred is winner:
                winner = (
                    _merge_provenance(
                        winner,
                        candidate,
                    )
                )
            else:
                winner = (
                    _merge_provenance(
                        candidate,
                        winner,
                    )
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
    #
    # 1. Collapse strongly overlapping hits of the
    #    same semantic type.
    #
    # 2. Resolve cross-type nested fragments when a
    #    broad Azure semantic entity is wholly inside
    #    a stronger structured entity.
    #
    final: list[
        DetectionCandidate
    ] = []

    for candidate in exact_merged:
        merged = False

        for index, existing in enumerate(
            final
        ):
            #
            # Same semantic type:
            # retain original overlap behavior.
            #
            if _same_semantic_type(
                candidate,
                existing,
            ):
                #
                # HealthcareProvider is special:
                # the full labeled INSYT span should beat
                # nested Azure fragments regardless of the
                # normal overlap preference.
                #
                provider_winner = (
                    _provider_containment_winner(
                        existing,
                        candidate,
                    )
                )

                if provider_winner is not None:
                    if provider_winner is existing:
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

                #
                # Azure sometimes splits one patient name into
                # adjacent Person fragments.
                #
                if (
                    text
                    and _person_candidates_are_adjacent(
                        existing,
                        candidate,
                        text=text,
                    )
                ):
                    final[index] = (
                        _combine_adjacent_person_candidates(
                            existing,
                            candidate,
                            text=text,
                        )
                    )

                    merged = True
                    break

                ratio = _overlap_ratio(
                    candidate,
                    existing,
                )

                if ratio < overlap_threshold:
                    continue

                preferred = (
                    _prefer_candidate(
                        existing,
                        candidate,
                    )
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

            #
            # Different semantic types:
            # only collapse a narrowly defined nested
            # semantic fragment.
            #
            nested_winner = (
                _nested_entity_winner(
                    existing,
                    candidate,
                )
            )

            if nested_winner is None:
                continue

            if nested_winner is existing:
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