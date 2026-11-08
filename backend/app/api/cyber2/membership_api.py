"""Authenticated Capture/Discovery Cyber2 membership mutation API.

Uses existing project storage, immutable RAW Capture, and ETag conditional writes.
No inference of identity, no source data returned, no Azure provisioning.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.entities import load_cyber2_raw_capture_records
from app.api.processing_center_azure import _processing_container_client, _project_base_path
from app.services.authorization import (
    PERMISSION_REVIEW, require_permission, require_scoped_project_access,
)
from app.services.security import get_current_user, require_admin
from app.services.cyber2.azure_membership_store import AzureBlobMembershipStore
from app.services.cyber2.entity_membership import (
    MembershipError, merge_entities, register_entity, reverse_last_merge,
)
from app.services.cyber2.membership_approval import approve_entity
from app.services.cyber2.membership_persistence import (
    MembershipConflict, MembershipError as PersistenceMembershipError, load_registry, registry_path, update_registry,
)

router = APIRouter(prefix="/api", tags=["cyber2-entity-membership"])
Workspace = Literal["capture", "discovery"]


class ScopeBody(BaseModel):
    client: str = Field(min_length=1)
    project: str = Field(min_length=1)
    expected_revision: int | None = Field(default=None, ge=0)


class RegisterBody(ScopeBody):
    entity_id: str = Field(min_length=1)
    raw_ucids: list[str] = Field(min_length=1)


class ApproveBody(ScopeBody):
    entity_id: str = Field(min_length=1)
    note: str = ""


class MergeBody(ScopeBody):
    target_entity_id: str = Field(min_length=1)
    source_entity_ids: list[str] = Field(min_length=1)
    note: str = ""


class ExactDedupePreviewBody(BaseModel):
    client: str = Field(min_length=1)
    project: str = Field(min_length=1)
    header_set_id: str = Field(min_length=1)
    merge_index: list[str] = Field(min_length=1)

class ReverseBody(ScopeBody):
    pass


def _actor(current_user) -> str:
    # Server-derived; never trust a caller-supplied reviewer/actor name.
    username = str(getattr(current_user, "username", "") or "").strip()
    if not username:
        raise HTTPException(status_code=403, detail="Authenticated reviewer identity required")
    return username


def _known_raw_ids(workspace: Workspace, client: str, project: str) -> list[str]:
    records = load_cyber2_raw_capture_records(workspace, client, project)
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=409, detail="RAW Capture population is unavailable")
    ucids = [str(r.get("ucid") or "").strip() for r in records if isinstance(r, dict)]
    if len(ucids) != len(records) or not all(ucids) or len(set(ucids)) != len(ucids):
        raise HTTPException(status_code=409, detail="RAW Capture identity inventory is incomplete")
    return ucids


def _operate(workspace: Workspace, body: ScopeBody, current_user, mutate, *, require_raw: bool):
    require_scoped_project_access(current_user, workspace, body.client, body.project)
    require_permission(current_user, PERMISSION_REVIEW)
    actor = _actor(current_user)
    # Approval and merge operations are restricted to existing admin roles.
    require_admin(current_user)
    known = _known_raw_ids(workspace, body.client, body.project) if require_raw else None
    path = registry_path(base_path=_project_base_path(
        workspace=workspace, client=body.client, project=body.project
    ))
    store = AzureBlobMembershipStore(_processing_container_client())

    def transform(registry):
        if body.expected_revision is not None and registry["revision"] != body.expected_revision:
            raise MembershipConflict("Stale membership revision")
        return mutate(registry, actor, known)

    try:
        result, _etag = update_registry(
            store, path=path, workspace=workspace, client=body.client,
            project=body.project, mutate=transform,
        )
    except MembershipConflict as exc:
        raise HTTPException(status_code=409, detail="Membership changed; reload and reconcile") from exc
    except MembershipError as exc:
        raise HTTPException(status_code=409, detail="Invalid or conflicting membership operation") from exc
    # Deliberately no RAW UCIDs, values, source paths or audit snapshots in response.
    return {"status": "saved", "workspace": workspace, "client": body.client,
            "project": body.project, "revision": result["revision"],
            "entity_count": len(result["entities"])}


@router.post("/{workspace}/cyber2/entity-membership/register")
def register_cyber2_membership(
    workspace: Workspace, body: RegisterBody, current_user=Depends(get_current_user),
) -> dict:
    """Register manually selected RAW members as pending, never auto-approved."""
    return _operate(workspace, body, current_user,
        lambda registry, actor, known: register_entity(
            registry, entity_id=body.entity_id, raw_ucids=body.raw_ucids,
            known_raw_ucids=known, actor=actor, status="pending"), require_raw=True)


@router.post("/{workspace}/cyber2/entity-membership/approve")
def approve_cyber2_membership(
    workspace: Workspace, body: ApproveBody, current_user=Depends(get_current_user),
) -> dict:
    return _operate(workspace, body, current_user,
        lambda registry, actor, known: approve_entity(
            registry, entity_id=body.entity_id, actor=actor, note=body.note),
        require_raw=True)


@router.post("/{workspace}/cyber2/entity-membership/merge")
def merge_cyber2_membership(
    workspace: Workspace, body: MergeBody, current_user=Depends(get_current_user),
) -> dict:
    return _operate(workspace, body, current_user,
        lambda registry, actor, known: merge_entities(
            registry, target_entity_id=body.target_entity_id,
            source_entity_ids=body.source_entity_ids, actor=actor,
            known_raw_ucids=known, note=body.note), require_raw=True)


@router.post("/{workspace}/cyber2/entity-membership/reverse-last-merge")
def reverse_cyber2_last_merge(
    workspace: Workspace, body: ReverseBody, current_user=Depends(get_current_user),
) -> dict:
    return _operate(workspace, body, current_user,
        lambda registry, actor, known: reverse_last_merge(registry, actor=actor),
        require_raw=True)


@router.get("/{workspace}/cyber2/entity-membership")
def list_cyber2_memberships(
    workspace: Workspace,
    client: str = Query(min_length=1),
    project: str = Query(min_length=1),
    current_user=Depends(get_current_user),
) -> dict:
    """Read current scoped memberships without exposing source values or audit history."""
    require_scoped_project_access(
        current_user, workspace, client, project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    known = set(_known_raw_ids(workspace, client, project))
    path = registry_path(
        base_path=_project_base_path(
            workspace=workspace, client=client, project=project
        )
    )
    store = AzureBlobMembershipStore(_processing_container_client())

    try:
        registry, _etag = load_registry(
            store,
            path=path,
            workspace=workspace,
            client=client,
            project=project,
        )
    except MembershipConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Membership registry changed; reload",
        ) from exc
    except (MembershipError, PersistenceMembershipError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Membership registry is invalid",
        ) from exc

    entities = []
    for entity_id, entry in sorted(registry["entities"].items()):
        raw_ucids = entry["raw_ucids"]
        if any(ucid not in known for ucid in raw_ucids):
            raise HTTPException(
                status_code=409,
                detail="Membership refers to unavailable RAW evidence",
            )
        entities.append({
            "entity_id": entity_id,
            "status": entry["status"],
            "raw_ucids": list(raw_ucids),
            "raw_count": len(raw_ucids),
        })

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "revision": registry["revision"],
        "entity_count": len(entities),
        "raw_inventory_count": len(known),
        "entities": entities,
    }


def _load_cyber2_merge_processing_set(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
    approved_mapping: dict,
) -> dict:
    """Read validated C2 Mapped CSV records; never write RAW."""

    from app.services.cyber2.mapped_processing_set import (
        MappedProcessingSetError,
        load_cyber2_mapped_processing_set,
    )

    try:
        return load_cyber2_mapped_processing_set(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
            approved_mapping=approved_mapping,
        )
    except MappedProcessingSetError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post("/{workspace}/cyber2/merge-dedupe/preview")
def preview_cyber2_exact_dedupe(
    workspace: Workspace,
    body: ExactDedupePreviewBody,
    current_user=Depends(get_current_user),
) -> dict:
    """Preview approved, project-scoped exact matches without writing."""

    require_scoped_project_access(
        current_user,
        workspace,
        body.client,
        body.project,
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    # Reuse INSYT's existing approved mapping and RAW services.
    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )
    from app.services.cyber2.exact_dedupe import ExactDedupeError
    from app.services.cyber2.header_set_dedupe import (
        preview_header_set_dedupe,
    )

    path = _approved_mapping_path(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
    )

    mapping = _load_required_json(
        path,
        description="Approved Cyber2 Header Mapping",
    )

    # Never accept a mapping belonging to another project or workspace.
    if any(
        mapping.get(key) != expected
        for key, expected in (
            ("workspace", workspace),
            ("client", body.client),
            ("project", body.project),
            ("header_set_id", body.header_set_id),
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Header mapping scope mismatch",
        )

    if mapping.get("status") != "approved":
        raise HTTPException(
            status_code=409,
            detail="Header mapping is not approved",
        )

    headers = (
        mapping.get("canonical_column_order")
        or mapping.get("protocol_headers")
    )

    if not isinstance(headers, list):
        raise HTTPException(
            status_code=409,
            detail="Approved protocol headers unavailable",
        )

    # Conflict fields are derived server-side from approved headers.
    # This is initial preview screening, NOT merge authorization.
    strong_identifier_names = {
        "ssn",
        "social security number",
        "social security number (ssn)",
        "social security #",
        "dob",
        "date of birth",
        "date of birth (dob)",
        "birth date",
    }

    conflict_headers = [
        field
        for field in headers
        if isinstance(field, str)
        and field.strip().casefold() in strong_identifier_names
    ]

    processing_set = _load_cyber2_merge_processing_set(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
        approved_mapping=mapping,
    )
    records = processing_set["records"]

    if not isinstance(records, list) or not records:
        raise HTTPException(
            status_code=409,
            detail="Mapped CSV processing population unavailable",
        )

    try:
        result = preview_header_set_dedupe(
            header_set_id=body.header_set_id,
            approved_mapping=mapping,
            raw_records=records,
            merge_index=body.merge_index,
            conflict_headers=conflict_headers,
        )
    except ExactDedupeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    # No RAW values or source file contents returned.
    # No identity membership changes or persistence.
    return {
        "status": "preview",
        "workspace": workspace,
        "client": body.client,
        "project": body.project,
        "conflict_headers_checked": conflict_headers,
        "execution_enabled": False,
        **result,
    }


@router.post("/{workspace}/cyber2/merge-dedupe/spreadsheet-preview")
def preview_cyber2_spreadsheet(
    workspace: str,
    body: ExactDedupePreviewBody,
    current_user=Depends(get_current_user),
):
    """Read-only, authorized spreadsheet of original approved RAW values."""
    from fastapi.responses import JSONResponse
    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )

    # Reuse the production exact-match endpoint's existing
    # project access, permission, admin, and mapping validation.
    summary = preview_cyber2_exact_dedupe(
        workspace=workspace,
        body=body,
        current_user=current_user,
    )

    path = _approved_mapping_path(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
    )
    mapping = _load_required_json(
        path,
        description="Approved Cyber2 Header Mapping",
    )

    headers = (
        mapping.get("canonical_column_order")
        or mapping.get("protocol_headers")
    )
    if not isinstance(headers, list) or not all(
        isinstance(field, str) and field.strip()
        for field in headers
    ):
        raise HTTPException(
            status_code=409,
            detail="Approved spreadsheet columns unavailable",
        )

    doc_ids = {
        str(doc["doc_id"])
        for doc in mapping.get("documents", [])
        if isinstance(doc, dict) and doc.get("doc_id")
    }

    classifications = {}

    def register(members, label, group_number=None):
        for member in members:
            ucid = str(member.get("ucid") or "")
            if not ucid or ucid in classifications:
                raise HTTPException(
                    status_code=409,
                    detail="Invalid spreadsheet membership",
                )
            classifications[ucid] = (label, group_number)

    for number, group in enumerate(summary["groups"], start=1):
        register(group["members"], "exact_duplicate", number)

    for number, group in enumerate(summary["conflicts"], start=1):
        register(group["members"], "qc_conflict", number)

    register(summary["unmatched"], "unmatched")
    register(summary["excluded"], "excluded")

    if len(classifications) > 5000:
        raise HTTPException(
            status_code=409,
            detail="Spreadsheet exceeds current 5000-row limit",
        )

    processing_set = _load_cyber2_merge_processing_set(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
        approved_mapping=mapping,
    )
    records = processing_set["records"]

    headers = processing_set["output_headers"]

    rows = []
    seen = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        ucid = str(record.get("ucid") or "")
        if ucid not in classifications:
            continue

        doc_id = str(record.get("doc_id") or "")
        provenance = record.get("provenance") or {}
        metadata = record.get("metadata") or {}

        if (
            ucid in seen
            or doc_id not in doc_ids
            or not isinstance(provenance, dict)
            or provenance.get("header_set_id") != body.header_set_id
            or not isinstance(metadata, dict)
        ):
            raise HTTPException(
                status_code=409,
                detail="Spreadsheet source validation failed",
            )

        seen.add(ucid)
        classification, group_number = classifications[ucid]

        rows.append({
            "ucid": ucid,
            "doc_id": doc_id,
            "classification": classification,
            "group_number": group_number,
            "cells": {
                field: metadata.get(field)
                for field in headers
            },
            "source": {
                "header_set_id": body.header_set_id,
                "source_row_number": provenance.get(
                    "source_row_number"
                ),
            },
        })

    if (
        seen != set(classifications)
        or len(rows) != summary["raw_record_count"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Spreadsheet source population incomplete",
        )

    from app.services.cyber2.merge_snapshot import (
        MergeSnapshotError,
        merge_snapshot_fingerprint,
    )

    try:
        snapshot_fingerprint = merge_snapshot_fingerprint(
            approved_mapping=mapping,
            merge_index=body.merge_index,
            raw_records=records,
        )
    except MergeSnapshotError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return JSONResponse(
        content={
            "snapshot_fingerprint": snapshot_fingerprint,
            "status": "spreadsheet_preview",
            "header_set_id": body.header_set_id,
            "merge_index": body.merge_index,
            "preview_columns": headers,
            "preview_rows": rows,
            "preview_row_count": len(rows),
            "preview_rows_complete": True,
            "execution_enabled": False,
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _cyber2_execution_actor(current_user):
    """Identify the authenticated person performing execution."""
    keys = ("oid", "sub", "id", "user_id", "email", "username")

    for key in keys:
        value = (
            current_user.get(key)
            if isinstance(current_user, dict)
            else getattr(current_user, key, None)
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)

    raise HTTPException(
        status_code=403,
        detail="Authenticated execution identity unavailable",
    )


def _cyber2_merge_store_for(workspace, client, project):
    """Reuse INSYT's established processing container and project path."""
    from app.services.cyber2.merge_set_store import Cyber2MergeSetStore

    return Cyber2MergeSetStore(
        _processing_container_client(),
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        ),
    )


