from __future__ import annotations

import json
import mimetypes
import os
import tempfile

import random
import time

from azure.core.exceptions import HttpResponseError

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
)

from apc.stages.ocr_live_placeholder import (
    _ocr_bytes,
    _prepare_image_for_ocr,
)

from apc.util import utc_now


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


def _review_container(
    workspace: str,
) -> str:
    workspace_key = str(
        workspace or "capture"
    ).strip().lower()

    return (
        os.getenv(
            f"INSYT_REVIEW_CONTAINER_{workspace_key.upper()}"
        )
        or f"insyt-{workspace_key}"
    )


def _review_blob_service() -> BlobServiceClient:
    return BlobServiceClient(
        account_url=(
            f"https://{_review_account()}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _write_review_text_blob(
    *,
    workspace: str,
    blob_path: str,
    text: str,
) -> None:
    (
        _review_blob_service()
        .get_container_client(
            _review_container(workspace)
        )
        .get_blob_client(blob_path)
        .upload_blob(
            (text or "").encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(
                content_type=(
                    "text/plain; charset=utf-8"
                )
            ),
        )
    )


def _blob_service() -> BlobServiceClient:
    processing_conn = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if processing_conn:
        return BlobServiceClient.from_connection_string(
            processing_conn
        )

    processing_account = _processing_account()

    return BlobServiceClient(
        account_url=(
            f"https://{processing_account}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _container_client():
    return (
        _blob_service()
        .get_container_client(
            _processing_container()
        )
    )


def _read_json_blob(
    blob_path: str,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        raw = (
            _container_client()
            .download_blob(blob_path)
            .readall()
        )

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:
        if default is not None:
            return default

        raise


def _write_json_blob(
    blob_path: str,
    payload: dict[str, Any],
) -> None:
    raw = json.dumps(
        payload,
        indent=2,
        default=str,
    ).encode("utf-8")

    (
        _container_client()
        .get_blob_client(blob_path)
        .upload_blob(
            raw,
            overwrite=True,
            content_settings=ContentSettings(
                content_type="application/json"
            ),
        )
    )


def _write_text_blob(
    blob_path: str,
    text: str,
) -> None:
    (
        _container_client()
        .get_blob_client(blob_path)
        .upload_blob(
            (text or "").encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(
                content_type=(
                    "text/plain; charset=utf-8"
                )
            ),
        )
    )


def _download_blob_bytes(
    blob_path: str,
) -> bytes:
    return (
        _container_client()
        .download_blob(blob_path)
        .readall()
    )


def _send_detection_queue_message(
    payload: dict[str, Any],
) -> dict[str, Any]:
    from azure.storage.queue import QueueClient

    queue_name = os.getenv(
        "APC_DETECTION_QUEUE_NAME",
        "apc-detection-jobs",
    )

    queue_conn = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if queue_conn:
        queue = QueueClient.from_connection_string(
            queue_conn,
            queue_name=queue_name,
        )
    else:
        queue = QueueClient(
            account_url=(
                f"https://{_processing_account()}"
                ".queue.core.windows.net"
            ),
            queue_name=queue_name,
            credential=DefaultAzureCredential(),
        )

    try:
        queue.create_queue()
    except Exception:
        pass

    result = queue.send_message(
        json.dumps(
            payload,
            default=str,
        )
    )

    return {
        "queue_name": queue_name,
        "message_id": result.id,
    }


def _content_type_for_document(
    document: dict[str, Any],
) -> str:
    filename = str(
        document.get("source_file_name")
        or document.get("native_blob_path")
        or ""
    )

    guessed, _ = mimetypes.guess_type(
        filename
    )

    return (
        guessed
        or "application/octet-stream"
    )

def _ocr_bytes_with_retry(
    content: bytes,
    content_type: str,
) -> tuple[str, int]:
    max_attempts = max(
        1,
        int(
            os.getenv(
                "APC_OCR_MAX_ATTEMPTS",
                "5",
            )
        ),
    )

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        try:
            return _ocr_bytes(
                content,
                content_type,
            )

        except HttpResponseError as exc:
            status_code = getattr(
                exc,
                "status_code",
                None,
            )

            #
            # Permanent failures such as InvalidContent
            # are NOT retried.
            #
            if status_code != 429:
                raise

            if attempt >= max_attempts:
                raise

            #
            # Respect Azure Retry-After when present,
            # while still progressively backing off.
            #
            retry_after = 0.0

            response = getattr(
                exc,
                "response",
                None,
            )

            headers = getattr(
                response,
                "headers",
                {},
            ) or {}

            try:
                retry_after = float(
                    headers.get(
                        "Retry-After",
                        headers.get(
                            "retry-after",
                            0,
                        ),
                    )
                    or 0
                )
            except Exception:
                retry_after = 0.0

            exponential_delay = float(
                2 ** (attempt - 1)
            )

            delay = max(
                retry_after,
                exponential_delay,
            )

            #
            # Jitter prevents many concurrent OCR threads
            # from retrying at exactly the same instant.
            #
            delay += random.uniform(
                0.25,
                1.25,
            )

            print(
                "Azure Document Intelligence throttled "
                f"OCR request (429). Attempt "
                f"{attempt}/{max_attempts}; retrying "
                f"in {delay:.2f} seconds."
            )

            time.sleep(
                delay
            )

    raise RuntimeError(
        "OCR retry loop exited unexpectedly."
    )

def _ocr_one_document(
    *,
    document: dict[str, Any],
    source_job_id: str,
    ocr_set_id: str,
    workspace: str,
    client: str,
    project: str,
) -> dict[str, Any]:
    doc_id = str(
        document.get("doc_id")
        or ""
    ).strip()

    native_blob_path = str(
        document.get("native_blob_path")
        or ""
    ).strip()

    if not doc_id:
        raise RuntimeError(
            "OCR set contains a document "
            "without doc_id."
        )

    if not native_blob_path:
        raise RuntimeError(
            f"{doc_id}: OCR set document "
            "has no native_blob_path."
        )

    content = _download_blob_bytes(
        native_blob_path
    )

    content_type = _content_type_for_document(
        document
    )

    content, content_type = (
        _prepare_image_for_ocr(
            content,
            content_type,
        )
    )

    text, page_count = _ocr_bytes_with_retry(
        content,
        content_type,
    )

    if not (text or "").strip():
        raise RuntimeError(
            "Azure Document Intelligence "
            "completed OCR but returned no text."
        )

    ocr_result_base = (
        f"{client}/{workspace}/{project}/"
        "processing_center/"
        f"jobs/{source_job_id}/ocr/"
        f"results/{doc_id}"
    )

    text_blob_path = (
        f"{ocr_result_base}.txt"
    )

    result_blob_path = (
        f"{ocr_result_base}.json"
    )

    _write_text_blob(
        text_blob_path,
        text,
    )

    staged_text_blob_path = (
        f"{client}/{workspace}/{project}/"
        "processing_center/"
        f"staged/{source_job_id}/"
        f"text/{doc_id}.txt"
    )

    _write_review_text_blob(
        workspace=workspace,
        blob_path=staged_text_blob_path,
        text=text,
    )

    result_payload = {
        "job_type": "ocr_document_result",
        "source_job_id": source_job_id,
        "ocr_set_id": ocr_set_id,
        "doc_id": doc_id,
        "file_id": document.get(
            "file_id"
        ),
        "processing_set_id":
            document.get(
                "processing_set_id"
            ),
        "processing_set_number":
            document.get(
                "processing_set_number"
            ),
        "processing_set_ordinal":
            document.get(
                "processing_set_ordinal"
            ),
        "status": "completed",
        "page_count": int(
            page_count or 0
        ),
        "text_blob_path":
            text_blob_path,
        "native_blob_path":
            native_blob_path,
        "ocr_engine":
            "azure_document_intelligence_read",
        "model_id":
            "prebuilt-read",
        "completed_at":
            utc_now(),
    }

    _write_json_blob(
        result_blob_path,
        result_payload,
    )

    result_payload[
        "result_blob_path"
    ] = result_blob_path

    return result_payload


def _update_set_status(
    *,
    status_blob_path: str,
    status: str,
    stage: str,
    message: str,
    document_count: int,
    documents_completed: int,
    documents_failed: int,
    pages_completed: int,
    current_doc_id: str = "",
    errors: list[dict[str, Any]] | None = None,
) -> None:
    current = _read_json_blob(
        status_blob_path,
        default={},
    )

    total_finished = (
        documents_completed
        + documents_failed
    )

    progress_pct = 0

    if document_count > 0:
        progress_pct = int(
            (
                total_finished
                / document_count
            )
            * 100
        )

    progress_pct = max(
        0,
        min(
            progress_pct,
            100,
        ),
    )

    current.update(
        {
            "status":
                status,
            "stage":
                stage,
            "progress_pct":
                progress_pct,
            "message":
                message,
            "current_doc_id":
                current_doc_id,
            "document_count":
                document_count,
            "documents_completed":
                documents_completed,
            "documents_failed":
                documents_failed,
            "documents_remaining":
                max(
                    document_count
                    - total_finished,
                    0,
                ),
            "pages_completed":
                pages_completed,
            "errors":
                errors or [],
            "updated_at":
                utc_now(),
        }
    )

    if status == "running":
        current.setdefault(
            "started_at",
            utc_now(),
        )

    if status in {
        "completed",
        "completed_with_exceptions",
        "failed",
    }:
        current["completed_at"] = (
            utc_now()
        )

    _write_json_blob(
        status_blob_path,
        current,
    )


def _queue_detection_for_completed_ocr(
    *,
    payload: dict[str, Any],
    completed_documents: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not completed_documents:
        return None

    #
    # MANUAL DATA DETECTION GATE
    #
    # OCR is complete. Completed OCR documents remain available
    # to the existing Data Detection Ready workflow.
    #
    # Do NOT automatically create or enqueue a DET-* job here.
    #
    return None

    from uuid import uuid4

    detection_job_id = (
        f"DET-{uuid4().hex[:16].upper()}"
    )

    workspace = str(
        payload.get("workspace")
        or "capture"
    )

    client = str(
        payload.get("client")
        or ""
    )

    project = str(
        payload.get("project")
        or ""
    )

    source_job_id = str(
        payload.get("source_job_id")
        or ""
    )

    detection_base = (
        f"{client}/{workspace}/{project}/"
        "processing_center/"
        "detection/jobs/"
        f"{detection_job_id}"
    )

    request_blob_path = (
        f"{detection_base}/request.json"
    )

    status_blob_path = (
        f"{detection_base}/status.json"
    )

    documents = []

    for result in completed_documents:
        documents.append(
            {
                "doc_id":
                    result.get("doc_id"),
                "file_id":
                    result.get("file_id"),
                "text_staged_blob_path":
                    result.get(
                        "text_blob_path"
                    ),
                "native_staged_blob_path":
                    result.get(
                        "native_blob_path"
                    ),
                "source_type":
                    "ocr_document",
                "detection_mode":
                    "ocr_text",
                "processing_set_id":
                    result.get(
                        "processing_set_id"
                    ),
                "processing_set_number":
                    result.get(
                        "processing_set_number"
                    ),
                "processing_set_ordinal":
                    result.get(
                        "processing_set_ordinal"
                    ),
            }
        )

    requested_at = utc_now()

    request_payload = {
        "job_type":
            "data_element_detection",
        "detection_job_id":
            detection_job_id,
        "workspace":
            workspace,
        "client":
            client,
        "project":
            project,
        "source_job_id":
            source_job_id,
        "source_ocr_set_id":
            payload.get(
                "ocr_set_id"
            ),
        "doc_ids": [
            str(
                document.get("doc_id")
                or ""
            )
            for document in documents
        ],
        "detection_mode":
            "ocr_text",
        "documents":
            documents,
        "protocol_name":
            payload.get(
                "protocol_name"
            ),
        "protocol_version":
            payload.get(
                "protocol_version"
            ),
        "include_phi":
            bool(
                payload.get(
                    "include_phi",
                    True,
                )
            ),
        "requested_by":
            payload.get(
                "requested_by"
            )
            or "APC OCR Worker",
        "requested_at":
            requested_at,
        "request_blob_path":
            request_blob_path,
        "status_blob_path":
            status_blob_path,
    }

    status_payload = {
        "job_type":
            "data_element_detection",
        "detection_job_id":
            detection_job_id,
        "source_job_id":
            source_job_id,
        "source_ocr_set_id":
            payload.get(
                "ocr_set_id"
            ),
        "workspace":
            workspace,
        "client":
            client,
        "project":
            project,
        "status":
            "queued",
        "stage":
            "queued",
        "progress_pct":
            0,
        "selected_doc_count":
            len(documents),
        "documents_scanned":
            0,
        "documents_with_hits":
            0,
        "documents_no_hits":
            0,
        "documents_nfr":
            0,
        "documents_exception":
            0,
        "entity_hit_count":
            0,
        "message":
            "OCR-completed population queued "
            "for Data Element Detection.",
        "requested_at":
            requested_at,
        "created_at":
            utc_now(),
        "updated_at":
            utc_now(),
        "request_blob_path":
            request_blob_path,
        "status_blob_path":
            status_blob_path,
    }

    _write_json_blob(
        request_blob_path,
        request_payload,
    )

    _write_json_blob(
        status_blob_path,
        status_payload,
    )

    queue_result = (
        _send_detection_queue_message(
            request_payload
        )
    )

    return {
        "detection_job_id":
            detection_job_id,
        "detection_queue_name":
            queue_result.get(
                "queue_name"
            ),
        "detection_message_id":
            queue_result.get(
                "message_id"
            ),
    }


def process_ocr_set_message(
    message_content: str,
) -> None:
    payload = json.loads(
        message_content
    )

    if (
        str(
            payload.get("job_type")
            or ""
        ).strip().lower()
        != "ocr_set"
    ):
        raise ValueError(
            "OCR worker received unsupported "
            "job_type."
        )

    ocr_set_id = str(
        payload.get("ocr_set_id")
        or ""
    ).strip()

    source_job_id = str(
        payload.get("source_job_id")
        or ""
    ).strip()

    workspace = str(
        payload.get("workspace")
        or "capture"
    ).strip()

    client = str(
        payload.get("client")
        or ""
    ).strip()

    project = str(
        payload.get("project")
        or ""
    ).strip()

    status_blob_path = str(
        payload.get("status_blob_path")
        or ""
    ).strip()

    documents = (
        payload.get("documents")
        or []
    )

    if not ocr_set_id:
        raise ValueError(
            "OCR queue message missing "
            "ocr_set_id."
        )

    if not source_job_id:
        raise ValueError(
            "OCR queue message missing "
            "source_job_id."
        )

    if not client:
        raise ValueError(
            "OCR queue message missing client."
        )

    if not project:
        raise ValueError(
            "OCR queue message missing project."
        )

    if not status_blob_path:
        raise ValueError(
            "OCR queue message missing "
            "status_blob_path."
        )

    if not isinstance(
        documents,
        list,
    ):
        raise ValueError(
            "OCR queue message documents "
            "must be a list."
        )

    #
    # Durable idempotency barrier.
    #
    existing_status = _read_json_blob(
        status_blob_path,
        default={},
    )

    if (
        str(
            existing_status.get("status")
            or ""
        ).lower()
        in {
            "completed",
            "completed_with_exceptions",
        }
    ):
        return

    concurrency = max(
        1,
        int(
            os.getenv(
                "APC_OCR_DOCUMENT_CONCURRENCY",
                "8",
            )
        ),
    )

    document_count = len(
        documents
    )

    completed_documents: list[
        dict[str, Any]
    ] = []

    errors: list[
        dict[str, Any]
    ] = []

    pages_completed = 0

    _update_set_status(
        status_blob_path=status_blob_path,
        status="running",
        stage="ocr_processing",
        message=(
            f"OCR processing started for "
            f"{document_count:,} document(s)."
        ),
        document_count=document_count,
        documents_completed=0,
        documents_failed=0,
        pages_completed=0,
    )

    try:
        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix="insyt-ocr",
        ) as executor:

            future_map = {
                executor.submit(
                    _ocr_one_document,
                    document=document,
                    source_job_id=source_job_id,
                    ocr_set_id=ocr_set_id,
                    workspace=workspace,
                    client=client,
                    project=project,
                ): document
                for document in documents
            }

            for future in as_completed(
                future_map
            ):
                document = future_map[
                    future
                ]

                doc_id = str(
                    document.get("doc_id")
                    or ""
                )

                try:
                    result = future.result()

                    completed_documents.append(
                        result
                    )

                    pages_completed += int(
                        result.get(
                            "page_count"
                        )
                        or 0
                    )

                except Exception as exc:
                    errors.append(
                        {
                            "doc_id":
                                doc_id,
                            "error_type":
                                type(exc).__name__,
                            "error":
                                str(exc),
                        }
                    )

                _update_set_status(
                    status_blob_path=
                        status_blob_path,
                    status="running",
                    stage="ocr_processing",
                    message=(
                        f"OCR set {ocr_set_id}: "
                        f"{len(completed_documents):,} "
                        "completed, "
                        f"{len(errors):,} failed."
                    ),
                    document_count=
                        document_count,
                    documents_completed=
                        len(
                            completed_documents
                        ),
                    documents_failed=
                        len(errors),
                    pages_completed=
                        pages_completed,
                    current_doc_id=
                        doc_id,
                    errors=
                        errors[:100],
                )

        detection_result = (
            _queue_detection_for_completed_ocr(
                payload=payload,
                completed_documents=
                    completed_documents,
            )
        )

        final_status = (
            "completed"
            if not errors
            else "completed_with_exceptions"
        )

        _update_set_status(
            status_blob_path=status_blob_path,
            status=final_status,
            stage="completed",
            message=(
                f"OCR set {ocr_set_id} completed: "
                f"{len(completed_documents):,} "
                "successful, "
                f"{len(errors):,} failed."
            ),
            document_count=document_count,
            documents_completed=
                len(
                    completed_documents
                ),
            documents_failed=
                len(errors),
            pages_completed=
                pages_completed,
            errors=
                errors[:100],
        )

        #
        # Append downstream Detection information.
        #
        if detection_result:
            status_payload = _read_json_blob(
                status_blob_path,
                default={},
            )

            status_payload.update(
                detection_result
            )

            status_payload[
                "updated_at"
            ] = utc_now()

            _write_json_blob(
                status_blob_path,
                status_payload,
            )

        #
        # IMPORTANT:
        # If every document failed, raise so Azure Queue
        # retries the OCR set.
        #
        if (
            document_count > 0
            and not completed_documents
        ):
            raise RuntimeError(
                f"OCR set {ocr_set_id} failed "
                "for every document."
            )

    except Exception as exc:
        _update_set_status(
            status_blob_path=status_blob_path,
            status="failed",
            stage="failed",
            message=(
                f"OCR set {ocr_set_id} failed: "
                f"{type(exc).__name__}: {exc}"
            ),
            document_count=document_count,
            documents_completed=
                len(
                    completed_documents
                ),
            documents_failed=max(
                len(errors),
                document_count
                - len(
                    completed_documents
                ),
            ),
            pages_completed=
                pages_completed,
            errors=
                errors[:100],
        )

        raise