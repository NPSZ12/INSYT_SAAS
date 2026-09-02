from __future__ import annotations

import os
import re
from typing import Any

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from .models import DetectionCandidate


DETECTOR_NAME = "azure_language"
DETECTOR_VERSION = "v2"

MAX_TEXT_CHARS_PER_REQUEST = 5000


#
# Context labels that strongly identify a DateTime value
# as a patient's date of birth.
#
_DOB_CONTEXT_RE = re.compile(
    r"\b("
    r"dob|"
    r"d\.o\.b\.|"
    r"date\s+of\s+birth|"
    r"birth\s*date|"
    r"birthdate|"
    r"born"
    r")\b"
    r"[\s:#\-]*$",
    re.IGNORECASE,
)


#
# Common clinical conditions/diseases that Azure PHI can
# occasionally classify as Person or another broad type.
#
# This is intentionally conservative. It is not intended
# to replace a clinical terminology service.
#
_CLINICAL_CONDITION_TERMS = {
    "arthritis",
    "asthma",
    "cancer",
    "copd",
    "diabetes",
    "diarrhea",
    "prediabetes",
    "epilepsy",
    "fibromyalgia",
    "gout",
    "hypertension",
    "hypothyroidism",
    "migraine",
    "migraines",
    "obesity",
    "pneumonia",
    "sepsis",
}


def _get_language_client() -> TextAnalyticsClient:
    endpoint = (
        os.getenv("AZURE_LANGUAGE_ENDPOINT")
        or os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT")
        or ""
    ).strip()

    key = (
        os.getenv("AZURE_LANGUAGE_KEY")
        or os.getenv("AZURE_TEXT_ANALYTICS_KEY")
        or ""
    ).strip()

    if not endpoint or not key:
        raise RuntimeError(
            "Azure Language PII detection credentials are missing. "
            "Set AZURE_LANGUAGE_ENDPOINT and AZURE_LANGUAGE_KEY."
        )

    return TextAnalyticsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )


def _chunk_text(
    text: str,
) -> list[tuple[int, str]]:
    value = str(text or "")

    if not value:
        return []

    chunks: list[tuple[int, str]] = []

    start = 0

    while start < len(value):
        end = min(
            len(value),
            start + MAX_TEXT_CHARS_PER_REQUEST,
        )

        chunk = value[start:end]

        if chunk:
            chunks.append(
                (
                    start,
                    chunk,
                )
            )

        start = end

    return chunks


def _detect_chunk(
    client: TextAnalyticsClient,
    text: str,
    *,
    domain_filter: str | None = None,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "language": "en",
        "disable_service_logs": True,
    }

    if domain_filter:
        kwargs["domain_filter"] = (
            domain_filter
        )

    results = client.recognize_pii_entities(
        documents=[text],
        **kwargs,
    )

    if not results:
        return []

    document = results[0]

    if getattr(
        document,
        "is_error",
        False,
    ):
        error = getattr(
            document,
            "error",
            None,
        )

        raise RuntimeError(
            "Azure Language PII detection failed: "
            f"{error}"
        )

    entities: list[
        dict[str, Any]
    ] = []

    for entity in getattr(
        document,
        "entities",
        [],
    ) or []:
        entities.append(
            {
                "text": str(
                    getattr(
                        entity,
                        "text",
                        "",
                    )
                    or ""
                ),
                "category": str(
                    getattr(
                        entity,
                        "category",
                        "",
                    )
                    or ""
                ),
                "subcategory": (
                    str(
                        getattr(
                            entity,
                            "subcategory",
                            "",
                        )
                        or ""
                    )
                    or None
                ),
                "confidence": float(
                    getattr(
                        entity,
                        "confidence_score",
                        0.0,
                    )
                    or 0.0
                ),
                "offset": int(
                    getattr(
                        entity,
                        "offset",
                        0,
                    )
                    or 0
                ),
                "length": int(
                    getattr(
                        entity,
                        "length",
                        0,
                    )
                    or 0
                ),
            }
        )

    return entities


def _normalize_entity_key(
    value: str,
) -> str:
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _context_before(
    full_text: str,
    start_offset: int,
    *,
    max_chars: int = 80,
) -> str:
    start = max(
        0,
        int(start_offset)
        - max_chars,
    )

    return str(
        full_text[
            start:start_offset
        ]
    )