class MergeExecuteBody(ExactDedupePreviewBody):
    snapshot_fingerprint: str
    request_id: str


@router.post("/{workspace}/cyber2/merge-dedupe/execute")
def execute_cyber2_exact_merge(
    workspace: str,
    body: MergeExecuteBody,
    current_user=Depends(get_current_user),
):
    """Recalculate exact groups and save a separate derived merge set."""
    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )
    from app.services.cyber2.exact_dedupe import ExactDedupeError
    from app.services.cyber2.header_set_dedupe import (
        preview_header_set_dedupe,
    )
    from app.services.cyber2.merge_execution import (
        MergeExecutionError,
        build_merged_working_population,
    )
    from app.services.cyber2.merge_set_store import (
        MergeSetConflict,
        MergeSetStoreError,
    )

    # Existing preview enforces scoped project access, review permission,
    # admin authorization, approved mapping, and Merge Index validation.
    # Its grouping output is recomputed below from one fresh RAW snapshot.
    preview_cyber2_exact_dedupe(
        workspace=workspace,
        body=body,
        current_user=current_user,
    )

    actor = _cyber2_execution_actor(current_user)

    mapping_path = _approved_mapping_path(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
    )

    mapping = _load_required_json(
        mapping_path,
        description="Approved Cyber2 Header Mapping",
    )

    if (
        not isinstance(mapping, dict)
        or mapping.get("status") != "approved"
        or any(
            mapping.get(key) != value
            for key, value in (
                ("workspace", workspace),
                ("client", body.client),
                ("project", body.project),
                ("header_set_id", body.header_set_id),
            )
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Approved merge mapping changed or is invalid",
        )

    headers = (
        mapping.get("canonical_column_order")
        or mapping.get("protocol_headers")
    )

    documents = mapping.get("documents")

    if (
        not isinstance(headers, list)
        or not headers
        or not all(isinstance(h, str) and h.strip() for h in headers)
        or not isinstance(documents, list)
        or not documents
    ):
        raise HTTPException(
            status_code=409,
            detail="Incomplete approved mapping",
        )

    doc_ids = [
        str(document.get("doc_id") or "")
        for document in documents
        if isinstance(document, dict)
    ]

    if (
        len(doc_ids) != len(documents)
        or not all(doc_ids)
        or len(set(doc_ids)) != len(doc_ids)
    ):
        raise HTTPException(
            status_code=409,
            detail="Invalid approved source documents",
        )

    # Conflict screening is derived on the server, never from the browser.
    strong_names = {
        "ssn",
        "social security number",
        "social security number (ssn)",
        "social security #",
        "dob",
        "date of birth",
        "date of birth (dob)",
        "birth date",
    }

    conflict_headers = [
        field
        for field in headers
        if field.strip().casefold() in strong_names
    ]

    processing_set = _load_cyber2_merge_processing_set(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=body.header_set_id,
        approved_mapping=mapping,
    )
    records = processing_set["records"]

    headers = processing_set["output_headers"]

    if not isinstance(records, list) or not records:
        raise HTTPException(
            status_code=409,
            detail="Mapped CSV processing population unavailable",
        )

    try:
        # Never trust browser-submitted group membership.
        fresh_preview = preview_header_set_dedupe(
            header_set_id=body.header_set_id,
            approved_mapping=mapping,
            raw_records=records,
            merge_index=body.merge_index,
            conflict_headers=conflict_headers,
        )

        from app.services.cyber2.merge_snapshot import (
            MergeSnapshotError,
            merge_snapshot_fingerprint,
        )

        try:
            current_fingerprint = merge_snapshot_fingerprint(
                approved_mapping=mapping,
                merge_index=body.merge_index,
                raw_records=records,
            )
        except MergeSnapshotError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        if body.snapshot_fingerprint != current_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Merge preview is stale. Refresh the spreadsheet.",
            )

        derived = build_merged_working_population(
            header_set_id=body.header_set_id,
            approved_headers=headers,
            approved_doc_ids=doc_ids,
            merge_index=body.merge_index,
            raw_records=records,
            preview=fresh_preview,
            conflict_headers=conflict_headers,
        )

        store = _cyber2_merge_store_for(
            workspace,
            body.client,
            body.project,
        )

        saved = store.save(
            derived=derived,
            workspace=workspace,
            client=body.client,
            project=body.project,
            approved_mapping_path=mapping_path,
            executed_by=actor,
            request_id=body.request_id,
            snapshot_fingerprint=current_fingerprint,
        )

    except (
        ExactDedupeError,
        MergeExecutionError,
        MergeSetConflict,
        MergeSetStoreError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    # No actual captured values are exposed in the execution receipt.
    return {
        "status": "completed",
        "execution_type": "cyber2_exact_merge",
        "execution_enabled": True,
        **saved,
    }


@router.get("/{workspace}/cyber2/merge-dedupe/completed")
def list_cyber2_completed_merge_sets(
    workspace: str,
    client: str = Query(...),
    project: str = Query(...),
    current_user=Depends(get_current_user),
):
    """List completed Cyber2 merge sets in the authorized project."""
    from fastapi.responses import JSONResponse
    from app.services.cyber2.merge_set_store import MergeSetStoreError

    require_scoped_project_access(
        current_user,
        workspace,
        client,
        project,
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    store = _cyber2_merge_store_for(
        workspace,
        client,
        project,
    )

    try:
        merge_sets = store.list_completed()
    except MergeSetStoreError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return JSONResponse(
        content={
            "status": "ok",
            "workspace": workspace,
            "client": client,
            "project": project,
            "count": len(merge_sets),
            "merge_sets": merge_sets,
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
        },
    )
