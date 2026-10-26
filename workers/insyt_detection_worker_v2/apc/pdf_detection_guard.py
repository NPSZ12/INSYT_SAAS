from __future__ import annotations

import json
from typing import Any


def validate_pdf_documents(
    documents: list[dict[str, Any]],
    report: dict[str, Any] | None,
    *,
    workspace: str,
    client: str,
    project: str,
    source_job_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Validate PDFs from a trusted source report, not queue claims."""

    if not isinstance(report, dict):
        raise ValueError(
            "Authoritative source report required for Detection guard"
        )

    by_doc_id: dict[str, list[dict[str, Any]]] = {}

    if isinstance(report, dict):
        records = report.get("files") or []
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                doc_id = str(record.get("doc_id") or "").strip()
                if doc_id:
                    by_doc_id.setdefault(doc_id, []).append(record)

    accepted = []
    rejected = []

    for doc in documents:
        if not isinstance(doc, dict):
            accepted.append(doc)
            continue

        # PDF_REPORT_CLASSIFICATION_V1
        # Source report, never queue extension, determines type.
        doc_id = str(doc.get("doc_id") or "").strip()
        matches = by_doc_id.get(doc_id) or []

        if len(matches) != 1:
            rejected.append({
                "doc_id": doc_id,
                "reason_code": "SOURCE_RECORD_MISSING_OR_AMBIGUOUS",
            })
            continue

        trusted_ext = str(
            matches[0].get("extension") or ""
        ).strip().lower().lstrip(".")

        if trusted_ext != "pdf":
            accepted.append(doc)
            continue

        reason = ""

        if len(matches) != 1:
            reason = "PDF_SOURCE_RECORD_MISSING_OR_AMBIGUOUS"
        else:
            record = matches[0]

            original_ext = str(
                record.get("extension") or ""
            ).strip().lower().lstrip(".")

            source_file_id = str(
                record.get("file_id") or ""
            ).strip()
            queued_file_id = str(
                doc.get("file_id") or ""
            ).strip()

            if original_ext != "pdf":
                reason = "PDF_SOURCE_EXTENSION_MISMATCH"

            elif (
                not source_file_id
                or not queued_file_id
                or source_file_id != queued_file_id
            ):
                reason = "PDF_SOURCE_FILE_ID_MISMATCH"

            else:
                raw = record.get("stage_status_json") or {}

                try:
                    stages = (
                        json.loads(raw)
                        if isinstance(raw, str)
                        else raw
                    )
                except (TypeError, ValueError):
                    stages = {}

                if not isinstance(stages, dict):
                    stages = {}

                inspection = stages.get(
                    "pdf_adapter_inspection"
                )

                if not isinstance(inspection, dict):
                    reason = "PDF_INSPECTION_MISSING"
                else:
                    metadata = inspection.get("metadata") or {}

                    if not isinstance(metadata, dict):
                        metadata = {}

                    if not (
                        inspection.get("status") == "completed"
                        and not inspection.get("error")
                        and not inspection.get(
                            "remediation_required"
                        )
                        and metadata.get(
                            "structural_status"
                        ) == "validated"
                        and not metadata.get(
                            "remediation_reason"
                        )
                    ):
                        reason = "PDF_INSPECTION_REMEDIATION_REQUIRED"

        if not reason:
            clean_client = str(client).strip().strip("/")
            clean_project = (
                str(project).strip().strip("/").replace(" ", "_")
            )
            clean_workspace = str(workspace).strip().lower()
            clean_job = str(source_job_id).strip()

            expected_path = (
                f"{clean_client}/{clean_workspace}/{clean_project}"
                f"/processing_center/staged/{clean_job}"
                f"/text/{doc_id}.txt"
            )

            submitted_path = str(
                doc.get("text_staged_blob_path") or ""
            ).strip()

            if submitted_path != expected_path:
                reason = "PDF_STAGED_TEXT_PATH_MISMATCH"

        if reason:
            rejected.append({
                "doc_id": doc_id,
                "reason_code": reason,
            })
        else:
            accepted.append(doc)

    return accepted, rejected
