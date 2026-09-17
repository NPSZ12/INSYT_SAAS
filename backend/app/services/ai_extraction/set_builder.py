from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import AiExtractionSourceDocument


JsonBlobReader = Callable[[str], Any]


def load_processing_set_documents(
    *,
    project_base_path: str,
    job_id: str,
    set_id: str,
    read_json_blob: JsonBlobReader,
    selected_doc_ids: set[str] | None = None,
) -> list[AiExtractionSourceDocument]:
    """
    Load one persisted APC Processing Set from Azure storage.

    The processing worker persists Processing Set membership at:

        {project_base_path}/processing_center/jobs/
        {job_id}/processing_sets/{set_id}.json

    This deliberately does not read the API's local SQLite database.
    The Azure manifest is the durable bridge between APC Processing
    Sets and downstream AI Extraction.
    """

    clean_project_base = str(
        project_base_path or ""
    ).strip().rstrip("/")

    clean_job_id = str(
        job_id or ""
    ).strip()

    clean_set_id = str(
        set_id or ""
    ).strip()

    clean_selected_doc_ids = {
        str(doc_id or "").strip()
        for doc_id in (
            selected_doc_ids
            or set()
        )
        if str(doc_id or "").strip()
    }

    if not clean_project_base:
        raise ValueError(
            "project_base_path is required."
        )

    if not clean_job_id:
        raise ValueError(
            "job_id is required."
        )

    if not clean_set_id:
        raise ValueError(
            "set_id is required."
        )

    manifest_blob_path = (
        f"{clean_project_base}/"
        "processing_center/jobs/"
        f"{clean_job_id}/processing_sets/"
        f"{clean_set_id}.json"
    )

    payload = read_json_blob(
        manifest_blob_path
    )

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Processing Set manifest is not "
            f"a JSON object: {manifest_blob_path}"
        )

    manifest_job_id = str(
        payload.get("job_id") or ""
    ).strip()

    manifest_set_id = str(
        payload.get("set_id") or ""
    ).strip()

    if (
        manifest_job_id
        and manifest_job_id != clean_job_id
    ):
        raise RuntimeError(
            "Processing Set manifest job mismatch: "
            f"requested {clean_job_id}, "
            f"manifest contains {manifest_job_id}."
        )

    if (
        manifest_set_id
        and manifest_set_id != clean_set_id
    ):
        raise RuntimeError(
            "Processing Set manifest set mismatch: "
            f"requested {clean_set_id}, "
            f"manifest contains {manifest_set_id}."
        )

    try:
        set_number = int(
            payload.get("set_number") or 0
        )
    except Exception:
        set_number = 0

    raw_members = (
        payload.get("members")
        or []
    )

    if not isinstance(raw_members, list):
        raise RuntimeError(
            "Processing Set manifest members "
            "must be a JSON array."
        )

    documents: list[
        AiExtractionSourceDocument
    ] = []

    for member in raw_members:
        if not isinstance(member, dict):
            continue

        membership_role = str(
            member.get("membership_role")
            or ""
        ).strip().lower()

        if membership_role != "primary":
            continue

        if bool(
            member.get("is_container")
            or False
        ):
            continue

        if bool(
            member.get("is_denisted")
            or False
        ):
            continue

        if bool(
            member.get("is_duplicate")
            or False
        ):
            continue

        doc_id = str(
            member.get("doc_id")
            or ""
        ).strip()

        if not doc_id:
            continue

        if (
            clean_selected_doc_ids
            and doc_id
            not in clean_selected_doc_ids
        ):
            continue

        file_id = str(
            member.get("file_id")
            or ""
        ).strip()

        try:
            ordinal = int(
                member.get("ordinal")
                or 0
            )
        except Exception:
            ordinal = 0

        normalized_path = str(
            member.get("normalized_path")
            or ""
        ).strip()

        original_path = str(
            member.get("original_path")
            or ""
        ).strip()

        source_filename = (
            normalized_path
            or original_path
        )

        document = AiExtractionSourceDocument(
            processing_set_id=clean_set_id,
            processing_set_number=set_number,
            processing_set_ordinal=ordinal,
            source_job_id=clean_job_id,
            source_file_id=file_id,
            source_doc_id=doc_id,
            source_filename=source_filename,
            text_path=str(
                member.get(
                    "text_output_path"
                )
                or ""
            ).strip(),
        )

        documents.append(
            document
        )

    documents.sort(
        key=lambda document: (
            document.processing_set_ordinal,
            document.source_filename,
            document.source_file_id,
        )
    )

    return documents