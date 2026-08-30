from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from ..util import json_dumps, new_id, utc_now


DETECTOR_NAME = "azure_language_pii"
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


def _row_get(row: Any, *names: str):
    for name in names:
        try:
            value = row[name]
        except Exception:
            value = getattr(row, name, None)

        if value not in (None, ""):
            return value

    return None


def _get_stage_status(row: Any) -> dict:
    raw = _row_get(row, "stage_status_json")

    if not raw:
        return {}

    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _find_text_path(row: Any) -> str | None:
    explicit = _row_get(
        row,
        "text_output_path",
        "ocr_text_path",
        "extracted_text_path",
        "text_path",
        "review_text_path",
        "output_text_path",
    )

    if explicit:
        path = Path(str(explicit))

        if path.exists() and path.is_file():
            return str(path)

    stage_status = _get_stage_status(row)

    ocr_live = stage_status.get("ocr_live") or {}

    if isinstance(ocr_live, dict):
        ocr_text_path = ocr_live.get("text_path")

        if ocr_text_path:
            path = Path(str(ocr_text_path))

            if path.exists() and path.is_file():
                return str(path)

    original_path = _row_get(
        row,
        "original_path",
        "source_path",
        "file_path",
        "path",
    )

    doc_id = _row_get(
        row,
        "doc_id",
        "assigned_doc_id",
        "document_id",
    )

    if original_path and doc_id:
        source = Path(str(original_path))

        derived = (
            source.parent.parent
            / "text"
            / f"{doc_id}.txt"
        )

        if derived.exists() and derived.is_file():
            return str(derived)

    return None


def _mask_value(value: str) -> str:
    text = str(value or "")

    if len(text) <= 2:
        return "*" * len(text)

    if len(text) <= 6:
        return text[0] + ("*" * (len(text) - 2)) + text[-1]

    return text[:2] + ("*" * (len(text) - 4)) + text[-2:]


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
            chunks.append((start, chunk))

        start = end

    return chunks


def _detect_chunk(
    client: TextAnalyticsClient,
    text: str,
    *,
    domain_filter: str | None = None,
) -> list[dict]:
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
        error = getattr(document, "error", None)

        raise RuntimeError(
            f"Azure Language PII detection failed: {error}"
        )

    entities: list[dict] = []

    for entity in getattr(document, "entities", []) or []:
        entities.append(
            {
                "text": str(
                    getattr(entity, "text", "")
                    or ""
                ),
                "category": str(
                    getattr(entity, "category", "")
                    or ""
                ),
                "subcategory": (
                    str(getattr(entity, "subcategory", "") or "")
                    or None
                ),
                "confidence": float(
                    getattr(entity, "confidence_score", 0.0)
                    or 0.0
                ),
                "offset": int(
                    getattr(entity, "offset", 0)
                    or 0
                ),
                "length": int(
                    getattr(entity, "length", 0)
                    or 0
                ),
            }
        )

    return entities