def _context_after(
    full_text: str,
    end_offset: int,
    *,
    max_chars: int = 80,
) -> str:
    end = min(
        len(full_text),
        int(end_offset)
        + max_chars,
    )

    return str(
        full_text[
            end_offset:end
        ]
    )


def _looks_like_dob_context(
    full_text: str,
    start_offset: int,
) -> bool:
    before = _context_before(
        full_text,
        start_offset,
        max_chars=60,
    )

    #
    # Limit this to the current line / immediate label
    # so a DOB elsewhere in the paragraph does not
    # accidentally reclassify another date.
    #
    line_before = (
        before
        .rsplit("\n", 1)[-1]
        .strip()
    )

    return bool(
        _DOB_CONTEXT_RE.search(
            line_before
        )
    )


def _looks_like_clinical_condition(
    detected_value: str,
) -> bool:
    normalized = (
        " ".join(
            str(
                detected_value
                or ""
            )
            .strip()
            .casefold()
            .split()
        )
    )

    if not normalized:
        return False

    return (
        normalized
        in _CLINICAL_CONDITION_TERMS
    )


def _normalize_azure_entity(
    *,
    full_text: str,
    detected_value: str,
    category: str,
    subcategory: str,
    start_offset: int,
    end_offset: int,
    phi_domain: bool,
) -> tuple[
    str,
    str,
    dict[str, Any],
]:
    """
    Normalize Azure output into INSYT entity semantics.

    This layer is intentionally conservative.

    It handles only corrections that are strongly supported by
    immediate context or by a known clinical lexical match.
    Broader protocol/reportability validation remains downstream.
    """

    original_category = str(
        category or "Unknown"
    ).strip()

    original_subcategory = str(
        subcategory or ""
    ).strip()

    entity_type = (
        original_category
        or "Unknown"
    )

    entity_subtype = (
        original_subcategory
    )

    normalization_metadata: dict[
        str,
        Any,
    ] = {
        "azure_original_category": (
            original_category
        ),
        "azure_original_subcategory": (
            original_subcategory
        ),
        "azure_entity_reclassified": False,
    }

    normalized_category = (
        _normalize_entity_key(
            original_category
        )
    )

    #
    # DOB contextual reclassification.
    #
    # Azure commonly returns dates as DateTime. When the
    # immediate source context identifies the value as DOB,
    # INSYT should expose the canonical DateOfBirth type.
    #
    if (
        normalized_category
        in {
            "datetime",
            "date",
        }
        and _looks_like_dob_context(
            full_text,
            start_offset,
        )
    ):
        entity_type = "DateOfBirth"
        entity_subtype = (
            original_category
        )

        normalization_metadata.update(
            {
                "azure_entity_reclassified": (
                    True
                ),
                "reclassification_reason": (
                    "dob_context"
                ),
                "reclassified_from": (
                    original_category
                ),
                "reclassified_to": (
                    "DateOfBirth"
                ),
            }
        )

        return (
            entity_type,
            entity_subtype,
            normalization_metadata,
        )

    #
    # Narrow clinical PHI correction.
    #
    # Azure PHI occasionally labels disease/condition names
    # as Person. A recognized condition term should instead
    # become MedicalCondition.
    #
    if (
        phi_domain
        and normalized_category
        in {
            "person",
            "persontype",
        }
        and _looks_like_clinical_condition(
            detected_value
        )
    ):
        entity_type = (
            "MedicalCondition"
        )

        entity_subtype = (
            "ClinicalCondition"
        )

        normalization_metadata.update(
            {
                "azure_entity_reclassified": (
                    True
                ),
                "reclassification_reason": (
                    "known_clinical_condition"
                ),
                "reclassified_from": (
                    original_category
                ),
                "reclassified_to": (
                    "MedicalCondition"
                ),
            }
        )

        return (
            entity_type,
            entity_subtype,
            normalization_metadata,
        )

    return (
        entity_type,
        entity_subtype,
        normalization_metadata,
    )


