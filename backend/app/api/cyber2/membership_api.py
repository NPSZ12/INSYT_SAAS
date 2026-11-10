"""Authenticated Capture/Discovery Cyber2 membership mutation API.

Uses existing project storage, immutable RAW Capture, and ETag conditional writes.
No inference of identity, no source data returned, no Azure provisioning.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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

class IterativePreviewBody(BaseModel):
    client: str = Field(min_length=1)
    project: str = Field(min_length=1)
    parent_merge_set_id: str = Field(min_length=1)
    merge_index: list[str] = Field(min_length=1)


@router.post("/{workspace}/cyber2/merge-dedupe/iterative-preview")
def preview_cyber2_iterative_merge(
    workspace: Workspace,
    body: IterativePreviewBody,
    current_user=Depends(get_current_user),
):
    """Preview another pass against a verified completed merge set.

    No writes. Source values are never included in the response.
    """
    import hashlib
    import json
    import re

    from app.services.cyber2.iterative_merge_input import (
        IterativeMergeInputError,
    )
    from app.services.cyber2.iterative_merge_preview import (
        preview_iterative_merge,
    )
    from app.services.cyber2.merge_set_store import (
        MergeSetStoreError,
    )

    require_scoped_project_access(
        current_user, workspace, body.client, body.project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    parent_id = body.parent_merge_set_id

    if not re.fullmatch(r"MSET-[0-9A-F]{32}", parent_id):
        raise HTTPException(
            status_code=409, detail="Invalid parent Merge Set ID"
        )

    store = _cyber2_merge_store_for(
        workspace, body.client, body.project
    )

    try:
        # load() verifies the saved SHA-256 integrity digest.
        parent = store.load(parent_id)

        if any(
            parent.get(field) != value
            for field, value in (
                ("workspace", workspace),
                ("client", body.client),
                ("project", body.project),
                ("merge_set_id", parent_id),
                ("status", "completed"),
            )
        ):
            raise IterativeMergeInputError(
                "Completed merge-set scope mismatch"
            )

        parent_digest = parent.get("integrity_sha256")

        if not isinstance(parent_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", parent_digest
        ):
            raise IterativeMergeInputError(
                "Parent snapshot integrity unavailable"
            )

        headers = parent.get("approved_headers")

        if not isinstance(headers, list):
            raise IterativeMergeInputError(
                "Approved headers unavailable"
            )

        # Reuse approved strong-identifier policy, including _2 columns.
        from app.services.cyber2.iterative_conflict_policy import (
            iterative_conflict_headers,
        )

        try:
            conflict_headers = iterative_conflict_headers(headers)
        except ValueError as exc:
            raise IterativeMergeInputError(str(exc)) from exc

        preview = preview_iterative_merge(
            parent, body.merge_index, conflict_headers
        )

        fingerprint_payload = {
            "parent_merge_set_id": parent_id,
            "parent_integrity_sha256": parent_digest,
            "merge_index": body.merge_index,
            "conflict_headers": conflict_headers,
            "preview_version": 1,
        }

        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    except (MergeSetStoreError, IterativeMergeInputError) as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    return {
        **preview,
        "workspace": workspace,
        "client": body.client,
        "project": body.project,
        "snapshot_fingerprint": fingerprint,
        "conflict_headers_checked": conflict_headers,
        "execution_enabled": False,
    }

class IterativeExecuteBody(IterativePreviewBody):
    snapshot_fingerprint: str = Field(min_length=64, max_length=64)
    request_id: str = Field(min_length=1)


@router.post("/{workspace}/cyber2/merge-dedupe/iterative-execute")
def execute_cyber2_iterative_merge(
    workspace: Workspace,
    body: IterativeExecuteBody,
    current_user=Depends(get_current_user),
):
    """Save one immutable child of an authorized completed merge set."""
    import hashlib
    import json
    import re

    from app.services.cyber2.iterative_merge_execution import (
        build_iterative_child,
    )
    from app.services.cyber2.iterative_merge_input import (
        IterativeMergeInputError,
    )
    from app.services.cyber2.merge_set_store import (
        MergeSetConflict,
        MergeSetStoreError,
    )

    # Reuse the preview endpoint's authorization, validation,
    # integrity-verified parent retrieval, and conflict policy.
    preview = preview_cyber2_iterative_merge(
        workspace=workspace,
        body=body,
        current_user=current_user,
    )

    if not re.fullmatch(
        r"[0-9a-f]{64}", body.snapshot_fingerprint
    ):
        raise HTTPException(
            status_code=409,
            detail="Invalid iterative snapshot fingerprint",
        )

    if body.snapshot_fingerprint != preview["snapshot_fingerprint"]:
        raise HTTPException(
            status_code=409,
            detail="Iterative preview is stale. Refresh preview.",
        )

    store = _cyber2_merge_store_for(
        workspace, body.client, body.project
    )

    try:
        # Recheck the immutable parent for the execution read.
        parent = store.load(body.parent_merge_set_id)

        if any(
            parent.get(field) != value
            for field, value in (
                ("workspace", workspace),
                ("client", body.client),
                ("project", body.project),
                ("merge_set_id", body.parent_merge_set_id),
                ("status", "completed"),
            )
        ):
            raise IterativeMergeInputError(
                "Execution parent scope mismatch"
            )

        digest = parent.get("integrity_sha256")

        if not isinstance(digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            raise IterativeMergeInputError(
                "Execution parent integrity unavailable"
            )

        payload = {
            "parent_merge_set_id": body.parent_merge_set_id,
            "parent_integrity_sha256": digest,
            "merge_index": body.merge_index,
            "conflict_headers": preview[
                "conflict_headers_checked"
            ],
            "preview_version": 1,
        }

        execution_fingerprint = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        if execution_fingerprint != body.snapshot_fingerprint:
            raise IterativeMergeInputError(
                "Parent changed after preview. Refresh preview."
            )

        derived = build_iterative_child(
            parent,
            body.merge_index,
            preview["conflict_headers_checked"],
        )

        mapping_path = parent.get("approved_mapping_path")

        if not isinstance(mapping_path, str) or not mapping_path:
            raise IterativeMergeInputError(
                "Parent approved mapping path unavailable"
            )

        saved = store.save(
            derived=derived,
            workspace=workspace,
            client=body.client,
            project=body.project,
            approved_mapping_path=mapping_path,
            executed_by=_cyber2_execution_actor(current_user),
            request_id=body.request_id,
            snapshot_fingerprint=execution_fingerprint,
        )

    except (
        IterativeMergeInputError,
        MergeSetConflict,
        MergeSetStoreError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "status": "completed",
        "execution_type": "cyber2_iterative_exact_merge",
        "parent_merge_set_id": body.parent_merge_set_id,
        "pass_number": derived["pass_number"],
        "input_working_record_count": (
            derived["input_working_record_count"]
        ),
        "conflict_group_count": derived["conflict_group_count"],
        **saved,
    }

@router.post("/{workspace}/cyber2/merge-dedupe/iterative-spreadsheet")
def preview_cyber2_iterative_spreadsheet(
    workspace: Workspace,
    body: IterativePreviewBody,
    current_user=Depends(get_current_user),
):
    """Authorized read-only working-record spreadsheet and lineage."""
    import hashlib
    import json
    from copy import deepcopy

    from fastapi.responses import JSONResponse
    from app.services.cyber2.iterative_merge_input import (
        IterativeMergeInputError,
        prepare_iterative_candidates,
    )
    from app.services.cyber2.merge_set_store import MergeSetStoreError

    # This performs project authorization and loads the verified
    # parent before any captured values are accessed.
    summary = preview_cyber2_iterative_merge(
        workspace=workspace,
        body=body,
        current_user=current_user,
    )

    store = _cyber2_merge_store_for(
        workspace, body.client, body.project
    )

    try:
        parent = store.load(body.parent_merge_set_id)

        if any(
            parent.get(field) != value
            for field, value in (
                ("workspace", workspace),
                ("client", body.client),
                ("project", body.project),
                ("merge_set_id", body.parent_merge_set_id),
                ("status", "completed"),
            )
        ):
            raise IterativeMergeInputError(
                "Spreadsheet parent scope mismatch"
            )

        # Reconstruct the preview fingerprint against this
        # second read, preventing inconsistent parent snapshots.
        fingerprint_data = {
            "parent_merge_set_id": body.parent_merge_set_id,
            "parent_integrity_sha256": parent.get(
                "integrity_sha256"
            ),
            "merge_index": body.merge_index,
            "conflict_headers": summary[
                "conflict_headers_checked"
            ],
            "preview_version": 1,
        }

        current_fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        if current_fingerprint != summary["snapshot_fingerprint"]:
            raise IterativeMergeInputError(
                "Spreadsheet parent changed during preview"
            )

        prepared = prepare_iterative_candidates(
            parent, body.merge_index
        )

        headers = parent["approved_headers"]
        records = parent["working_records"]

        if len(records) > 10000:
            raise IterativeMergeInputError(
                "Spreadsheet exceeds supported row limit"
            )

        # Each parent working record must appear exactly once
        # across the proposed classifications.
        classes = {}

        def assign(member, classification, group_number):
            working_id = member["working_record_id"]
            if working_id in classes:
                raise IterativeMergeInputError(
                    "Repeated spreadsheet working identity"
                )
            classes[working_id] = (
                classification, group_number
            )

        for number, group in enumerate(
            summary["groups"], start=1
        ):
            for member in group["members"]:
                assign(member, "exact_duplicate", number)

        for number, group in enumerate(
            summary["conflicts"], start=1
        ):
            for member in group["members"]:
                assign(member, "qc_conflict", number)

        for member in summary["unmatched"]:
            assign(member, "unmatched", None)

        for member in summary["excluded"]:
            assign(member, "excluded", None)

        if len(classes) != len(records):
            raise IterativeMergeInputError(
                "Incomplete spreadsheet classification"
            )

        rows = []

        for record in records:
            working_id = record["working_record_id"]
            classification = classes.get(working_id)

            if classification is None:
                raise IterativeMergeInputError(
                    "Unknown spreadsheet working identity"
                )

            rows.append({
                "working_record_id": working_id,
                "classification": classification[0],
                "group_number": classification[1],
                "source_ucids": deepcopy(
                    record["source_ucids"]
                ),
                "source_doc_ids": deepcopy(
                    record["source_doc_ids"]
                ),
                "cells": deepcopy(record["cells"]),
                "field_provenance": deepcopy(
                    record["field_provenance"]
                ),
            })

        if (
            len(rows) != prepared[
                "input_working_record_count"
            ]
            or len({
                row["working_record_id"] for row in rows
            }) != len(rows)
        ):
            raise IterativeMergeInputError(
                "Spreadsheet population mismatch"
            )

    except (MergeSetStoreError, IterativeMergeInputError) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return JSONResponse(
        content={
            "status": "iterative_spreadsheet_preview",
            "workspace": workspace,
            "client": body.client,
            "project": body.project,
            "header_set_id": parent["header_set_id"],
            "parent_merge_set_id": body.parent_merge_set_id,
            "merge_index": body.merge_index,
            "snapshot_fingerprint": current_fingerprint,
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

@router.get("/{workspace}/cyber2/c2/records")
def read_cyber2_c2_records(
    workspace: Workspace,
    response: Response,
    client: str = Query(min_length=1),
    project: str = Query(min_length=1),
    header_set_id: str = Query(min_length=1),
    current_user=Depends(get_current_user),
):
    """Read project-scoped C2 display rows; never return source evidence."""
    from app.services.cyber2.c2_transfer_store import (
        C2TransferStoreError,
        Cyber2C2TransferStore,
    )

    require_scoped_project_access(
        current_user, workspace, client, project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    store = Cyber2C2TransferStore(
        _processing_container_client(),
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        ),
        workspace=workspace,
        client=client,
        project=project,
    )

    try:
        snapshot = store.display(header_set_id)
    except C2TransferStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if snapshot is None:
        return {
            "status": "ok",
            "headers": [],
            "rows": [],
            "source": "cyber2_c2_transfer",
            "working_record_count": 0,
            "original_source_record_count": 0,
        }

    return {
        "status": "ok",
        **snapshot,
    }
@router.get("/{workspace}/cyber2/c2/transfer-readiness")
def inspect_cyber2_c2_transfer_readiness(
    workspace: Workspace,
    response: Response,
    client: str = Query(min_length=1),
    project: str = Query(min_length=1),
    merge_set_id: str = Query(min_length=1),
    current_user=Depends(get_current_user),
):
    """Independently verify a selected completed C2 Merge Set.

    This operation never creates an origin approval or writes C2 data.
    """
    import re

    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )
    from app.services.cyber2.merge_set_store import MergeSetStoreError
    from app.services.cyber2.c2_transfer_validation import (
        C2TransferValidationError,
        validate_c2_merge_population,
    )

    require_scoped_project_access(
        current_user, workspace, client, project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    if re.fullmatch(r"MSET-[0-9A-F]{32}", merge_set_id) is None:
        raise HTTPException(
            status_code=422, detail="Invalid Merge Set identifier"
        )

    store = _cyber2_merge_store_for(workspace, client, project)

    try:
        merge_set = store.load(merge_set_id)
        completed = store.list_completed()
    except MergeSetStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if (
        merge_set.get("status") != "completed"
        or merge_set.get("merge_set_id") != merge_set_id
        or any(
            merge_set.get(key) != value
            for key, value in (
                ("workspace", workspace),
                ("client", client),
                ("project", project),
            )
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Completed Merge Set scope mismatch",
        )

    header_set_id = merge_set.get("header_set_id")
    same_header = [
        item for item in completed
        if item.get("header_set_id") == header_set_id
        and item.get("status") == "completed"
    ]

    from app.services.cyber2.c2_merge_lineage import (
        C2MergeLineageError,
        require_complete_c2_lineage,
    )

    try:
        require_complete_c2_lineage(
            completed,
            header_set_id=header_set_id,
            merge_set_id=merge_set_id,
        )
    except C2MergeLineageError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    # Verify the SHA-256 integrity of every saved ancestor,
    # not only the completed-set listing relationships.
    from app.services.cyber2.c2_stored_lineage import (
        verify_c2_stored_lineage,
    )

    try:
        verify_c2_stored_lineage(
            store,
            completed,
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
            merge_set_id=merge_set_id,
        )
    except C2MergeLineageError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    mapping = _load_required_json(
        _approved_mapping_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        ),
        description="Approved Cyber2 Header Mapping",
    )

    if (
        not isinstance(mapping, dict)
        or mapping.get("status") != "approved"
        or any(
            mapping.get(key) != value
            for key, value in (
                ("workspace", workspace),
                ("client", client),
                ("project", project),
                ("header_set_id", header_set_id),
            )
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Approved Header Set scope mismatch",
        )

    processing_set = _load_cyber2_merge_processing_set(
        workspace=workspace,
        client=client,
        project=project,
        header_set_id=header_set_id,
        approved_mapping=mapping,
    )

    try:
        result = validate_c2_merge_population(
            merge_set,
            processing_set["records"],
            workspace=workspace,
            client=client,
            project=project,
        )
    except C2TransferValidationError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    return {
        "status": "source_verified_origin_pending",
        "workspace": workspace,
        "client": client,
        "project": project,
        "merge_set_id": merge_set_id,
        "header_set_id": header_set_id,
        "working_record_count": result["working_record_count"],
        "original_source_record_count":
            result["original_source_record_count"],
        "source_conservation_verified": True,
        "origin_authorized": False,
        "transfer_authorized": False,
    }

class C2OriginApprovalBody(BaseModel):
    client: str = Field(min_length=1)
    project: str = Field(min_length=1)
    merge_set_id: str = Field(min_length=1)
    reviewed_doc_ids: list[str] = Field(min_length=1)
    attested_non_ai: bool = False


@router.post("/{workspace}/cyber2/c2/approve-origin")
def approve_cyber2_c2_origin(
    workspace: Workspace,
    body: C2OriginApprovalBody,
    response: Response,
    current_user=Depends(get_current_user),
):
    """Audited administrator attestation for non-AI structured sources."""
    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )
    from app.services.cyber2.c2_origin_receipt import (
        C2OriginReceiptError,
        save_c2_origin_approval,
    )
    from app.services.cyber2.merge_set_store import MergeSetStoreError

    require_scoped_project_access(
        current_user, workspace, body.client, body.project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)
    reviewer = _cyber2_execution_actor(current_user)

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    if body.attested_non_ai is not True:
        raise HTTPException(
            status_code=422,
            detail="Explicit non-AI source review required",
        )

    # Re-run server-side source and lineage checks. Never accept
    # browser-provided readiness or origin-authorized flags.
    inspect_cyber2_c2_transfer_readiness(
        workspace=workspace,
        response=response,
        client=body.client,
        project=body.project,
        merge_set_id=body.merge_set_id,
        current_user=current_user,
    )

    merge_store = _cyber2_merge_store_for(
        workspace, body.client, body.project
    )

    try:
        merge_set = merge_store.load(body.merge_set_id)
    except MergeSetStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    mapping = _load_required_json(
        _approved_mapping_path(
            workspace=workspace,
            client=body.client,
            project=body.project,
            header_set_id=merge_set["header_set_id"],
        ),
        description="Approved Cyber2 Header Mapping",
    )

    try:
        saved = save_c2_origin_approval(
            container=_processing_container_client(),
            project_base_path=_project_base_path(
                workspace=workspace,
                client=body.client,
                project=body.project,
            ),
            merge_set=merge_set,
            approved_mapping=mapping,
            reviewed_doc_ids=body.reviewed_doc_ids,
            reviewer=reviewer,
            attested_non_ai=body.attested_non_ai,
        )
    except (C2OriginReceiptError, ValueError) as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    return saved

class C2TransferBody(BaseModel):
    client: str = Field(min_length=1)
    project: str = Field(min_length=1)
    merge_set_id: str = Field(min_length=1)


@router.post("/{workspace}/cyber2/c2/transfer")
def transfer_cyber2_merge_set_to_c2(
    workspace: Workspace,
    body: C2TransferBody,
    response: Response,
    current_user=Depends(get_current_user),
):
    """Transfer one verified, origin-approved Merge Set into C2 only."""
    import re

    from app.api.cyber2.schema_mapping import (
        _approved_mapping_path,
        _load_required_json,
    )
    from app.services.cyber2.c2_origin_receipt import (
        C2OriginReceiptError,
        _load as load_origin_blob,
        _path as origin_receipt_path,
    )
    from app.services.cyber2.c2_origin_authorization import (
        C2OriginAuthorizationError,
        require_c2_origin_authorization,
    )
    from app.services.cyber2.c2_transfer_validation import (
        C2TransferValidationError,
        validate_c2_merge_population,
    )
    from app.services.cyber2.c2_transfer_projection import (
        C2ProjectionError,
        build_c2_projection,
    )
    from app.services.cyber2.c2_transfer_store import (
        C2TransferStoreError,
        Cyber2C2TransferStore,
    )
    from app.services.cyber2.merge_set_store import (
        MergeSetStoreError,
    )

    # Permission gates precede all reads and writes.
    require_scoped_project_access(
        current_user, workspace, body.client, body.project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)
    actor = _cyber2_execution_actor(current_user)

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    if re.fullmatch(
        r"MSET-[0-9A-F]{32}", body.merge_set_id
    ) is None:
        raise HTTPException(
            status_code=422,
            detail="Invalid C2 Merge Set identifier",
        )

    # Recompute readiness on the server. This checks the completed
    # inventory, full iterative lineage, mapping and original sources.
    inspect_cyber2_c2_transfer_readiness(
        workspace=workspace,
        response=response,
        client=body.client,
        project=body.project,
        merge_set_id=body.merge_set_id,
        current_user=current_user,
    )

    merge_store = _cyber2_merge_store_for(
        workspace, body.client, body.project
    )

    try:
        # load() verifies the saved Merge Set SHA-256 digest.
        merge_set = merge_store.load(body.merge_set_id)
    except MergeSetStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if (
        merge_set.get("status") != "completed"
        or merge_set.get("merge_set_id") != body.merge_set_id
        or any(
            merge_set.get(key) != value
            for key, value in (
                ("workspace", workspace),
                ("client", body.client),
                ("project", body.project),
            )
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="C2 Merge Set scope mismatch",
        )

    header_set_id = merge_set.get("header_set_id")

    mapping = _load_required_json(
        _approved_mapping_path(
            workspace=workspace,
            client=body.client,
            project=body.project,
            header_set_id=header_set_id,
        ),
        description="Approved Cyber2 Header Mapping",
    )

    if (
        not isinstance(mapping, dict)
        or mapping.get("status") != "approved"
        or any(
            mapping.get(key) != merge_set.get(key)
            for key in (
                "workspace", "client",
                "project", "header_set_id",
            )
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="C2 approved mapping scope mismatch",
        )

    base_path = _project_base_path(
        workspace=workspace,
        client=body.client,
        project=body.project,
    )
    container = _processing_container_client()

    # The approval must already exist. Never create an approval
    # automatically during transfer.
    receipt_blob = container.get_blob_client(
        origin_receipt_path(base_path, body.merge_set_id)
    )

    try:
        receipt = load_origin_blob(receipt_blob)
    except C2OriginReceiptError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if receipt is None:
        raise HTTPException(
            status_code=409,
            detail="Administrator non-AI origin approval required",
        )

    try:
        origin_result = require_c2_origin_authorization(
            merge_set, mapping, receipt
        )
    except C2OriginAuthorizationError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if receipt.get("approval_basis") != "administrator_source_review":
        raise HTTPException(
            status_code=409,
            detail="Unsupported C2 origin approval basis",
        )

    # Reconstruct the actual approved mapped source population.
    processing_set = _load_cyber2_merge_processing_set(
        workspace=workspace,
        client=body.client,
        project=body.project,
        header_set_id=header_set_id,
        approved_mapping=mapping,
    )

    try:
        conservation_result = validate_c2_merge_population(
            merge_set,
            processing_set["records"],
            workspace=workspace,
            client=body.client,
            project=body.project,
        )

        projection = build_c2_projection(
            merge_set,
            mapping,
            conservation_result,
            origin_result,
        )
    except (
        C2TransferValidationError,
        C2ProjectionError,
    ) as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    # Recheck the latest completed lineage before the write.
    # This is not a substitute for storage-level immutability.
    inspect_cyber2_c2_transfer_readiness(
        workspace=workspace,
        response=response,
        client=body.client,
        project=body.project,
        merge_set_id=body.merge_set_id,
        current_user=current_user,
    )

    snapshot_store = Cyber2C2TransferStore(
        container,
        base_path,
        workspace=workspace,
        client=body.client,
        project=body.project,
    )

    try:
        saved = snapshot_store.save(
            projection,
            authorized_by=actor,
        )
    except C2TransferStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    # Do not return full field provenance to the caller.
    return {
        **saved,
        "workspace": workspace,
        "client": body.client,
        "project": body.project,
        "origin_approval_verified": True,
        "source_conservation_verified": True,
    }

@router.get("/{workspace}/cyber2/c2/project-records")
def read_cyber2_project_c2_records(
    workspace: Workspace,
    response: Response,
    client: str = Query(min_length=1),
    project: str = Query(min_length=1),
    current_user=Depends(get_current_user),
):
    """Aggregate authorized C2 transfers without reading other views."""
    from app.services.cyber2.c2_transfer_store import (
        C2TransferStoreError,
        Cyber2C2TransferStore,
    )
    from app.services.cyber2.merge_set_store import MergeSetStoreError

    require_scoped_project_access(
        current_user, workspace, client, project
    )
    require_permission(current_user, PERMISSION_REVIEW)
    require_admin(current_user)

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    merge_store = _cyber2_merge_store_for(
        workspace, client, project
    )

    try:
        completed = merge_store.list_completed()
    except MergeSetStoreError as exc:
        raise HTTPException(
            status_code=409, detail=str(exc)
        ) from exc

    if not isinstance(completed, list) or len(completed) >= 1000:
        raise HTTPException(
            status_code=409,
            detail="C2 completed-set inventory may be incomplete",
        )

    header_ids = set()
    for item in completed:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=409,
                detail="Invalid C2 completed-set inventory",
            )
        header_id = item.get("header_set_id")
        if (
            item.get("status") != "completed"
            or not isinstance(header_id, str)
            or not header_id
        ):
            raise HTTPException(
                status_code=409,
                detail="Invalid completed Merge Set metadata",
            )
        header_ids.add(header_id)

    store = Cyber2C2TransferStore(
        _processing_container_client(),
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        ),
        workspace=workspace,
        client=client,
        project=project,
    )

    rows = []
    headers = []
    seen_rows = set()
    transferred_sets = []
    source_count = 0

    for header_id in sorted(header_ids):
        try:
            snapshot = store.display(header_id)
        except C2TransferStoreError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc)
            ) from exc

        if snapshot is None:
            continue

        if (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("rows"), list)
            or not isinstance(snapshot.get("headers"), list)
            or not isinstance(snapshot.get("merge_set_id"), str)
        ):
            raise HTTPException(
                status_code=409,
                detail="Invalid C2 snapshot response",
            )

        for row in snapshot["rows"]:
            if not isinstance(row, dict):
                raise HTTPException(
                    status_code=409, detail="Invalid C2 record"
                )

            identity = row.get("id")
            if (
                not isinstance(identity, str)
                or not identity
                or identity in seen_rows
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate or invalid C2 record identity",
                )

            seen_rows.add(identity)
            rows.append(row)

        for header in snapshot["headers"]:
            if (
                not isinstance(header, str)
                or not header
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Invalid C2 display header",
                )
            if header not in headers:
                headers.append(header)

        if snapshot.get("working_record_count") != len(snapshot["rows"]):
            raise HTTPException(
                status_code=409,
                detail="C2 working-record count mismatch",
            )

        original_count = snapshot.get("original_source_record_count")
        if not isinstance(original_count, int) or original_count <= 0:
            raise HTTPException(
                status_code=409,
                detail="C2 original-source count invalid",
            )

        source_count += original_count
        transferred_sets.append({
            "header_set_id": header_id,
            "merge_set_id": snapshot["merge_set_id"],
            "working_record_count": len(snapshot["rows"]),
        })

    return {
        "status": "ok",
        "source": "cyber2_c2_transfer",
        "workspace": workspace,
        "client": client,
        "project": project,
        "headers": headers,
        "rows": rows,
        "working_record_count": len(rows),
        "source_membership_count": source_count,
        "transferred_header_set_count": len(transferred_sets),
        "transferred_sets": transferred_sets,
    }