def _insert_detection_entity(
    db,
    *,
    detection_run_id: str,
    detection_document_id: str,
    matter_id: str,
    file_id: str,
    doc_id: str,
    entity: dict,
    chunk_start_offset: int,
    protocol_name: str | None,
    protocol_version: str | None,
    source_text_type: str,
):
    entity_text = str(entity.get("text") or "")

    local_offset = int(entity.get("offset") or 0)
    entity_length = int(entity.get("length") or len(entity_text))

    start_offset = chunk_start_offset + local_offset
    end_offset = start_offset + entity_length

    db.execute(
        """
        INSERT INTO processing_detection_entity (
            detection_entity_id,
            detection_run_id,
            detection_document_id,
            matter_id,
            file_id,
            doc_id,
            entity_type,
            entity_subtype,
            detected_value,
            normalized_value,
            masked_value,
            confidence,
            start_offset,
            end_offset,
            page_number,
            detector_name,
            detector_version,
            detection_rule,
            protocol_name,
            protocol_version,
            reportability,
            source_text_type,
            metadata_json,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            new_id("DETENT"),
            detection_run_id,
            detection_document_id,
            matter_id,
            file_id,
            doc_id,
            str(entity.get("category") or "Unknown"),
            entity.get("subcategory"),
            entity_text,
            entity_text.strip(),
            _mask_value(entity_text),
            float(entity.get("confidence") or 0.0),
            start_offset,
            end_offset,
            None,
            DETECTOR_NAME,
            DETECTOR_VERSION,
            "azure_language_pii",
            protocol_name,
            protocol_version,
            "UNCLASSIFIED",
            source_text_type,
            json_dumps(
                {
                    "azure_offset": local_offset,
                    "azure_length": entity_length,
                    "chunk_start_offset": chunk_start_offset,
                }
            ),
            utc_now(),
        ),
    )


def run_pii_phi_detection(
    db,
    *,
    source_job_id: str,
    matter_id: str,
    client_id: str,
    workspace: str = "capture",
    protocol_name: str | None = None,
    protocol_version: str | None = None,
    include_phi: bool = True,
) -> dict:
    """
    Scan ingestion-complete documents for Azure Language PII / PHI entities.

    This stage is intentionally separate from Initial Ingestion. It is called
    by the Data Element Detection workflow after Doc ID assignment, native
    text extraction, and any required OCR have completed.
    """

    client = _get_language_client()

    detection_run_id = new_id("DETRUN")
    now = utc_now()

    db.execute(
        """
        INSERT INTO processing_detection_run (
            detection_run_id,
            matter_id,
            client_id,
            workspace,
            source_job_id,
            protocol_name,
            protocol_version,
            detector_name,
            detector_version,
            created_at,
            started_at,
            status,
            metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            detection_run_id,
            matter_id,
            client_id,
            workspace,
            source_job_id,
            protocol_name,
            protocol_version,
            DETECTOR_NAME,
            DETECTOR_VERSION,
            now,
            now,
            "running",
            json_dumps(
                {
                    "include_phi": include_phi,
                    "service": "Azure AI Language",
                    "operation": "recognize_pii_entities",
                    "service_logs_disabled": True,
                }
            ),
        ),
    )

    rows = db.query(
        """
        SELECT *
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND doc_id IS NOT NULL
        ORDER BY doc_id
        """,
        (source_job_id,),
    )

    documents_total = len(rows)
    documents_scanned = 0
    documents_with_hits = 0
    documents_no_hits = 0
    documents_exception = 0
    entity_hit_count = 0

    for row in rows:
        file_id = str(_row_get(row, "file_id") or "")
        doc_id = str(_row_get(row, "doc_id") or "")

        detection_document_id = new_id("DETDOC")

        text_path = _find_text_path(row)

        text_source = "unknown"

        stage_status = _get_stage_status(row)

        ocr_live = stage_status.get("ocr_live") or {}

        if isinstance(ocr_live, dict) and ocr_live.get("status") == "completed":
            text_source = "azure_document_intelligence_read"
        elif int(_row_get(row, "has_native_text") or 0):
            text_source = "native_text"

        db.execute(
            """
            INSERT INTO processing_detection_document (
                detection_document_id,
                detection_run_id,
                matter_id,
                source_job_id,
                file_id,
                doc_id,
                text_source,
                text_path,
                detection_status,
                classification,
                hit_count,
                protocol_name,
                protocol_version,
                exception_json,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                detection_document_id,
                detection_run_id,
                matter_id,
                source_job_id,
                file_id,
                doc_id,
                text_source,
                text_path,
                "running",
                "PENDING",
                0,
                protocol_name,
                protocol_version,
                "[]",
                "{}",
                utc_now(),
                utc_now(),
            ),
        )

        try:
            if not text_path:
                raise RuntimeError(
                    "No extracted/OCR text path available for detection."
                )

            path = Path(text_path)

            if not path.exists() or not path.is_file():
                raise RuntimeError(
                    f"Detection text file does not exist: {text_path}"
                )

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if not text.strip():
                raise RuntimeError(
                    "Detection text file is empty."
                )

            all_entities: list[dict] = []

            for chunk_start, chunk in _chunk_text(text):
                pii_entities = _detect_chunk(
                    client,
                    chunk,
                    domain_filter=None,
                )

                for entity in pii_entities:
                    entity["_chunk_start"] = chunk_start
                    all_entities.append(entity)

                if include_phi:
                    phi_entities = _detect_chunk(
                        client,
                        chunk,
                        domain_filter="phi",
                    )

                    for entity in phi_entities:
                        entity["_chunk_start"] = chunk_start
                        entity["_phi_domain"] = True
                        all_entities.append(entity)

            # Avoid exact duplicate hits when an entity is returned by both
            # the general PII request and PHI-domain request.
            unique_entities: list[dict] = []
            seen: set[tuple] = set()

            for entity in all_entities:
                key = (
                    str(entity.get("category") or ""),
                    str(entity.get("subcategory") or ""),
                    str(entity.get("text") or ""),
                    int(entity.get("_chunk_start") or 0)
                    + int(entity.get("offset") or 0),
                )

                if key in seen:
                    continue

                seen.add(key)
                unique_entities.append(entity)

            confidences: list[float] = []

            for entity in unique_entities:
                confidence = float(
                    entity.get("confidence") or 0.0
                )

                confidences.append(confidence)

                _insert_detection_entity(
                    db,
                    detection_run_id=detection_run_id,
                    detection_document_id=detection_document_id,
                    matter_id=matter_id,
                    file_id=file_id,
                    doc_id=doc_id,
                    entity=entity,
                    chunk_start_offset=int(
                        entity.get("_chunk_start") or 0
                    ),
                    protocol_name=protocol_name,
                    protocol_version=protocol_version,
                    source_text_type=text_source,
                )

            hit_count = len(unique_entities)

            highest_confidence = (
                max(confidences)
                if confidences
                else None
            )

            average_confidence = (
                sum(confidences) / len(confidences)
                if confidences
                else None
            )

            classification = (
                "HIT"
                if hit_count > 0
                else "NO_HIT"
            )

            db.execute(
                """
                UPDATE processing_detection_document
                SET detection_status=?,
                    classification=?,
                    hit_count=?,
                    highest_confidence=?,
                    average_confidence=?,
                    metadata_json=?,
                    updated_at=?
                WHERE detection_document_id=?
                """,
                (
                    "completed",
                    classification,
                    hit_count,
                    highest_confidence,
                    average_confidence,
                    json_dumps(
                        {
                            "general_pii_enabled": True,
                            "phi_enabled": include_phi,
                        }
                    ),
                    utc_now(),
                    detection_document_id,
                ),
            )

            documents_scanned += 1
            entity_hit_count += hit_count

            if classification == "HIT":
                documents_with_hits += 1
            else:
                documents_no_hits += 1

        except Exception as exc:
            documents_exception += 1

            db.execute(
                """
                UPDATE processing_detection_document
                SET detection_status=?,
                    classification=?,
                    exception_json=?,
                    updated_at=?
                WHERE detection_document_id=?
                """,
                (
                    "failed",
                    "EXCEPTION",
                    json_dumps(
                        [
                            {
                                "error": (
                                    f"{type(exc).__name__}: {exc}"
                                )
                            }
                        ]
                    ),
                    utc_now(),
                    detection_document_id,
                ),
            )

    db.execute(
        """
        UPDATE processing_detection_run
        SET completed_at=?,
            status=?,
            documents_total=?,
            documents_scanned=?,
            documents_with_hits=?,
            documents_no_hits=?,
            documents_nfr=?,
            documents_exception=?,
            entity_hit_count=?,
            metadata_json=?
        WHERE detection_run_id=?
        """,
        (
            utc_now(),
            (
                "completed"
                if documents_exception == 0
                else "completed_with_exceptions"
            ),
            documents_total,
            documents_scanned,
            documents_with_hits,
            documents_no_hits,
            0,
            documents_exception,
            entity_hit_count,
            json_dumps(
                {
                    "general_pii_enabled": True,
                    "phi_enabled": include_phi,
                    "service_logs_disabled": True,
                }
            ),
            detection_run_id,
        ),
    )

    return {
        "detection_run_id": detection_run_id,
        "status": (
            "completed"
            if documents_exception == 0
            else "completed_with_exceptions"
        ),
        "documents_total": documents_total,
        "documents_scanned": documents_scanned,
        "documents_with_hits": documents_with_hits,
        "documents_no_hits": documents_no_hits,
        "documents_nfr": 0,
        "documents_exception": documents_exception,
        "entity_hit_count": entity_hit_count,
    }