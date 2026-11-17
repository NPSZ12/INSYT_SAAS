from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.processing_center_azure import (
    _processing_container_client,
    User,
    require_admin,
    require_scoped_project_access,
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



def _claim_native_json_intake_blob(
    *,
    blob_client,
    expected_document,
    header_set_id,
    created_at,
    requested_by,
):
    """Claim one native JSON intake record using Azure ETag CAS.

    Source JSON bytes are never opened or modified. Only the
    existing intake metadata blob is conditionally updated.
    """
    import json
    from azure.core import MatchConditions
    from azure.core.exceptions import (
        HttpResponseError,
        ResourceModifiedError,
        ResourceNotFoundError,
    )
    from azure.storage.blob import ContentSettings

    try:
        properties = blob_client.get_blob_properties()
        etag = str(getattr(properties, "etag", "") or "")

        if not etag:
            raise HTTPException(
                status_code=409,
                detail="Intake record has no usable ETag.",
            )

        raw = blob_client.download_blob(
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
        ).readall()

    except HTTPException:
        raise
    except (ResourceModifiedError, ResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=409,
            detail="JSON intake record changed; reload and retry.",
        ) from exc
    except HttpResponseError as exc:
        status = getattr(exc, "status_code", None)
        raise HTTPException(
            status_code=409 if status in (404, 409, 412) else 503,
            detail="Unable to obtain a stable JSON intake snapshot.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to read JSON intake record.",
        ) from exc

    try:
        current = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="JSON intake metadata is invalid.",
        ) from exc

    if not isinstance(current, dict):
        raise HTTPException(
            status_code=409,
            detail="JSON intake metadata must be an object.",
        )

    if current.get("source_kind") != "native_json":
        raise HTTPException(
            status_code=409,
            detail="Source is no longer native JSON.",
        )

    for key in (
        "doc_id",
        "source_native_path",
        "source_sha256",
        "source_bytes",
    ):
        if current.get(key) != expected_document.get(key):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Native JSON source identity changed. "
                    "Refresh intake before creating a Header Set."
                ),
            )

    assigned = str(
        current.get("header_set_id") or ""
    ).strip()

    if assigned:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Native JSON is already assigned.",
                "header_set_id": assigned,
                "doc_id": current.get("doc_id"),
            },
        )

    updated = dict(current)
    updated.update({
        "header_set_id": header_set_id,
        "cyber2_stage": "header_schema_mapping",
        "header_set_status": "assigned",
        "sent_to_header_mapping_at": created_at,
        "sent_to_header_mapping_by": requested_by,
    })

    try:
        result = blob_client.upload_blob(
            json.dumps(
                updated, indent=2, default=str
            ).encode("utf-8"),
            overwrite=True,
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
            content_settings=ContentSettings(
                content_type="application/json"
            ),
        )
    except ResourceModifiedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Concurrent JSON assignment detected; "
                "reload the Header Set listing."
            ),
        ) from exc
    except HttpResponseError as exc:
        status = getattr(exc, "status_code", None)
        raise HTTPException(
            status_code=409 if status in (409, 412) else 503,
            detail="Conditional JSON assignment failed.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to save JSON intake assignment.",
        ) from exc

    return {
        "doc_id": current["doc_id"],
        "previous": current,
        "assigned": updated,
        "previous_etag": etag,
        "committed_etag": (
            result.get("etag")
            if isinstance(result, dict)
            else getattr(result, "etag", None)
        ),
    }