def _to_candidate(
    entity: dict[str, Any],
    *,
    full_text: str,
    chunk_start: int,
    detector_name: str,
    detection_rule: str,
    protocol_name: str | None,
    protocol_version: str | None,
    phi_domain: bool,
) -> DetectionCandidate | None:
    detected_value = str(
        entity.get("text")
        or ""
    )

    if not detected_value:
        return None

    local_offset = int(
        entity.get("offset")
        or 0
    )

    length = int(
        entity.get("length")
        or len(detected_value)
    )

    start_offset = (
        chunk_start
        + local_offset
    )

    end_offset = (
        start_offset
        + length
    )

    if start_offset < 0:
        return None

    if end_offset <= start_offset:
        return None

    original_category = str(
        entity.get("category")
        or "Unknown"
    )

    original_subcategory = str(
        entity.get("subcategory")
        or ""
    )

    (
        entity_type,
        entity_subtype,
        normalization_metadata,
    ) = _normalize_azure_entity(
        full_text=full_text,
        detected_value=(
            detected_value
        ),
        category=original_category,
        subcategory=(
            original_subcategory
        ),
        start_offset=start_offset,
        end_offset=end_offset,
        phi_domain=phi_domain,
    )

    return DetectionCandidate(
        entity_type=entity_type,
        entity_subtype=(
            entity_subtype
        ),
        detected_value=(
            detected_value
        ),
        normalized_value=(
            detected_value.strip()
        ),
        start_offset=start_offset,
        end_offset=end_offset,
        confidence=float(
            entity.get("confidence")
            or 0.0
        ),
        detector_name=(
            detector_name
        ),
        detector_version=(
            DETECTOR_VERSION
        ),
        detection_rule=(
            detection_rule
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
        methods=["ner"],
        metadata={
            "azure_offset": (
                local_offset
            ),
            "azure_length": (
                length
            ),
            "chunk_start_offset": (
                chunk_start
            ),
            "phi_domain": (
                phi_domain
            ),
            "service": (
                "Azure AI Language"
            ),
            "operation": (
                "recognize_pii_entities"
            ),
            **normalization_metadata,
        },
    )


def detect_azure_entities(
    text: str,
    *,
    include_phi: bool = True,
    protocol_name: str | None = None,
    protocol_version: str | None = None,
) -> list[DetectionCandidate]:
    """
    Run Azure Language PII and optional PHI detection.

    Returns normalized DetectionCandidate objects using
    global character offsets into the complete input text.
    """

    value = str(text or "")

    if not value.strip():
        return []

    client = _get_language_client()

    candidates: list[
        DetectionCandidate
    ] = []

    for (
        chunk_start,
        chunk,
    ) in _chunk_text(value):
        pii_entities = _detect_chunk(
            client,
            chunk,
            domain_filter=None,
        )

        for entity in pii_entities:
            candidate = _to_candidate(
                entity,
                full_text=value,
                chunk_start=(
                    chunk_start
                ),
                detector_name=(
                    "azure_language_pii"
                ),
                detection_rule=(
                    "azure_language_pii"
                ),
                protocol_name=(
                    protocol_name
                ),
                protocol_version=(
                    protocol_version
                ),
                phi_domain=False,
            )

            if candidate is not None:
                candidates.append(
                    candidate
                )

        if include_phi:
            phi_entities = (
                _detect_chunk(
                    client,
                    chunk,
                    domain_filter="phi",
                )
            )

            for entity in phi_entities:
                candidate = (
                    _to_candidate(
                        entity,
                        full_text=value,
                        chunk_start=(
                            chunk_start
                        ),
                        detector_name=(
                            "azure_language_phi"
                        ),
                        detection_rule=(
                            "azure_language_phi"
                        ),
                        protocol_name=(
                            protocol_name
                        ),
                        protocol_version=(
                            protocol_version
                        ),
                        phi_domain=True,
                    )
                )

                if candidate is not None:
                    candidates.append(
                        candidate
                    )

    #
    # Azure can return the same entity from both the
    # general PII request and PHI-domain request.
    #
    # Preserve the first occurrence while removing exact
    # duplicates after INSYT normalization.
    #
    unique_candidates: list[
        DetectionCandidate
    ] = []

    seen: set[tuple] = set()

    for candidate in candidates:
        key = (
            candidate.entity_type.casefold(),
            candidate.entity_subtype.casefold(),
            candidate.detected_value.casefold(),
            candidate.start_offset,
            candidate.end_offset,
        )

        if key in seen:
            continue

        seen.add(key)

        unique_candidates.append(
            candidate
        )

    unique_candidates.sort(
        key=lambda candidate: (
            candidate.start_offset,
            candidate.end_offset,
            candidate.entity_type,
        )
    )

    return unique_candidates