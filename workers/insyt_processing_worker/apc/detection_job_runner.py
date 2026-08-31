from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from .db import LedgerDB
from .stages.pii_phi_detection import run_pii_phi_detection
from .util import json_dumps, new_id, utc_now


def _processing_account() -> str:
    return os.getenv(
        "INSYT_PROCESSING_STORAGE_ACCOUNT",
        "insytprodstorage",
    )


def _processing_container() -> str:
    return os.getenv(
        "INSYT_PROCESSING_CONTAINER",
        "insyt-processing",
    )


def _review_account() -> str:
    return os.getenv(
        "INSYT_REVIEW_STORAGE_ACCOUNT",
        "insytreviewstorage",
    )


def _review_container(workspace: str) -> str:
    workspace_key = str(
        workspace or "capture"
    ).strip().lower()

    return (
        os.getenv(
            f"INSYT_REVIEW_CONTAINER_{workspace_key.upper()}"
        )
        or os.getenv("INSYT_REVIEW_CONTAINER")
        or f"insyt-{workspace_key}"
    )


def _processing_blob_service() -> BlobServiceClient:
    connection_string = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(
            connection_string
        )

    return BlobServiceClient(
        account_url=(
            f"https://{_processing_account()}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _review_blob_service() -> BlobServiceClient:
    connection_string = os.getenv(
        "INSYT_REVIEW_STORAGE_CONNECTION_STRING"
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(
            connection_string
        )

    return BlobServiceClient(
        account_url=(
            f"https://{_review_account()}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _write_processing_json(
    blob_path: str,
    payload: Any,
) -> dict[str, Any]:
    container = (
        _processing_blob_service()
        .get_container_client(_processing_container())
    )

    blob_client = container.get_blob_client(blob_path)

    data = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(
            content_type="application/json; charset=utf-8"
        ),
    )

    return {
        "storage_account": _processing_account(),
        "container": _processing_container(),
        "blob_path": blob_path,
        "bytes": len(data),
    }


def _download_detection_text(
    *,
    workspace: str,
    blob_path: str,
    destination: Path,
) -> None:
    container = (
        _review_blob_service()
        .get_container_client(
            _review_container(workspace)
        )
    )

    blob_client = container.get_blob_client(blob_path)

    data = blob_client.download_blob().readall()

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_bytes(data)


def _seed_source_job(
    db: LedgerDB,
    *,
    source_job_id: str,
    matter_id: str,
    client_id: str,
    workspace: str,
) -> None:
    existing = db.query_one(
        """
        SELECT job_id
        FROM processing_job
        WHERE job_id=?
        """,
        (source_job_id,),
    )

    if existing:
        return

    db.execute(
        """
        INSERT INTO processing_job (
            job_id,
            matter_id,
            client_id,
            created_at,
            status,
            metadata_json
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            source_job_id,
            matter_id,
            client_id,
            utc_now(),
            "detection_source",
            json_dumps(
                {
                    "workspace": workspace,
                    "purpose": (
                        "data_element_detection_source"
                    ),
                }
            ),
        ),
    )


def _seed_detection_document(
    db: LedgerDB,
    *,
    source_job_id: str,
    matter_id: str,
    doc: dict[str, Any],
    local_text_path: Path,
) -> str:
    doc_id = str(
        doc.get("doc_id") or ""
    ).strip()

    file_id = (
        str(doc.get("file_id") or "").strip()
        or new_id("DETFILE")
    )

    native_blob_path = str(
        doc.get("native_staged_blob_path") or ""
    )

    original_name = (
        native_blob_path.rsplit("/", 1)[-1]
        if native_blob_path
        else f"{doc_id}.bin"
    )

    extension = ""

    if "." in original_name:
        extension = (
            original_name.rsplit(".", 1)[-1]
            .strip()
            .lower()
        )

    existing = db.query_one(
        """
        SELECT file_id
        FROM file_processing_metrics
        WHERE job_id=? AND doc_id=?
        """,
        (
            source_job_id,
            doc_id,
        ),
    )

    if existing:
        return str(existing["file_id"])

    db.execute(
        """
        INSERT INTO file_processing_metrics (
            file_id,
            matter_id,
            job_id,
            original_path,
            normalized_path,
            extension,
            source_bytes,
            expanded_bytes,
            is_container,
            is_extracted,
            page_count,
            text_bytes,
            has_native_text,
            requires_ocr,
            is_duplicate,
            is_denisted,
            doc_id,
            text_output_path,
            stage_status_json,
            exception_json,
            created_at,
            updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            file_id,
            matter_id,
            source_job_id,
            native_blob_path or original_name,
            original_name,
            extension,
            int(doc.get("source_bytes") or 0),
            int(doc.get("source_bytes") or 0),
            0,
            0,
            int(doc.get("page_count") or 0),
            int(local_text_path.stat().st_size),
            1,
            0,
            0,
            0,
            doc_id,
            str(local_text_path),
            json_dumps(
                {
                    "detection_staging": {
                        "status": "ready",
                        "source_text_blob_path": (
                            doc.get(
                                "text_staged_blob_path"
                            )
                        ),
                    }
                }
            ),
            "[]",
            utc_now(),
            utc_now(),
        ),
    )

    return file_id


def run_data_element_detection_job(
    *,
    db: LedgerDB,
    payload: dict[str, Any],
) -> dict[str, Any]:
    detection_job_id = str(
        payload.get("detection_job_id")
        or payload.get("job_id")
        or ""
    ).strip()

    if not detection_job_id:
        raise RuntimeError(
            "Detection queue payload is missing "
            "detection_job_id."
        )

    workspace = str(
        payload.get("workspace") or "capture"
    ).strip().lower()

    client_id = str(
        payload.get("client") or ""
    ).strip()

    project = str(
        payload.get("project") or ""
    ).strip()

    source_job_id = str(
        payload.get("source_job_id") or ""
    ).strip()

    if not client_id:
        raise RuntimeError(
            "Detection queue payload is missing client."
        )

    if not project:
        raise RuntimeError(
            "Detection queue payload is missing project."
        )

    if not source_job_id:
        raise RuntimeError(
            "Detection queue payload is missing "
            "source_job_id."
        )

    matter_id = str(
        payload.get("matter_id")
        or project
        or source_job_id
    ).strip()

    documents = payload.get("documents") or []

    if not isinstance(documents, list):
        raise RuntimeError(
            "Detection queue payload documents "
            "must be a list."
        )

    if not documents:
        raise RuntimeError(
            "Detection queue payload contains no documents."
        )

    db.init_schema()

    _seed_source_job(
        db,
        source_job_id=source_job_id,
        matter_id=matter_id,
        client_id=client_id,
        workspace=workspace,
    )

    local_root = (
        Path(
            os.getenv(
                "APC_DETECTION_ROOT",
                "/tmp/apc_detection_runs",
            )
        )
        / detection_job_id
    )

    text_dir = local_root / "text"

    downloaded_docs: list[dict[str, Any]] = []

    for doc in documents:
        if not isinstance(doc, dict):
            continue

        doc_id = str(
            doc.get("doc_id") or ""
        ).strip()

        text_blob_path = str(
            doc.get("text_staged_blob_path") or ""
        ).strip()

        if not doc_id or not text_blob_path:
            continue

        local_text_path = (
            text_dir / f"{doc_id}.txt"
        )

        _download_detection_text(
            workspace=workspace,
            blob_path=text_blob_path,
            destination=local_text_path,
        )

        file_id = _seed_detection_document(
            db,
            source_job_id=source_job_id,
            matter_id=matter_id,
            doc=doc,
            local_text_path=local_text_path,
        )

        downloaded_docs.append(
            {
                **doc,
                "file_id": file_id,
                "local_text_path": str(
                    local_text_path
                ),
            }
        )

    if not downloaded_docs:
        raise RuntimeError(
            "No staged detection text files could "
            "be prepared."
        )

    result = run_pii_phi_detection(
        db,
        source_job_id=source_job_id,
        matter_id=matter_id,
        client_id=client_id,
        workspace=workspace,
        protocol_name=payload.get(
            "protocol_name"
        ),
        protocol_version=payload.get(
            "protocol_version"
        ),
        include_phi=bool(
            payload.get("include_phi", True)
        ),
    )

    detection_run_id = str(
        result.get("detection_run_id") or ""
    )

    document_rows = [
        dict(row)
        for row in db.query(
            """
            SELECT *
            FROM processing_detection_document
            WHERE detection_run_id=?
            ORDER BY doc_id
            """,
            (detection_run_id,),
        )
    ]

    entity_rows = [
        dict(row)
        for row in db.query(
            """
            SELECT *
            FROM processing_detection_entity
            WHERE detection_run_id=?
            ORDER BY doc_id, start_offset
            """,
            (detection_run_id,),
        )
    ]

    entity_counts_rows = db.query(
        """
        SELECT
            entity_type,
            count(*) AS hit_count,
            count(DISTINCT doc_id) AS document_count
        FROM processing_detection_entity
        WHERE detection_run_id=?
        GROUP BY entity_type
        ORDER BY document_count DESC,
                 hit_count DESC,
                 entity_type
        """,
        (detection_run_id,),
    )

    entity_counts = [
        {
            "entity_type": row["entity_type"],
            "hit_count": int(
                row["hit_count"] or 0
            ),
            "document_count": int(
                row["document_count"] or 0
            ),
        }
        for row in entity_counts_rows
    ]

    project_base = (
        f"{client_id}/{workspace}/"
        f"{project.replace(' ', '_')}"
    )

    result_prefix = (
        f"{project_base}/processing_center/"
        f"detection/jobs/{detection_job_id}/results"
    )

    summary_payload = {
        **result,
        "job_type": "data_element_detection",
        "detection_job_id": detection_job_id,
        "workspace": workspace,
        "client": client_id,
        "project": project,
        "source_job_id": source_job_id,
        "protocol_name": payload.get(
            "protocol_name"
        ),
        "protocol_version": payload.get(
            "protocol_version"
        ),
        "include_phi": bool(
            payload.get("include_phi", True)
        ),
        "entity_type_counts": entity_counts,
        "completed_at": utc_now(),
    }

    summary_upload = _write_processing_json(
        f"{result_prefix}/summary.json",
        summary_payload,
    )

    documents_upload = _write_processing_json(
        f"{result_prefix}/documents.json",
        document_rows,
    )

    entities_upload = _write_processing_json(
        f"{result_prefix}/entities.json",
        entity_rows,
    )
    
    document_index_prefix = (
        f"{project_base}/processing_center/"
        f"detection/documents"
    )

    document_index_uploads: list[dict[str, Any]] = []

    entities_by_doc_id: dict[str, list[dict[str, Any]]] = {}

    for entity in entity_rows:
        entity_doc_id = str(
            entity.get("doc_id") or ""
        ).strip()

        if not entity_doc_id:
            continue

        entities_by_doc_id.setdefault(
            entity_doc_id,
            [],
        ).append(entity)

    for document_row in document_rows:
        doc_id = str(
            document_row.get("doc_id") or ""
        ).strip()

        if not doc_id:
            continue

        document_entities = entities_by_doc_id.get(
            doc_id,
            [],
        )

        entity_type_counts: dict[str, int] = {}

        normalized_hits: list[dict[str, Any]] = []

        for entity in document_entities:
            entity_type = str(
                entity.get("entity_type")
                or entity.get("category")
                or ""
            ).strip()

            if entity_type:
                entity_type_counts[entity_type] = (
                    entity_type_counts.get(entity_type, 0) + 1
                )

            start_offset = entity.get("start_offset")

            if start_offset is None:
                start_offset = entity.get("offset")

            end_offset = entity.get("end_offset")
            length = entity.get("length")

            try:
                normalized_start = int(start_offset)
            except (TypeError, ValueError):
                continue

            if end_offset is not None:
                try:
                    normalized_end = int(end_offset)
                except (TypeError, ValueError):
                    continue

            elif length is not None:
                try:
                    normalized_end = (
                        normalized_start + int(length)
                    )
                except (TypeError, ValueError):
                    continue

            else:
                detected_value = str(
                    entity.get("detected_value")
                    or entity.get("text")
                    or ""
                )

                if not detected_value:
                    continue

                normalized_end = (
                    normalized_start + len(detected_value)
                )

            if normalized_start < 0:
                continue

            if normalized_end <= normalized_start:
                continue

            confidence_raw = (
                entity.get("confidence")
                if entity.get("confidence") is not None
                else entity.get("confidence_score")
            )

            try:
                confidence = (
                    float(confidence_raw)
                    if confidence_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                confidence = None

            normalized_hits.append(
                {
                    "entity_type": entity_type,
                    "entity_subtype": str(
                        entity.get("entity_subtype")
                        or entity.get("subcategory")
                        or ""
                    ).strip(),
                    "detected_value": str(
                        entity.get("detected_value")
                        or entity.get("text")
                        or ""
                    ),
                    "normalized_value": entity.get(
                        "normalized_value"
                    ),
                    "masked_value": entity.get(
                        "masked_value"
                    ),
                    "confidence": confidence,
                    "start_offset": normalized_start,
                    "end_offset": normalized_end,
                    "page_number": (
                        entity.get("page_number")
                        or entity.get("page")
                    ),
                    "detector": (
                        entity.get("detector")
                        or entity.get("detector_name")
                        or "azure_language"
                    ),
                    "detector_version": entity.get(
                        "detector_version"
                    ),
                    "rule_id": entity.get("rule_id"),
                    "protocol": (
                        entity.get("protocol")
                        or entity.get("protocol_name")
                        or payload.get("protocol_name")
                        or ""
                    ),
                    "protocol_version": (
                        entity.get("protocol_version")
                        or payload.get("protocol_version")
                        or ""
                    ),
                    "reportability": (
                        entity.get("reportability")
                        or "UNCLASSIFIED"
                    ),
                }
            )

        normalized_hits.sort(
            key=lambda hit: (
                int(hit.get("start_offset") or 0),
                int(hit.get("end_offset") or 0),
            )
        )

        document_index_payload = {
            "schema_version": 1,
            "workspace": workspace,
            "client": client_id,
            "project": project,
            "doc_id": doc_id,
            "classification": (
                document_row.get("classification")
                or "PENDING"
            ),
            "detection_status": (
                document_row.get("status")
                or document_row.get("detection_status")
                or ""
            ),
            "hit_count": len(normalized_hits),
            "entity_type_counts": entity_type_counts,
            "source_job_id": source_job_id,
            "latest_detection_job_id": detection_job_id,
            "detection_run_id": detection_run_id,
            "protocol_name": payload.get(
                "protocol_name"
            ),
            "protocol_version": payload.get(
                "protocol_version"
            ),
            "include_phi": bool(
                payload.get("include_phi", True)
            ),
            "text_source": (
                document_row.get("text_source")
                or document_row.get("source_text_type")
                or ""
            ),
            "text_path": (
                document_row.get("text_path")
                or document_row.get("text_output_path")
                or ""
            ),
            "detected_at": (
                document_row.get("completed_at")
                or document_row.get("updated_at")
                or summary_payload.get("completed_at")
            ),
            "hits": normalized_hits,
        }

        document_index_uploads.append(
            _write_processing_json(
                f"{document_index_prefix}/{doc_id}.json",
                document_index_payload,
            )
        )

    return {
        **summary_payload,
        "message": (
            "Data Element Detection completed."
        ),
        "result_prefix": result_prefix,
        "summary_blob_path": (
            summary_upload["blob_path"]
        ),
        "documents_blob_path": (
            documents_upload["blob_path"]
        ),
        "entities_blob_path": (
            entities_upload["blob_path"]
        ),
        "document_index_prefix": document_index_prefix,
        "document_index_count": len(document_index_uploads),
        "document_index_uploads": document_index_uploads,
        "documents": document_rows,
        "entity_type_counts": entity_counts,
    }