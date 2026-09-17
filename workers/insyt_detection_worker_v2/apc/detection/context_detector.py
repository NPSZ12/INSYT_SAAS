from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ContextMatch:
    term: str
    start_offset: int
    end_offset: int
    distance: int
    direction: str


def normalize_context_term(value: str) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .casefold()
        .split()
    )


def _term_pattern(term: str) -> re.Pattern[str]:
    """
    Build a case-insensitive context-term matcher.

    Spaces in the configured term may match ordinary spaces,
    tabs, line breaks, underscores, or hyphens.
    """
    normalized = normalize_context_term(term)

    if not normalized:
        return re.compile(r"(?!x)x")

    pieces = [
        re.escape(piece)
        for piece in normalized.split(" ")
        if piece
    ]

    pattern = r"[\s_-]+".join(pieces)

    return re.compile(
        rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def find_context_matches(
    text: str,
    *,
    candidate_start: int,
    candidate_end: int,
    context_terms: Iterable[str],
    window_chars: int = 120,
) -> list[ContextMatch]:
    """
    Find configured context terms near a candidate entity.

    Offsets returned here are global offsets into the full text.
    """
    value = str(text or "")

    if not value:
        return []

    start = max(
        0,
        int(candidate_start) - int(window_chars),
    )

    end = min(
        len(value),
        int(candidate_end) + int(window_chars),
    )

    window = value[start:end]

    matches: list[ContextMatch] = []

    seen: set[tuple[str, int, int]] = set()

    for raw_term in context_terms:
        term = normalize_context_term(raw_term)

        if not term:
            continue

        pattern = _term_pattern(term)

        for match in pattern.finditer(window):
            global_start = start + match.start()
            global_end = start + match.end()

            if global_end <= candidate_start:
                distance = candidate_start - global_end
                direction = "before"

            elif global_start >= candidate_end:
                distance = global_start - candidate_end
                direction = "after"

            else:
                distance = 0
                direction = "overlap"

            key = (
                term,
                global_start,
                global_end,
            )

            if key in seen:
                continue

            seen.add(key)

            matches.append(
                ContextMatch(
                    term=term,
                    start_offset=global_start,
                    end_offset=global_end,
                    distance=distance,
                    direction=direction,
                )
            )

    matches.sort(
        key=lambda item: (
            item.distance,
            0 if item.direction == "before" else 1,
            item.start_offset,
            item.term,
        )
    )

    return matches


def context_confidence_boost(
    matches: list[ContextMatch],
    *,
    strong_window: int = 30,
    medium_window: int = 75,
) -> float:
    """
    Return a confidence boost based on nearby context.

    Intended to be added to a detector's base score and then capped at 1.0.
    """
    if not matches:
        return 0.0

    nearest = min(
        match.distance
        for match in matches
    )

    if nearest <= strong_window:
        return 0.15

    if nearest <= medium_window:
        return 0.10

    return 0.05


def get_context_terms(
    matches: list[ContextMatch],
) -> list[str]:
    """
    Return unique matched terms in nearest-first order.
    """
    terms: list[str] = []
    seen: set[str] = set()

    for match in matches:
        if match.term in seen:
            continue

        seen.add(match.term)
        terms.append(match.term)

    return terms