from __future__ import annotations


from pathlib import Path
from typing import Any

from ..detection.engine import run_detection_engine
from ..detection.models import DetectionCandidate

from ..util import json_dumps, new_id, utc_now


DETECTOR_NAME = "insyt_detection_engine"
DETECTOR_VERSION = "v1"


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


def _insert_detection_candidate(
    db,
    *,
    detection_run_id: str,
    detection_document_id: str,
    matter_id: str,
    file_id: str,
    doc_id: str,
    candidate: DetectionCandidate,
    source_text_type: str,
):
    entity_text = str(
        candidate.detected_value
        or ""
    )

    normalized_value = str(
        candidate.normalized_value
        or entity_text.strip()
    )

    masked_value = str(
        candidate.masked_value
        or _mask_value(entity_text)
    )

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
            candidate.entity_type or "Unknown",
            candidate.entity_subtype or None,
            entity_text,
            normalized_value,
            masked_value,
            float(
                candidate.confidence
                or 0.0
            ),
            int(
                candidate.start_offset
            ),
            int(
                candidate.end_offset
            ),
            candidate.page_number,
            candidate.detector_name
            or DETECTOR_NAME,
            candidate.detector_version
            or DETECTOR_VERSION,
            candidate.detection_rule
            or "",
            candidate.protocol_name
            or None,
            candidate.protocol_version
            or None,
            candidate.reportability
            or "UNCLASSIFIED",
            source_text_type,
            json_dumps(
                {
                    "methods": list(
                        candidate.methods
                    ),
                    "context_terms": list(
                        candidate.context_terms
                    ),
                    "validation_status": (
                        candidate.validation_status
                    ),
                    "validation_method": (
                        candidate.validation_method
                    ),
                    **dict(
                        candidate.metadata
                        or {}
                    ),
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
    Scan ingestion-complete documents with the unified INSYT
    Data Element Detection engine.

    Current detector stack:
    - Azure AI Language PII / PHI NER
    - INSYT structured regex/context/validator rules
    - merge/deduplication

    This stage is intentionally separate from Initial Ingestion. It is called
    by the Data Element Detection workflow after Doc ID assignment, native
    text extraction, and any required OCR have completed.
    """

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
                    "engine": "INSYT Data Element Detection",
                    "azure_ner_enabled": True,
                    "structured_rules_enabled": True,
                    "merge_enabled": True,
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
    
    azure_candidate_count = 0
    structured_candidate_count = 0
    merged_candidate_count = 0

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

            engine_result = run_detection_engine(
                text,
                include_phi=include_phi,
                protocol_name=protocol_name,
                protocol_version=protocol_version,
                enable_azure=True,
                enable_structured_rules=True,
            )

            candidates = (
                engine_result.get("candidates")
                or []
            )

            azure_candidate_count += int(
                engine_result.get(
                    "azure_candidate_count",
                    0,
                )
                or 0
            )

            structured_candidate_count += int(
                engine_result.get(
                    "structured_candidate_count",
                    0,
                )
                or 0
            )

            merged_candidate_count += int(
                engine_result.get(
                    "merged_candidate_count",
                    len(candidates),
                )
                or 0
            )

            confidences: list[float] = []

            for candidate in candidates:
                confidence = float(
                    candidate.confidence
                    or 0.0
                )

                confidences.append(
                    confidence
                )

                _insert_detection_candidate(
                    db,
                    detection_run_id=detection_run_id,
                    detection_document_id=detection_document_id,
                    matter_id=matter_id,
                    file_id=file_id,
                    doc_id=doc_id,
                    candidate=candidate,
                    source_text_type=text_source,
                )

            hit_count = len(candidates)

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
                            "azure_ner_enabled": True,
                            "structured_rules_enabled": True,
                            "merge_enabled": True,
                            "azure_candidate_count": (
                                engine_result.get(
                                    "azure_candidate_count",
                                    0,
                                )
                            ),
                            "structured_candidate_count": (
                                engine_result.get(
                                    "structured_candidate_count",
                                    0,
                                )
                            ),
                            "merged_candidate_count": (
                                engine_result.get(
                                    "merged_candidate_count",
                                    hit_count,
                                )
                            ),
                            "detectors": (
                                engine_result.get(
                                    "detectors",
                                    [],
                                )
                            ),
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
                    "azure_ner_enabled": True,
                    "structured_rules_enabled": True,
                    "merge_enabled": True,
                    "service_logs_disabled": True,
                    "azure_candidate_count": (
                        azure_candidate_count
                    ),
                    "structured_candidate_count": (
                        structured_candidate_count
                    ),
                    "merged_candidate_count": (
                        merged_candidate_count
                    ),
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
        "azure_candidate_count": azure_candidate_count,
        "structured_candidate_count": structured_candidate_count,
        "merged_candidate_count": merged_candidate_count,
    }