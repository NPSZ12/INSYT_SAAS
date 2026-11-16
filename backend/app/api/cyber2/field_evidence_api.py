"""Read-only, scoped Cyber2 RAW field-evidence document lookup.

This endpoint never accepts client-provided RAW UCIDs or sends original field
values. A later, separately audited source-open operation must enforce its own
project and sensitive-document permissions.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.processing_center_azure import _processing_container_client, _project_base_path
from app.services.authorization import (
    PERMISSION_REVIEW,
    require_permission,
    require_scoped_project_access,
)
from app.services.security import get_current_user
from app.services.cyber2.azure_membership_store import AzureBlobMembershipStore
from app.services.cyber2.entity_membership import MembershipError, approved_entity_ucids
from app.services.cyber2.field_evidence import FieldEvidenceError, find_field_evidence
from app.services.cyber2.membership_persistence import MembershipConflict, load_registry, registry_path
from app.api.entities import load_cyber2_raw_capture_records

router = APIRouter(prefix="/api", tags=["cyber2-field-evidence"])


@router.get("/{workspace}/cyber2/entities/{entity_id}/field-evidence")
def get_cyber2_entity_field_evidence(
    workspace: Literal["capture", "discovery"],
    entity_id: str,
    client: str = Query(..., min_length=1),
    project: str = Query(..., min_length=1),
    field: str = Query(..., min_length=1),
    current_user=Depends(get_current_user),
) -> dict:
    """Return only document references proving a selected field for an approved entity.

    No original values are returned, and no entity membership is inferred.
    This route does not create or mutate a registry or any RAW document.
    """
    # Crucial: authorize *before* constructing a storage client or loading RAW.
    require_scoped_project_access(current_user, workspace, client, project)
    require_permission(current_user, PERMISSION_REVIEW)

    base_path = _project_base_path(workspace=workspace, client=client, project=project)
    path = registry_path(base_path=base_path)
    store = AzureBlobMembershipStore(_processing_container_client())
    try:
        registry, _etag = load_registry(
            store, path=path, workspace=workspace, client=client, project=project
        )
        raw_ucids = approved_entity_ucids(registry, entity_id=entity_id)
    except MembershipConflict as exc:
        raise HTTPException(status_code=409, detail="Membership changed; reload and retry") from exc
    except MembershipError as exc:
        # Do not reveal registry contents or approval status.
        raise HTTPException(status_code=404, detail="Approved entity not found") from exc

    try:
        result = find_field_evidence(
            load_cyber2_raw_capture_records(workspace, client, project),
            entity_raw_ucids=raw_ucids,
            field=field,
        )
    except FieldEvidenceError as exc:
        raise HTTPException(status_code=409, detail="RAW evidence linkage is incomplete or invalid") from exc

    # Explicit allowlist. Never return original_value, unmasked identifiers,
    # raw blob URLs, storage account names or untrusted native source paths.
    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "entity_id": entity_id,
        "field": result["field"],
        "entity_raw_record_count": result["entity_raw_record_count"],
        "matching_document_count": result["matching_document_count"],
        "matching_occurrence_count": result["matching_occurrence_count"],
        "documents": [
            {
                "source_doc_id": d["source_doc_id"],
                "occurrences": [
                    {
                        "raw_ucid": o["raw_ucid"],
                        "source_record_id": o["source_record_id"],
                        "source_field": o["source_field"],
                        "source_pointer": o["source_pointer"],
                        "source_row_number": o["source_row_number"],
                    }
                    for o in d["occurrences"]
                ],
            }
            for d in result["documents"]
        ],
    }
