"""Approval operation for Cyber2's existing project-scoped RAW membership registry.

Pure transformation: no storage, no network calls, no source mutation.
Only an authenticated, authorized API may invoke this operation and persist the
result using membership_persistence.update_registry (ETag compare-and-swap).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .entity_membership import MembershipError, _event, _require_text, _validated_copy


def approve_entity(
    registry: Mapping[str, Any],
    *,
    entity_id: str,
    actor: str,
    note: str = "",
) -> dict[str, Any]:
    """Approve an existing pending entity without changing any RAW membership.

    Reject duplicate approvals, unknown entities, or corrupted registries.
    Preserve a reversible audit history via the registry's existing event model.
    """
    result = _validated_copy(registry)
    key = _require_text(entity_id, "entity_id")
    reviewer = _require_text(actor, "actor")
    entry = result["entities"].get(key)
    if entry is None:
        raise MembershipError("Unknown entity")
    if entry["status"] != "pending":
        raise MembershipError("Entity is not pending approval")

    before = deepcopy(result["entities"])
    entry["status"] = "approved"
    _event(result, "approve", reviewer, before, note=str(note or ""))
    return result
