from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import case, func


DEFAULT_CHUNK_SIZE = 500


def _enabled() -> bool:
    value = str(
        os.getenv(
            "INSYT_ENABLE_DOCUMENT_LIFECYCLE_INDEX",
            "false",
        )
        or ""
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def _chunk_size() -> int:
    raw = str(
        os.getenv(
            "INSYT_DOCUMENT_LIFECYCLE_CHUNK_SIZE",
            str(DEFAULT_CHUNK_SIZE),
        )
        or ""
    ).strip()

    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_CHUNK_SIZE

    return max(
        1,
        min(
            value,
            1000,
        ),
    )


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _build_staging_lookup(
    staging_payloads: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    for payload in staging_payloads or []:
        if not isinstance(payload, dict):
            continue

        #
        # Shape A:
        # ordinary review uploader
        #
        ordinary = payload.get("uploads")

        if isinstance(ordinary, list):
            for item in ordinary:
                if not isinstance(item, dict):
                    continue

                doc_id = _safe_text(
                    item.get("doc_id")
                )

                kind = _safe_text(
                    item.get("kind")
                ).lower()

                if not doc_id:
                    continue

                row = lookup.setdefault(
                    doc_id,
                    {},
                )

                if kind == "native":
                    upload_ok = (
                        _safe_text(
                            item.get("status")
                        ).lower()
                        == "uploaded"
                    )

                    row["native_uploaded"] = upload_ok

                    row["native_staged_blob_path"] = (
                        _safe_text(
                            item.get("blob_path")
                        )
                        or None
                        if upload_ok
                        else None
                    )

                    row["native_bytes"] = (
                        int(
                            item.get("bytes")
                            or 0
                        )
                        if upload_ok
                        else 0
                    )

                elif kind == "text":
                    upload_ok = (
                        _safe_text(
                            item.get("status")
                        ).lower()
                        == "uploaded"
                    )

                    row["text_uploaded"] = upload_ok

                    row["text_staged_blob_path"] = (
                        _safe_text(
                            item.get("blob_path")
                        )
                        or None
                        if upload_ok
                        else None
                    )

                    row["text_bytes"] = (
                        int(
                            item.get("bytes")
                            or 0
                        )
                        if upload_ok
                        else 0
                    )

        #
        # Shape B:
        # XL / JSON / structured fast-lane uploaders
        #
        uploaded = payload.get("uploaded")

        if isinstance(uploaded, list):
            for item in uploaded:
                if not isinstance(item, dict):
                    continue

                doc_id = _safe_text(
                    item.get("doc_id")
                )

                if not doc_id:
                    continue

                row = lookup.setdefault(
                    doc_id,
                    {},
                )

                native_path = _safe_text(
                    item.get(
                        "native_staged_blob_path"
                    )
                )

                text_path = _safe_text(
                    item.get(
                        "text_staged_blob_path"
                    )
                )

                upload_ok = (
                    _safe_text(
                        item.get("status")
                    ).lower()
                    == "uploaded"
                )

                if native_path:
                    row[
                        "native_staged_blob_path"
                    ] = native_path

                    row["native_uploaded"] = (
                        upload_ok
                    )

                if text_path:
                    row[
                        "text_staged_blob_path"
                    ] = text_path

                    row["text_uploaded"] = (
                        upload_ok
                    )

                row["native_bytes"] = int(
                    item.get("bytes")
                    or 0
                )

                row["text_bytes"] = int(
                    item.get(
                        "text_bytes"
                    )
                    or 0
                )

                #
                # Preserve arbitrary adapter metadata
                # without teaching lifecycle about
                # individual source formats.
                #
                row["staging_metadata"] = {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {
                        "doc_id",
                        "native_staged_blob_path",
                        "text_staged_blob_path",
                        "status",
                        "bytes",
                        "text_bytes",
                    }
                }

    return lookup


def build_document_lifecycle_rows(
    *,
    ledger_db,
    workspace: str,
    client: str,
    project: str,
    source_job_id: str,
    tracked_job_id: str | None = None,
    staging_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build lifecycle rows from the APC ledger plus confirmed Azure upload results.

    Important:
      - Does NOT filter is_duplicate=0.
      - Does NOT filter on Review Promotion membership.
      - Every non-container, non-deNIST row with a Doc ID is eligible
        for lifecycle registration.
      - Detection READY requires confirmed staged text.
    """

    rows = ledger_db.query(
        """
        SELECT
            file_id,
            job_id,
            doc_id,
            parent_file_id,
            family_id,
            original_path,
            normalized_path,
            extension,
            source_bytes,
            page_count,
            md5,
            sha1,
            sha256,
            is_duplicate,
            is_denisted,
            requires_ocr,
            promoted_to_review,
            review_export_status
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND doc_id IS NOT NULL
        ORDER BY doc_id
        """,
        (
            source_job_id,
        ),
    )

    staging_lookup = _build_staging_lookup(
        staging_payloads
    )

    lifecycle_rows: list[
        dict[str, Any]
    ] = []

    for row in rows:
        doc_id = _safe_text(
            row["doc_id"]
        )

        if not doc_id:
            continue

        staged = staging_lookup.get(
            doc_id,
            {},
        )

        native_uploaded = bool(
            staged.get(
                "native_uploaded"
            )
        )

        text_uploaded = bool(
            staged.get(
                "text_uploaded"
            )
        )

        normalized_path = (
            _safe_text(
                row["normalized_path"]
            )
            or _safe_text(
                row["original_path"]
            )
        )

        filename = (
            Path(
                normalized_path
            ).name
            if normalized_path
            else ""
        )

        extension = _safe_text(
            row["extension"]
        ).lower().lstrip(".")

        native_staged_blob_path = (
            staged.get(
                "native_staged_blob_path"
            )
        )

        text_staged_blob_path = (
            staged.get(
                "text_staged_blob_path"
            )
        )

        try:
            text_staged_bytes = int(
                staged.get(
                    "text_bytes"
                )
                or 0
            )
        except Exception:
            text_staged_bytes = 0

        #
        # READY is based on confirmed staged text.
        #
        detection_status = (
            "READY"
            if text_uploaded
            else "PENDING"
        )

        ingestion_status = (
            "COMPLETE"
            if native_uploaded
            else "PENDING"
        )

        promotion_status = (
            "STAGED"
            if (
                native_uploaded
                or text_uploaded
            )
            else "PENDING"
        )

        source_metadata = {
            "normalized_path":
                normalized_path,

            "md5":
                _safe_text(
                    row["md5"]
                ),

            "sha1":
                _safe_text(
                    row["sha1"]
                ),

            "sha256":
                _safe_text(
                    row["sha256"]
                ),

            "requires_ocr":
                bool(
                    row[
                        "requires_ocr"
                    ]
                    or 0
                ),

            "review_export_status":
                _safe_text(
                    row[
                        "review_export_status"
                    ]
                ),

            "native_upload_status":
                (
                    "uploaded"
                    if native_uploaded
                    else "not_uploaded"
                ),

            "text_upload_status":
                (
                    "uploaded"
                    if text_uploaded
                    else "not_uploaded"
                ),

            "staging_metadata":
                staged.get(
                    "staging_metadata"
                )
                or {},
        }

        lifecycle_rows.append(
            {
                "workspace":
                    _safe_text(
                        workspace
                    ).lower()
                    or "capture",

                "client":
                    _safe_text(
                        client
                    ),

                "project":
                    _safe_text(
                        project
                    ),

                "doc_id":
                    doc_id,

                "source_job_id":
                    _safe_text(
                        source_job_id
                    ),

                "tracked_job_id":
                    _safe_text(
                        tracked_job_id
                    )
                    or None,

                "file_id":
                    _safe_text(
                        row["file_id"]
                    )
                    or None,

                "parent_file_id":
                    _safe_text(
                        row[
                            "parent_file_id"
                        ]
                    )
                    or None,

                "family_id":
                    _safe_text(
                        row["family_id"]
                    )
                    or None,

                "original_filename":
                    filename
                    or None,

                "extension":
                    extension
                    or None,

                "source_type":
                    "document",

                "source_bytes":
                    int(
                        row["source_bytes"]
                        or 0
                    ),

                "page_count":
                    int(
                        row["page_count"]
                        or 0
                    ),

                "content_hash":
                    _safe_text(
                        row["sha256"]
                    ).lower()
                    or None,

                "canonical_doc_id":
                    None,

                "is_duplicate":
                    bool(
                        row["is_duplicate"]
                        or 0
                    ),

                #
                # We are NOT guessing email occurrence semantics here.
                # That will be set by the dedicated occurrence logic.
                #
                "preserve_occurrence":
                    False,

                "is_denisted":
                    bool(
                        row["is_denisted"]
                        or 0
                    ),

                "native_staged_blob_path":
                    native_staged_blob_path
                    or None,

                "text_staged_blob_path":
                    text_staged_blob_path
                    or None,

                "text_staged_bytes":
                    text_staged_bytes,

                "native_live_blob_path":
                    None,

                "text_live_blob_path":
                    None,

                "ingestion_status":
                    ingestion_status,

                "ocr_status":
                    (
                        "REQUIRED"
                        if bool(
                            row[
                                "requires_ocr"
                            ]
                            or 0
                        )
                        else "NOT_REQUIRED"
                    ),

                "detection_status":
                    detection_status,

                "promotion_status":
                    promotion_status,

                "review_status":
                    None,

                "detection_mode":
                    "full",

                "coding":
                    {},

                "source_metadata":
                    source_metadata,

                "detection_metadata":
                    {},
            }
        )

    return lifecycle_rows


def _upsert_chunk(
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    # Lazy imports are intentional.
    # When lifecycle indexing is disabled, the processing worker must not
    # require PostgreSQL/Key Vault configuration merely to import/start.
    from app.database.connection import engine
    from app.models.document_lifecycle import DocumentLifecycle

    table = DocumentLifecycle.__table__

    statement = insert(
        table
    ).values(
        rows
    )

    excluded = statement.excluded

    statement = (
        statement
        .on_conflict_do_update(
            constraint=(
                "uq_document_lifecycle_project_doc"
            ),
            set_={
                "source_job_id":
                    excluded.source_job_id,

                "tracked_job_id":
                    excluded.tracked_job_id,

                "file_id":
                    excluded.file_id,

                "parent_file_id":
                    excluded.parent_file_id,

                "family_id":
                    excluded.family_id,

                "original_filename":
                    excluded.original_filename,

                "extension":
                    excluded.extension,

                "source_type":
                    excluded.source_type,

                "source_bytes":
                    excluded.source_bytes,

                "page_count":
                    excluded.page_count,

                "content_hash":
                    excluded.content_hash,

                "is_duplicate":
                    excluded.is_duplicate,

                "is_denisted":
                    excluded.is_denisted,

                "native_staged_blob_path":
                    func.coalesce(
                        excluded.native_staged_blob_path,
                        table.c.native_staged_blob_path,
                    ),

                "text_staged_blob_path":
                    func.coalesce(
                        excluded.text_staged_blob_path,
                        table.c.text_staged_blob_path,
                    ),

                "text_staged_bytes":
                    case(
                        (
                            excluded.text_staged_blob_path
                            .is_not(None),
                            excluded.text_staged_bytes,
                        ),
                        else_=table.c.text_staged_bytes,
                    ),

                "ingestion_status":
                    case(
                        (
                            excluded.ingestion_status
                            == "COMPLETE",
                            excluded.ingestion_status,
                        ),
                        else_=table.c.ingestion_status,
                    ),

                "ocr_status":
                    excluded.ocr_status,

                "detection_status":
                    case(
                        (
                            (
                                table.c.detection_status
                                == "PENDING"
                            )
                            & (
                                excluded.detection_status
                                == "READY"
                            ),
                            "READY",
                        ),
                        else_=table.c.detection_status,
                    ),

                "promotion_status":
                    case(
                        (
                            (
                                table.c.promotion_status
                                == "PENDING"
                            )
                            & (
                                excluded.promotion_status
                                == "STAGED"
                            ),
                            "STAGED",
                        ),
                        else_=table.c.promotion_status,
                    ),

                "detection_mode":
                    excluded.detection_mode,

                "source_metadata":
                    excluded.source_metadata,

                "updated_at":
                    func.now(),
            },
        )
    )

    with engine.begin() as connection:
        connection.execute(
            statement
        )

    return len(
        rows
    )

def bulk_mark_ocr_completed(
    *,
    workspace: str,
    client: str,
    project: str,
    source_job_id: str,
    completed_documents: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    """
    Advance successfully OCR-completed documents in the
    PostgreSQL lifecycle index.

    This function is deliberately independent of the APC
    SQLite ledger because asynchronous OCR may execute on a
    different worker instance after the ingestion ledger is gone.

    It does not enqueue Detection. It only makes successfully
    OCR-completed documents eligible for the existing manual
    Detection Ready workflow.
    """

    if not _enabled():
        return {
            "enabled": False,
            "status": "disabled",
            "updated_count": 0,
        }

    if not completed_documents:
        return {
            "enabled": True,
            "status": "no_documents",
            "updated_count": 0,
        }

    #
    # Lazy imports preserve the current worker behavior when
    # lifecycle indexing is disabled.
    #
    from sqlalchemy import text
    from app.database.connection import engine

    parameters: list[
        dict[str, Any]
    ] = []

    for document in completed_documents:
        doc_id = _safe_text(
            document.get("doc_id")
        )

        staged_text_blob_path = _safe_text(
            document.get(
                "staged_text_blob_path"
            )
        )

        if (
            not doc_id
            or not staged_text_blob_path
        ):
            continue

        try:
            text_bytes = int(
                document.get(
                    "text_bytes"
                )
                or 0
            )
        except Exception:
            text_bytes = 0

        parameters.append(
            {
                "workspace":
                    _safe_text(
                        workspace
                    ).lower()
                    or "capture",

                "client":
                    _safe_text(
                        client
                    ),

                "project":
                    _safe_text(
                        project
                    ),

                "source_job_id":
                    _safe_text(
                        source_job_id
                    ),

                "doc_id":
                    doc_id,

                "text_staged_blob_path":
                    staged_text_blob_path,

                "text_staged_bytes":
                    text_bytes,
            }
        )

    if not parameters:
        return {
            "enabled": True,
            "status": "no_valid_documents",
            "updated_count": 0,
        }

    statement = text(
        """
        UPDATE document_lifecycle
        SET
            text_staged_blob_path =
                :text_staged_blob_path,

            text_staged_bytes =
                :text_staged_bytes,

            ocr_status =
                'COMPLETE',

            detection_status =
                CASE
                    WHEN detection_status = 'PENDING'
                        THEN 'READY'
                    ELSE detection_status
                END,

            updated_at =
                NOW()

        WHERE workspace =
                :workspace
          AND client =
                :client
          AND project =
                :project
          AND source_job_id =
                :source_job_id
          AND doc_id =
                :doc_id
        """
    )

    updated = 0

    #
    # Chunked executemany keeps OCR-set completion scalable
    # without issuing one transaction per document.
    #
    size = _chunk_size()

    with engine.begin() as connection:
        for offset in range(
            0,
            len(parameters),
            size,
        ):
            chunk = parameters[
                offset:
                offset + size
            ]

            result = connection.execute(
                statement,
                chunk,
            )

            if (
                result.rowcount is not None
                and result.rowcount >= 0
            ):
                updated += int(
                    result.rowcount
                )

    return {
        "enabled": True,
        "status": "completed",
        "document_count":
            len(parameters),
        "updated_count":
            updated,
        "chunk_size":
            size,
    }

def bulk_upsert_document_lifecycle(
    *,
    ledger_db,
    workspace: str,
    client: str,
    project: str,
    source_job_id: str,
    tracked_job_id: str | None = None,
    staging_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Register/update an APC job in the PostgreSQL lifecycle index.

    Feature-flagged so deployment is additive and inert until explicitly enabled.
    """

    if not _enabled():
        return {
            "enabled": False,
            "status": "disabled",
            "row_count": 0,
        }

    rows = build_document_lifecycle_rows(
        ledger_db=ledger_db,
        workspace=workspace,
        client=client,
        project=project,
        source_job_id=source_job_id,
        tracked_job_id=tracked_job_id,
        staging_payloads=staging_payloads,
    )

    size = _chunk_size()
    written = 0

    for offset in range(
        0,
        len(rows),
        size,
    ):
        chunk = rows[
            offset:
            offset + size
        ]

        written += _upsert_chunk(
            chunk
        )

    return {
        "enabled": True,
        "status": "completed",
        "row_count": len(rows),
        "written_count": written,
        "chunk_size": size,
    }
