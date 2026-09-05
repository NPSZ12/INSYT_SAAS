from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.processing_center_azure import (
    _processing_container_client,
    _project_base_path,
    _read_processing_json_blob,
    _utc_now,
    _write_processing_json_blob,
)

from uuid import uuid4


router = APIRouter(
    prefix="/api",
    tags=["cyber2-header-sets"],
)


class CreateCyber2HeaderSetRequest(
    BaseModel
):
    client: str
    project: str
    doc_ids: list[str] = []
    requested_by: str = ""


@router.post(
    "/{workspace}/cyber2/header-sets"
)
def create_cyber2_header_set(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    request: CreateCyber2HeaderSetRequest,
) -> dict[str, Any]:

    client = str(
        request.client or ""
    ).strip()

    project = str(
        request.project or ""
    ).strip()

    requested_doc_ids = [
        str(doc_id).strip()
        for doc_id in (
            request.doc_ids
            or []
        )
        if str(doc_id).strip()
    ]

    requested_doc_ids = list(
        dict.fromkeys(
            requested_doc_ids
        )
    )

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not requested_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Select at least one CSV "
                "for the Header Set."
            ),
        )

    base_path = (
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    intake_prefix = (
        f"{base_path}/cyber2/"
        f"intake/documents/"
    )

    container_client = (
        _processing_container_client()
    )

    intake_documents: dict[
        str,
        dict[str, Any],
    ] = {}

    for blob in (
        container_client.list_blobs(
            name_starts_with=(
                intake_prefix
            )
        )
    ):
        blob_path = str(
            blob.name
            or ""
        )

        if not blob_path.endswith(
            ".json"
        ):
            continue

        try:
            payload = (
                _read_processing_json_blob(
                    blob_path
                )
            )
        except Exception:
            continue

        if not isinstance(
            payload,
            dict,
        ):
            continue

        doc_id = str(
            payload.get(
                "doc_id"
            )
            or ""
        ).strip()

        if not doc_id:
            continue

        intake_documents[
            doc_id
        ] = payload

    missing_doc_ids = [
        doc_id
        for doc_id in requested_doc_ids
        if doc_id
        not in intake_documents
    ]

    if missing_doc_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "One or more selected "
                    "documents are not present "
                    "in Cyber² Intake."
                ),
                "missing_doc_ids": (
                    missing_doc_ids
                ),
            },
        )

    header_set_id = (
        "HDRSET-"
        + uuid4().hex[
            :12
        ].upper()
    )

    created_at = (
        _utc_now()
    )

    header_set_documents: list[
        dict[str, Any]
    ] = []

    for doc_id in (
        requested_doc_ids
    ):
        source = (
            intake_documents[
                doc_id
            ]
        )

        header_set_documents.append(
            {
                "doc_id": doc_id,

                "source_csv_path": (
                    source.get(
                        "source_csv_path"
                    )
                    or ""
                ),

                "classification": (
                    source.get(
                        "classification"
                    )
                    or ""
                ),

                "entity_types": (
                    source.get(
                        "entity_types"
                    )
                    or []
                ),

                "profiled_entity_count": (
                    source.get(
                        "profiled_entity_count"
                    )
                ),

                "source_job_id": (
                    source.get(
                        "source_job_id"
                    )
                    or ""
                ),

                "detection_job_id": (
                    source.get(
                        "detection_job_id"
                    )
                    or ""
                ),

                "detection_run_id": (
                    source.get(
                        "detection_run_id"
                    )
                    or ""
                ),

                "original_filename": (
                    source.get(
                        "original_filename"
                    )
                    or ""
                ),

                "original_workbook_name": (
                    source.get(
                        "original_workbook_name"
                    )
                    or ""
                ),

                "original_workbook_file_id": (
                    source.get(
                        "original_workbook_file_id"
                    )
                    or ""
                ),

                "sheet_name": (
                    source.get(
                        "sheet_name"
                    )
                    or ""
                ),

                "sheet_index": (
                    source.get(
                        "sheet_index"
                    )
                ),

                "sheet_visibility": (
                    source.get(
                        "sheet_visibility"
                    )
                    or ""
                ),

                "intake_index_path": (
                    source.get(
                        "intake_index_path"
                    )
                    or ""
                ),

                "header_status": (
                    "pending_identification"
                ),

                "header_confidence": None,
            }
        )

    manifest = {
        "schema_version": 1,

        "header_set_id": (
            header_set_id
        ),

        "workspace": workspace,
        "client": client,
        "project": project,

        "status": (
            "pending_header_identification"
        ),

        "created_at": (
            created_at
        ),

        "created_by": str(
            request.requested_by
            or ""
        ).strip(),

        "document_count": len(
            header_set_documents
        ),

        "doc_ids": (
            requested_doc_ids
        ),

        "documents": (
            header_set_documents
        ),
    }

    manifest_path = (
        f"{base_path}/cyber2/"
        f"header_sets/"
        f"{header_set_id}.json"
    )

    upload_result = (
        _write_processing_json_blob(
            blob_path=(
                manifest_path
            ),
            payload=manifest,
            overwrite=False,
        )
    )

    return {
        "status": "created",

        "message": (
            f"Header Set "
            f"{header_set_id} "
            f"created with "
            f"{len(header_set_documents)} "
            f"CSV(s)."
        ),

        "header_set_id": (
            header_set_id
        ),

        "header_set_path": (
            manifest_path
        ),

        "document_count": len(
            header_set_documents
        ),

        "documents": (
            header_set_documents
        ),

        "manifest_upload": (
            upload_result
        ),
    }


@router.get(
    "/{workspace}/cyber2/header-sets"
)
def list_cyber2_header_sets(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    base_path = (
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    prefix = (
        f"{base_path}/cyber2/"
        f"header_sets/"
    )

    container_client = (
        _processing_container_client()
    )

    header_sets: list[
        dict[str, Any]
    ] = []

    for blob in (
        container_client.list_blobs(
            name_starts_with=prefix
        )
    ):
        blob_path = str(
            blob.name
            or ""
        )

        if not blob_path.endswith(
            ".json"
        ):
            continue

        try:
            payload = (
                _read_processing_json_blob(
                    blob_path
                )
            )
        except Exception:
            continue

        if not isinstance(
            payload,
            dict,
        ):
            continue

        header_sets.append(
            {
                **payload,

                "header_set_path": (
                    blob_path
                ),

                "last_modified": (
                    blob.last_modified.isoformat()
                    if getattr(
                        blob,
                        "last_modified",
                        None,
                    )
                    else None
                ),
            }
        )

    header_sets.sort(
        key=lambda row: (
            str(
                row.get(
                    "created_at"
                )
                or row.get(
                    "last_modified"
                )
                or ""
            )
        ),
        reverse=True,
    )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_count": len(
            header_sets
        ),

        "header_sets": (
            header_sets
        ),

        "header_sets_prefix": (
            prefix
        ),
    }