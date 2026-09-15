from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .csv_writer import build_ai_extraction_csv
from .detection_loader import attach_detection_results
from .extractor import build_detection_projection_rows
from .set_builder import load_processing_set_documents


def build_processing_set_ai_extraction(
    *,
    job_id: str,
    set_id: str,
    project_base_path: str,
    read_json_blob: Callable[[str], Any],
    read_text_blob: Callable[
        [str],
        str | None,
    ],
) -> dict[str, Any]:
    """
    Build the AI Extraction artifact for one persisted APC
    Processing Set.

    This stage is downstream of ingestion and Detection.

    It does not:
      - rerun ingestion
      - recreate Processing Sets
      - rerun OCR
      - rerun Detection
      - depend on worker-local SQLite state
    """

    documents = load_processing_set_documents(
        project_base_path=project_base_path,
        job_id=job_id,
        set_id=set_id,
        read_json_blob=read_json_blob,
    )

    documents = attach_detection_results(
        documents=documents,
        project_base_path=project_base_path,
        read_json_blob=read_json_blob,
    )

    documents = attach_source_text(
        documents=documents,
        project_base_path=project_base_path,
        read_text_blob=read_text_blob,
    )

    extraction_rows = (
        build_detection_projection_rows(
            documents
        )
    )

    csv_bytes = build_ai_extraction_csv(
        extraction_rows
    )

    documents_with_hits = sum(
        1
        for document in documents
        if document.hits
    )

    return {
        "job_id": job_id,
        "set_id": set_id,
        "document_count": len(
            documents
        ),
        "documents_with_hits": (
            documents_with_hits
        ),
        "ai_entity_count": len(
            extraction_rows
        ),
        "documents": documents,
        "rows": extraction_rows,
        "csv_bytes": csv_bytes,
    }