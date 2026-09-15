from __future__ import annotations

from collections.abc import Callable

from .models import AiExtractionSourceDocument


TextBlobReader = Callable[[str], str | None]


def attach_source_text(
    *,
    documents: list[AiExtractionSourceDocument],
    project_base_path: str,
    read_text_blob: TextBlobReader,
) -> list[AiExtractionSourceDocument]:
    """
    Attach durable staged source text to AI Extraction
    documents.

    APC review staging stores text at:

        {project_base_path}/processing_center/staged/
        {source_job_id}/text/{doc_id}.txt

    The temporary Detection worker text_path is not used
    as downstream storage provenance.
    """

    clean_base = str(
        project_base_path or ""
    ).strip().rstrip("/")

    enriched: list[
        AiExtractionSourceDocument
    ] = []

    for document in documents:
        job_id = str(
            document.source_job_id or ""
        ).strip()

        doc_id = str(
            document.source_doc_id or ""
        ).strip()

        if not clean_base or not job_id or not doc_id:
            enriched.append(document)
            continue

        blob_path = (
            f"{clean_base}/"
            "processing_center/staged/"
            f"{job_id}/text/{doc_id}.txt"
        )

        try:
            source_text = (
                read_text_blob(
                    blob_path
                )
                or ""
            )
        except Exception:
            source_text = ""

        if source_text:
            document.text_blob_path = (
                blob_path
            )

            document.source_text = (
                source_text
            )

        enriched.append(
            document
        )

    return enriched