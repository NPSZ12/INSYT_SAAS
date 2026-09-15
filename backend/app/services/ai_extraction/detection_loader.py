from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import AiExtractionSourceDocument


JsonBlobReader = Callable[[str], Any]


def attach_detection_results(
    *,
    documents: list[AiExtractionSourceDocument],
    project_base_path: str,
    read_json_blob: JsonBlobReader,
) -> list[AiExtractionSourceDocument]:
    """
    Enrich Processing Set documents with their existing
    per-document Data Element Detection index.

    No detection is rerun here.

    Expected detection index path:

        {project_base_path}/processing_center/
        detection/documents/{DOC_ID}.json
    """

    enriched: list[AiExtractionSourceDocument] = []

    for document in documents:
        doc_id = str(
            document.source_doc_id or ""
        ).strip()

        if not doc_id:
            enriched.append(document)
            continue

        blob_path = (
            f"{project_base_path}/"
            "processing_center/detection/"
            f"documents/{doc_id}.json"
        )

        try:
            payload = read_json_blob(
                blob_path
            )
        except Exception:
            #
            # A document without a detection index simply
            # contributes no AI Extraction candidates.
            #
            enriched.append(document)
            continue

        if not isinstance(payload, dict):
            enriched.append(document)
            continue

        raw_hits = payload.get(
            "hits"
        ) or []

        hits = [
            dict(hit)
            for hit in raw_hits
            if isinstance(hit, dict)
        ]

        document.detection_job_id = str(
            payload.get(
                "latest_detection_job_id"
            )
            or ""
        ).strip()

        document.text_path = str(
            payload.get("text_path")
            or document.text_path
            or ""
        ).strip()

        document.text_source = str(
            payload.get("text_source")
            or ""
        ).strip()

        document.hits = hits

        enriched.append(document)

    return enriched