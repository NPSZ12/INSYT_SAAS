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