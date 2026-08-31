from __future__ import annotations

from typing import Any

from .built_in_rules import get_built_in_rules
from .merge import merge_detection_candidates
from .models import DetectionCandidate
from .post_validation import post_validate_candidates
from .regex_detector import detect_regex_entities


def run_detection_engine(
    text: str,
    *,
    include_phi: bool = True,
    protocol_name: str | None = None,
    protocol_version: str | None = None,
    enable_azure: bool = True,
    enable_structured_rules: bool = True,
) -> dict[str, Any]:
    """
    Run the unified INSYT Data Element Detection engine.

    Current detector stack:
      - Azure AI Language PII / PHI NER
      - INSYT structured regex/context/validator rules
      - candidate merge / deduplication

    Returns normalized DetectionCandidate objects plus detector metrics.
    """

    value = str(text or "")

    if not value.strip():
        return {
            "candidates": [],
            "azure_candidate_count": 0,
            "structured_candidate_count": 0,
            "validated_candidate_count": 0,
            "merged_candidate_count": 0,
            "detectors": [],
        }

    all_candidates: list[DetectionCandidate] = []

    azure_candidates: list[DetectionCandidate] = []
    structured_candidates: list[DetectionCandidate] = []

    detectors_used: list[str] = []

    if enable_azure:
        from .azure_ner_detector import detect_azure_entities

        azure_candidates = detect_azure_entities(
            value,
            include_phi=include_phi,
            protocol_name=protocol_name,
            protocol_version=protocol_version,
        )

        all_candidates.extend(
            azure_candidates
        )

        detectors_used.append(
            "azure_language"
        )

    if enable_structured_rules:
        structured_candidates = detect_regex_entities(
            value,
            rules=get_built_in_rules(),
            protocol_name=protocol_name,
            protocol_version=protocol_version,
        )

        all_candidates.extend(
            structured_candidates
        )

        detectors_used.append(
            "insyt_structured"
        )

    validated_candidates = post_validate_candidates(
        all_candidates,
        text=value,
    )

    merged_candidates = merge_detection_candidates(
        validated_candidates
    )

    return {
        "candidates": merged_candidates,
        "azure_candidate_count": len(
            azure_candidates
        ),
        "structured_candidate_count": len(
            structured_candidates
        ),
        "validated_candidate_count": len(
            validated_candidates
        ),
        "merged_candidate_count": len(
            merged_candidates
        ),
        "detectors": detectors_used,
    }