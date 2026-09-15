from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AiExtractionSourceDocument:
    processing_set_id: str
    processing_set_number: int
    processing_set_ordinal: int

    source_job_id: str
    source_file_id: str
    source_doc_id: str
    source_filename: str

    detection_job_id: str = ""
    text_path: str = ""
    text_source: str = ""
    text_blob_path: str = ""
    source_text: str = ""

    hits: list[dict[str, Any]] = field(
        default_factory=list
    )


@dataclass
class AiExtractionRow:
    ai_entity_id: str
    processing_set_id: str

    source_job_id: str
    source_file_id: str
    source_doc_id: str
    source_filename: str

    source_page: int | None = None
    source_record_id: str = ""
    source_field: str = ""
    source_text: str = ""

    detection_job_id: str = ""
    extraction_confidence: float | None = None

    extracted_values: dict[str, Any] = field(
        default_factory=dict
    )