def _release_native_json_intake_claim(
    *,
    blob_client,
    claim,
):
    """Restore pre-claim intake metadata only if unchanged.

    Uses the ETag returned by the successful claim. A newer
    version or different assignment must not be overwritten.
    """
    import json
    from azure.core import MatchConditions
    from azure.core.exceptions import (
        HttpResponseError,
        ResourceModifiedError,
        ResourceNotFoundError,
    )
    from azure.storage.blob import ContentSettings

    previous = claim.get("previous")
    assigned = claim.get("assigned")
    committed_etag = str(
        claim.get("committed_etag") or ""
    )

    if (
        not isinstance(previous, dict)
        or not isinstance(assigned, dict)
        or not committed_etag
        or not str(assigned.get("header_set_id") or "").strip()
        or previous.get("doc_id") != assigned.get("doc_id")
        or previous.get("source_sha256")
        != assigned.get("source_sha256")
    ):
        raise HTTPException(
            status_code=409,
            detail="Claim cannot be safely released.",
        )

    try:
        properties = blob_client.get_blob_properties()
        current_etag = str(
            getattr(properties, "etag", "") or ""
        )

        if current_etag != committed_etag:
            raise HTTPException(
                status_code=409,
                detail="Claim changed after assignment; no rollback.",
            )

        raw = blob_client.download_blob(
            etag=committed_etag,
            match_condition=MatchConditions.IfNotModified,
        ).readall()

        current = json.loads(raw.decode("utf-8"))

        if current != assigned:
            raise HTTPException(
                status_code=409,
                detail="Assigned metadata changed; no rollback.",
            )

        blob_client.upload_blob(
            json.dumps(
                previous, indent=2, default=str
            ).encode("utf-8"),
            overwrite=True,
            etag=committed_etag,
            match_condition=MatchConditions.IfNotModified,
            content_settings=ContentSettings(
                content_type="application/json"
            ),
        )

    except HTTPException:
        raise
    except (ResourceModifiedError, ResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Concurrent change prevented claim rollback.",
        ) from exc
    except HttpResponseError as exc:
        status = getattr(exc, "status_code", None)
        raise HTTPException(
            status_code=409 if status in (404, 409, 412) else 503,
            detail="Conditional claim rollback failed.",
        ) from exc
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Assigned metadata cannot be safely verified.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to safely release JSON claim.",
        ) from exc

    return {
        "doc_id": previous["doc_id"],
        "status": "released",
    }



def _claim_native_json_header_set_batch(
    *,
    container_client,
    base_path,
    document_ids,
    intake_documents,
    header_set_id,
    created_at,
    requested_by,
):
    """Claim native JSON intake metadata in deterministic order.

    A failed claim causes conditional rollback of all preceding
    claims. A rollback conflict is surfaced, never suppressed.
    The native JSON source files are never modified.
    """
    selected = []

    for doc_id in document_ids:
        document = intake_documents.get(doc_id)

        if not isinstance(document, dict):
            raise HTTPException(
                status_code=409,
                detail="Selected intake document is missing.",
            )

        if document.get("source_kind") != "native_json":
            continue

        canonical = (
            f"{base_path}/cyber2/intake/documents/"
            f"{doc_id}.json"
        )

        registered_path = str(
            document.get("intake_index_path") or canonical
        ).strip()

        if (
            registered_path != canonical
            or document.get("doc_id") != doc_id
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Native JSON intake identity or "
                    "index path is invalid."
                ),
            )

        selected.append((doc_id, canonical, document))

    if len({item[0] for item in selected}) != len(selected):
        raise HTTPException(
            status_code=409,
            detail="Duplicate native JSON document selection.",
        )

    acquired = []

    try:
        # Stable order avoids order-dependent contention.
        for doc_id, intake_path, document in sorted(selected):
            blob_client = container_client.get_blob_client(
                intake_path
            )

            claim = _claim_native_json_intake_blob(
                blob_client=blob_client,
                expected_document=document,
                header_set_id=header_set_id,
                created_at=created_at,
                requested_by=requested_by,
            )

            acquired.append({
                "doc_id": doc_id,
                "blob_client": blob_client,
                "claim": claim,
            })

    except Exception as exc:
        failures = []

        # Roll back all earlier successful claims in reverse order.
        for entry in reversed(acquired):
            try:
                _release_native_json_intake_claim(
                    blob_client=entry["blob_client"],
                    claim=entry["claim"],
                )
            except Exception:
                failures.append(entry["doc_id"])

        if failures:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": (
                        "Header Set claim failed and some intake "
                        "assignments could not be safely released. "
                        "Manual reconciliation is required before retry."
                    ),
                    "unreleased_doc_ids": failures,
                    "header_set_id": header_set_id,
                },
            ) from exc

        raise

    return acquired



