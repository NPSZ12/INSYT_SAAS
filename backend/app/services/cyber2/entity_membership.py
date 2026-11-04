"""Pure, project-scoped Cyber2 entity-to-RAW membership operations.

No database, Azure, authentication, fuzzy matching, or source-data mutations.
Only an authorized API/storage layer may persist a returned registry snapshot.
Snapshots are copy-on-write; every approved merge has a reversible audit entry.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class MembershipError(ValueError):
    """Unsafe, ambiguous or invalid entity membership operation."""


def _require_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MembershipError(f"{name} is required")
    return text


def _ids(values: Iterable[str], name: str) -> list[str]:
    result = [_require_text(v, name) for v in values]
    if len(set(result)) != len(result):
        raise MembershipError(f"Duplicate {name}")
    if not result:
        raise MembershipError(f"At least one {name} is required")
    return result


def new_registry(*, workspace: str, client: str, project: str) -> dict[str, Any]:
    if workspace not in {"capture", "discovery"}:
        raise MembershipError("Unsupported workspace")
    return {
        "schema_version": 1,
        "workspace": workspace,
        "client": _require_text(client, "client"),
        "project": _require_text(project, "project"),
        "revision": 0,
        "entities": {},
        "history": [],
    }


def _validated_copy(registry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(registry, Mapping) or registry.get("schema_version") != 1:
        raise MembershipError("Invalid registry schema")
    if registry.get("workspace") not in {"capture", "discovery"}:
        raise MembershipError("Invalid registry workspace")
    for key in ("client", "project"):
        _require_text(registry.get(key), key)
    result = deepcopy(dict(registry))
    if not isinstance(result.get("entities"), dict) or not isinstance(result.get("history"), list):
        raise MembershipError("Invalid registry contents")
    if not isinstance(result.get("revision"), int) or result["revision"] < 0:
        raise MembershipError("Invalid registry revision")
    claimed: dict[str, str] = {}
    for entity_id, entry in result["entities"].items():
        _require_text(entity_id, "entity_id")
        if not isinstance(entry, dict) or entry.get("status") not in {"approved", "pending"}:
            raise MembershipError("Invalid entity entry")
        ucids = _ids(entry.get("raw_ucids", []), "RAW UCID")
        for ucid in ucids:
            if ucid in claimed:
                raise MembershipError(f"RAW UCID {ucid} belongs to multiple entities")
            claimed[ucid] = entity_id
    return result


def _validate_known(ucids: Iterable[str], known_raw_ucids: Iterable[str]) -> None:
    known = set(_ids(known_raw_ucids, "known RAW UCID"))
    missing = set(ucids) - known
    if missing:
        raise MembershipError("RAW UCIDs not found in source population: " + ", ".join(sorted(missing)))


def _event(result: dict[str, Any], operation: str, actor: str, before: dict[str, Any],
           *, note: str = "") -> None:
    result["revision"] += 1
    result["history"].append({
        "revision": result["revision"],
        "operation": operation,
        "actor": _require_text(actor, "actor"),
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "before_entities": before,
        "after_entities": deepcopy(result["entities"]),
    })


def register_entity(registry: Mapping[str, Any], *, entity_id: str, raw_ucids: Iterable[str],
                    known_raw_ucids: Iterable[str], actor: str, status: str = "pending") -> dict[str, Any]:
    """Register explicitly selected RAW members; never infer identity from names."""
    result = _validated_copy(registry)
    entity_id = _require_text(entity_id, "entity_id")
    ucids = _ids(raw_ucids, "RAW UCID")
    _validate_known(ucids, known_raw_ucids)
    if status not in {"approved", "pending"}:
        raise MembershipError("Invalid status")
    if entity_id in result["entities"]:
        raise MembershipError("Entity already exists")
    occupied = {ucid for entity in result["entities"].values() for ucid in entity["raw_ucids"]}
    if occupied.intersection(ucids):
        raise MembershipError("RAW UCID already assigned to another entity")
    before = deepcopy(result["entities"])
    result["entities"][entity_id] = {"status": status, "raw_ucids": ucids}
    _event(result, "register", actor, before)
    return result


def merge_entities(registry: Mapping[str, Any], *, target_entity_id: str,
                   source_entity_ids: Iterable[str], actor: str,
                   known_raw_ucids: Iterable[str], note: str = "") -> dict[str, Any]:
    """Explicit, reviewer-approved merge; retain all membership and reversible history."""
    result = _validated_copy(registry)
    target = _require_text(target_entity_id, "target_entity_id")
    sources = _ids(source_entity_ids, "source_entity_id")
    if target in sources:
        raise MembershipError("Target cannot be its own source")
    entities = result["entities"]
    for entity_id in [target, *sources]:
        if entity_id not in entities:
            raise MembershipError(f"Unknown entity: {entity_id}")
        if entities[entity_id]["status"] != "approved":
            raise MembershipError(f"Entity requires approval: {entity_id}")
    before = deepcopy(entities)
    combined = list(entities[target]["raw_ucids"])
    for source in sources:
        combined.extend(entities[source]["raw_ucids"])
    _validate_known(combined, known_raw_ucids)
    entities[target]["raw_ucids"] = combined
    for source in sources:
        del entities[source]
    _event(result, "merge", actor, before, note=note)
    return result


def reverse_last_merge(registry: Mapping[str, Any], *, actor: str) -> dict[str, Any]:
    """Undo only the most recent merge; reject stale or intervening operations."""
    result = _validated_copy(registry)
    if not result["history"] or result["history"][-1].get("operation") != "merge":
        raise MembershipError("Last operation is not a merge")
    last = result["history"][-1]
    if last.get("revision") != result["revision"] or last.get("after_entities") != result["entities"]:
        raise MembershipError("Registry changed since merge")
    prior = deepcopy(last["before_entities"])
    before = deepcopy(result["entities"])
    result["entities"] = prior
    _validated_copy(result)
    _event(result, "reverse_merge", actor, before, note=f"Reversed revision {last['revision']}")
    return result


def approved_entity_ucids(registry: Mapping[str, Any], *, entity_id: str) -> list[str]:
    result = _validated_copy(registry)
    entry = result["entities"].get(_require_text(entity_id, "entity_id"))
    if entry is None or entry["status"] != "approved":
        raise MembershipError("Approved entity not found")
    return list(entry["raw_ucids"])
