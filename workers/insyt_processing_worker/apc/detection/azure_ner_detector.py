from __future__ import annotations

import os
from typing import Any

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from .models import DetectionCandidate


DETECTOR_NAME = "azure_language"
DETECTOR_VERSION = "v1"

MAX_TEXT_CHARS_PER_REQUEST = 5000


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


def _chunk_text(text: str) -> list[tuple[int, str]]:
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
        kwargs["domain_filter"] = domain_filter

    results = client.recognize_pii_entities(
        documents=[text],
        **kwargs,
    )

    if not results:
        return []

    document = results[0]

    if getattr(document, "is_error", False):
        error = getattr(
            document,
            "error",
            None,
        )

        raise RuntimeError(
            f"Azure Language PII detection failed: {error}"
        )

    entities: list[dict[str, Any]] = []

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


def _to_candidate(
    entity: dict[str, Any],
    *,
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

    return DetectionCandidate(
        entity_type=str(
            entity.get("category")
            or "Unknown"
        ),
        entity_subtype=str(
            entity.get("subcategory")
            or ""
        ),
        detected_value=detected_value,
        normalized_value=detected_value.strip(),
        start_offset=start_offset,
        end_offset=end_offset,
        confidence=float(
            entity.get("confidence")
            or 0.0
        ),
        detector_name=detector_name,
        detector_version=DETECTOR_VERSION,
        detection_rule=detection_rule,
        protocol_name=str(
            protocol_name
            or ""
        ),
        protocol_version=str(
            protocol_version
            or ""
        ),
        reportability="UNCLASSIFIED",
        methods=["ner"],
        metadata={
            "azure_offset": local_offset,
            "azure_length": length,
            "chunk_start_offset": chunk_start,
            "phi_domain": phi_domain,
            "service": "Azure AI Language",
            "operation": "recognize_pii_entities",
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

    Returns normalized DetectionCandidate objects using global
    character offsets into the complete input text.
    """

    value = str(text or "")

    if not value.strip():
        return []

    client = _get_language_client()

    candidates: list[DetectionCandidate] = []

    for chunk_start, chunk in _chunk_text(value):
        pii_entities = _detect_chunk(
            client,
            chunk,
            domain_filter=None,
        )

        for entity in pii_entities:
            candidate = _to_candidate(
                entity,
                chunk_start=chunk_start,
                detector_name="azure_language_pii",
                detection_rule="azure_language_pii",
                protocol_name=protocol_name,
                protocol_version=protocol_version,
                phi_domain=False,
            )

            if candidate is not None:
                candidates.append(
                    candidate
                )

        if include_phi:
            phi_entities = _detect_chunk(
                client,
                chunk,
                domain_filter="phi",
            )

            for entity in phi_entities:
                candidate = _to_candidate(
                    entity,
                    chunk_start=chunk_start,
                    detector_name="azure_language_phi",
                    detection_rule="azure_language_phi",
                    protocol_name=protocol_name,
                    protocol_version=protocol_version,
                    phi_domain=True,
                )

                if candidate is not None:
                    candidates.append(
                        candidate
                    )

    #
    # Azure can return the same entity from both the general
    # PII request and PHI-domain request.
    #
    # Preserve the first occurrence while removing exact
    # duplicates by entity/type/location/value.
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