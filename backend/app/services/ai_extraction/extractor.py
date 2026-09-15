from __future__ import annotations

from uuid import uuid4

from .models import (
    AiExtractionRow,
    AiExtractionSourceDocument,
)


DEFAULT_GROUP_GAP_CHARS = 150
DEFAULT_CONTEXT_PADDING_CHARS = 80


def _new_ai_entity_id() -> str:
    return (
        "AIENT-"
        + uuid4().hex[:16].upper()
    )


def _safe_int(
    value,
) -> int | None:
    try:
        if value is None:
            return None

        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _safe_float(
    value,
) -> float | None:
    try:
        if value is None:
            return None

        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _hit_start(
    hit: dict,
) -> int | None:
    return _safe_int(
        hit.get("start_offset")
    )


def _hit_end(
    hit: dict,
) -> int | None:
    return _safe_int(
        hit.get("end_offset")
    )


def _hit_entity_type(
    hit: dict,
) -> str:
    return str(
        hit.get("entity_type")
        or ""
    ).strip()


def _hit_detected_value(
    hit: dict,
) -> str:
    return str(
        hit.get("detected_value")
        or hit.get("text")
        or ""
    ).strip()


def _source_context(
    *,
    source_text: str,
    start_offset: int | None,
    end_offset: int | None,
) -> str:
    if not source_text:
        return ""

    if (
        start_offset is None
        or end_offset is None
    ):
        return source_text[
            :500
        ].strip()

    start = max(
        0,
        start_offset
        - DEFAULT_CONTEXT_PADDING_CHARS,
    )

    end = min(
        len(source_text),
        end_offset
        + DEFAULT_CONTEXT_PADDING_CHARS,
    )

    return source_text[
        start:end
    ].strip()


def _should_start_new_group(
    *,
    current_hits: list[dict],
    next_hit: dict,
) -> bool:
    if not current_hits:
        return False

    next_type = _hit_entity_type(
        next_hit
    )

    if not next_type:
        return False

    existing_types = {
        _hit_entity_type(hit)
        for hit in current_hits
        if _hit_entity_type(hit)
    }

    #
    # A repeated field type is a useful boundary signal.
    #
    # Example:
    #   Person: John Smith
    #   DOB: ...
    #   Address: ...
    #   Person: Jane Smith
    #
    # The second Person should begin another candidate
    # rather than overwrite the first Person field.
    #
    if next_type in existing_types:
        return True

    previous_hit = current_hits[-1]

    previous_end = _hit_end(
        previous_hit
    )

    next_start = _hit_start(
        next_hit
    )

    if (
        previous_end is None
        or next_start is None
    ):
        return False

    gap = (
        next_start
        - previous_end
    )

    return (
        gap
        > DEFAULT_GROUP_GAP_CHARS
    )


def _group_document_hits(
    document: AiExtractionSourceDocument,
) -> list[list[dict]]:
    valid_hits = []

    for hit in document.hits:
        if not isinstance(
            hit,
            dict,
        ):
            continue

        entity_type = (
            _hit_entity_type(
                hit
            )
        )

        detected_value = (
            _hit_detected_value(
                hit
            )
        )

        if (
            not entity_type
            or not detected_value
        ):
            continue

        valid_hits.append(
            dict(hit)
        )

    valid_hits.sort(
        key=lambda hit: (
            _hit_start(hit)
            if _hit_start(hit)
            is not None
            else 10**18,
            _hit_end(hit)
            if _hit_end(hit)
            is not None
            else 10**18,
            _hit_entity_type(hit),
        )
    )

    groups: list[
        list[dict]
    ] = []

    current_group: list[
        dict
    ] = []

    for hit in valid_hits:
        if (
            current_group
            and _should_start_new_group(
                current_hits=current_group,
                next_hit=hit,
            )
        ):
            groups.append(
                current_group
            )

            current_group = []

        current_group.append(
            hit
        )

    if current_group:
        groups.append(
            current_group
        )

    return groups


def _build_group_row(
    *,
    document: AiExtractionSourceDocument,
    hits: list[dict],
) -> AiExtractionRow:
    extracted_values = {}

    confidences: list[
        float
    ] = []

    start_offsets: list[
        int
    ] = []

    end_offsets: list[
        int
    ] = []

    page_numbers: list[
        int
    ] = []

    detection_job_id = (
        document.detection_job_id
        or ""
    )

    for hit in hits:
        entity_type = (
            _hit_entity_type(
                hit
            )
        )

        detected_value = (
            _hit_detected_value(
                hit
            )
        )

        if (
            entity_type
            and detected_value
        ):
            extracted_values[
                entity_type
            ] = detected_value

        confidence = _safe_float(
            hit.get("confidence")
        )

        if confidence is not None:
            confidences.append(
                confidence
            )

        start_offset = (
            _hit_start(
                hit
            )
        )

        if start_offset is not None:
            start_offsets.append(
                start_offset
            )

        end_offset = (
            _hit_end(
                hit
            )
        )

        if end_offset is not None:
            end_offsets.append(
                end_offset
            )

        page_number = _safe_int(
            hit.get(
                "page_number"
            )
        )

        if page_number is not None:
            page_numbers.append(
                page_number
            )

        hit_detection_job_id = str(
            hit.get(
                "detection_job_id"
            )
            or ""
        ).strip()

        if hit_detection_job_id:
            detection_job_id = (
                hit_detection_job_id
            )

    group_start = (
        min(start_offsets)
        if start_offsets
        else None
    )

    group_end = (
        max(end_offsets)
        if end_offsets
        else None
    )

    #
    # Use the minimum confidence for the candidate.
    #
    # This is intentionally conservative:
    # the candidate is only as strong as its weakest
    # detected component.
    #
    extraction_confidence = (
        min(confidences)
        if confidences
        else None
    )

    source_page = (
        min(page_numbers)
        if page_numbers
        else None
    )

    source_text = (
        _source_context(
            source_text=(
                document.source_text
                or ""
            ),
            start_offset=group_start,
            end_offset=group_end,
        )
    )

    return AiExtractionRow(
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
        source_record_id="",
        source_field="",
        source_text=source_text,
        detection_job_id=(
            detection_job_id
        ),
        extraction_confidence=(
            extraction_confidence
        ),
        extracted_values=(
            extracted_values
        ),
    )


def build_detection_projection_rows(
    documents: list[
        AiExtractionSourceDocument
    ],
) -> list[AiExtractionRow]:
    """
    Build contextual AI candidate rows from existing
    Data Element Detection hits.

    Detection answers:
        What sensitive/data elements were found?

    This layer answers:
        Which nearby elements appear to belong to
        the same logical source entity?

    Grouping is currently deterministic and based on:
      - source document
      - character proximity
      - repeated entity-type boundaries

    It does not rerun Detection and does not modify
    ingestion or OCR behavior.
    """

    output: list[
        AiExtractionRow
    ] = []

    for document in documents:
        groups = (
            _group_document_hits(
                document
            )
        )

        for hits in groups:
            if not hits:
                continue

            output.append(
                _build_group_row(
                    document=document,
                    hits=hits,
                )
            )

    return output