def _transition_native_json_header_set_manifest(
    *,
    blob_client,
    header_set_id,
    document_ids,
    target_status,
    status_detail=None,
):
    """Commit an assignment outcome with an Azure ETag CAS.

    The pending manifest is the durable recovery reference.
    Header Identification must not start until the manifest
    reaches pending_header_identification.
    """
    import json
    from azure.core import MatchConditions
    from azure.core.exceptions import (
        HttpResponseError,
        ResourceModifiedError,
        ResourceNotFoundError,
    )
    from azure.storage.blob import ContentSettings

    permitted = {
        "pending_header_identification",
        "assignment_failed",
    }

    if target_status not in permitted:
        raise HTTPException(
            status_code=400,
            detail="Invalid native JSON manifest transition.",
        )

    expected_ids = list(document_ids)

    if not expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise HTTPException(
            status_code=409,
            detail="Invalid Header Set document selection.",
        )

    try:
        properties = blob_client.get_blob_properties()
        etag = str(getattr(properties, "etag", "") or "")

        if not etag:
            raise HTTPException(
                status_code=409,
                detail="Header Set manifest has no ETag.",
            )

        raw = blob_client.download_blob(
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
        ).readall()

    except HTTPException:
        raise
    except (ResourceModifiedError, ResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Header Set manifest changed during inspection.",
        ) from exc
    except HttpResponseError as exc:
        status = getattr(exc, "status_code", None)
        raise HTTPException(
            status_code=409 if status in (404, 409, 412) else 503,
            detail="Unable to read stable Header Set manifest.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to inspect Header Set manifest.",
        ) from exc

    try:
        current = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Header Set manifest is invalid.",
        ) from exc

    if not isinstance(current, dict):
        raise HTTPException(
            status_code=409,
            detail="Header Set manifest must be an object.",
        )

    current_ids = current.get("doc_ids")
    current_documents = current.get("documents")

    if (
        current.get("header_set_id") != header_set_id
        or current.get("status") != "assigning_native_json"
        or not isinstance(current_ids, list)
        or not isinstance(current_documents, list)
        or current_ids != expected_ids
        or len(current_documents) != len(expected_ids)
        or any(
            not isinstance(document, dict)
            or document.get("doc_id") != expected_ids[index]
            for index, document in enumerate(current_documents)
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Header Set identity or pending state changed.",
        )

    updated = dict(current)
    updated["status"] = target_status

    if status_detail is not None:
        if not isinstance(status_detail, dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid assignment status detail.",
            )
        updated["assignment_status_detail"] = status_detail

    try:
        result = blob_client.upload_blob(
            json.dumps(
                updated, indent=2, default=str
            ).encode("utf-8"),
            overwrite=True,
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
            content_settings=ContentSettings(
                content_type="application/json"
            ),
        )
    except ResourceModifiedError as exc:
        raise HTTPException(
            status_code=409,
            detail="Concurrent Header Set manifest modification.",
        ) from exc
    except HttpResponseError as exc:
        status = getattr(exc, "status_code", None)
        raise HTTPException(
            status_code=409 if status in (409, 412) else 503,
            detail="Conditional Header Set transition failed.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to publish Header Set state.",
        ) from exc

    return {
        "header_set_id": header_set_id,
        "status": target_status,
        "etag": (
            result.get("etag")
            if isinstance(result, dict)
            else getattr(result, "etag", None)
        ),
    }


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
    admin: User = Depends(require_admin),
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

    require_scoped_project_access(
        admin, workspace, client, project
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


    # STEP 554: NATIVE JSON ASSIGNMENT GUARD
    # Reject already assigned native JSON before creating a new
    # Header Set or writing project metadata.
    existing_json_assignments = []

    for selected_doc_id in requested_doc_ids:
        selected_source = intake_documents[selected_doc_id]

        if selected_source.get("source_kind") != "native_json":
            continue

        assigned_set = str(
            selected_source.get("header_set_id") or ""
        ).strip()

        if assigned_set:
            existing_json_assignments.append({
                "doc_id": selected_doc_id,
                "header_set_id": assigned_set,
            })

    if existing_json_assignments:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Native JSON is already assigned to Header "
                    "& Schema Mapping. Open its existing Header Set."
                ),
                "existing_assignments": existing_json_assignments,
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


        if source.get("source_kind") == "native_json":
            doc_id_checked = str(source.get("doc_id") or "")
            source_path_checked = str(
                source.get("source_native_path") or ""
            )
            source_hash_checked = str(
                source.get("source_sha256") or ""
            ).lower()

            expected_source_prefix = (
                f"{base_path}/source/native/{doc_id}."
            )

            extension = (
                source_path_checked.rsplit(".", 1)[-1].lower()
            )

            if (
                not re.fullmatch(
                    r"[A-Za-z0-9_-]{1,128}", doc_id_checked
                )
                or doc_id_checked != doc_id
                or not source_path_checked.startswith(
                    expected_source_prefix
                )
                or extension not in {"json", "jsonl", "ndjson"}
                or not re.fullmatch(
                    r"[0-9a-f]{64}", source_hash_checked
                )
                or bool(source.get("source_csv_path"))
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Native JSON intake identity is invalid.",
                )

            try:
                source_length = int(source["source_bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Native JSON source size is invalid.",
                ) from exc

            # The current verified preview supports at most 4 MiB.
            # Larger native files remain intact but cannot enter
            # this bounded mapping flow until it is expanded safely.
            if not 0 < source_length <= 4 * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Native JSON exceeds the current bounded "
                        "header discovery limit."
                    ),
                )

        header_set_documents.append(
            {
                "doc_id": doc_id,

                # Source format identity; original CSV path remains unchanged.
                "source_kind": (
                    source.get("source_kind") or "csv"
                ),
                "source_native_path": (
                    source.get("source_native_path") or ""
                ),
                "source_sha256": (
                    source.get("source_sha256") or ""
                ),
                "source_bytes": (
                    source.get("source_bytes")
                ),
                "source_format": (
                    source.get("source_format") or ""
                ),
                "source_profile": (
                    source.get("source_profile") or ""
                ),

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
    
    #
    # Advance selected Intake documents to
    # Header & Schema Mapping.
    #
    for doc_id in requested_doc_ids:
        intake_document = dict(
            intake_documents[
                doc_id
            ]
        )

        intake_document[
            "header_set_id"
        ] = header_set_id

        intake_document[
            "cyber2_stage"
        ] = "header_schema_mapping"

        intake_document[
            "header_set_status"
        ] = "assigned"

        intake_document[
            "sent_to_header_mapping_at"
        ] = created_at

        intake_document[
            "sent_to_header_mapping_by"
        ] = str(
            request.requested_by
            or ""
        ).strip()

        intake_path = str(
            intake_document.get(
                "intake_index_path"
            )
            or (
                f"{base_path}/cyber2/"
                f"intake/documents/"
                f"{doc_id}.json"
            )
        )

        _write_processing_json_blob(
            blob_path=intake_path,
            payload=intake_document,
            overwrite=True,
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
    admin: User = Depends(require_admin),
) -> dict[str, Any]:

    require_scoped_project_access(
        admin, workspace, client, project
    )

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