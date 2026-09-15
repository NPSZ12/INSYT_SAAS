from __future__ import annotations

from uuid import uuid4

from .models import (
    AiExtractionRow,
    AiExtractionSourceDocument,
)


def _new_ai_entity_id() -> str:
    return (
        "AIENT-"
        + uuid4().hex[:16].upper()
    )


def build_detection_projection_rows(
    documents: list[
        AiExtractionSourceDocument
    ],
) -> list[AiExtractionRow]:
    """
    First-pass extraction projection.

    This intentionally does NOT perform contextual
    AI grouping yet.

    It proves:
      - set lineage
      - document lineage
      - detection lineage
      - CSV generation

    Each detection hit temporarily becomes one
    extraction row.

    Contextual grouping into logical AI Entities
    is the next layer.
    """

    output: list[AiExtractionRow] = []

    for document in documents:
        for hit in document.hits:
            entity_type = str(
                hit.get("entity_type")
                or ""
            ).strip()

            detected_value = str(
                hit.get("detected_value")
                or hit.get("text")
                or ""
            ).strip()

            if (
                not entity_type
                or not detected_value
            ):
                continue

            confidence_raw = hit.get(
                "confidence"
            )

            try:
                confidence = (
                    float(confidence_raw)
                    if confidence_raw
                    is not None
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = None

            page_raw = hit.get(
                "page_number"
            )

            try:
                source_page = (
                    int(page_raw)
                    if page_raw
                    is not None
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                source_page = None

            output.append(
                AiExtractionRow(
                    ai_entity_id=(
                        _new_ai_entity_id()
                    ),
                    processing_set_id=(
                        document
                        .processing_set_id
                    ),
                    source_job_id=(
                        document
                        .source_job_id
                    ),
                    source_file_id=(
                        document
                        .source_file_id
                    ),
                    source_doc_id=(
                        document
                        .source_doc_id
                    ),
                    source_filename=(
                        document
                        .source_filename
                    ),
                    source_page=source_page,
                    detection_job_id=str(
                        hit.get(
                            "detection_job_id"
                        )
                        or document
                        .detection_job_id
                        or ""
                    ),
                    extraction_confidence=(
                        confidence
                    ),
                    extracted_values={
                        entity_type:
                            detected_value,
                    },
                )
            )

    return output