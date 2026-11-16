"""Transport-independent, optimistic-concurrency persistence for Cyber2 membership.

The storage adapter MUST guarantee compare-and-swap (CAS) writes using a blob
ETag or an equivalent version token. This module never uses unsafe blind writes.
RAW evidence and historic registry snapshots are never modified here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .entity_membership import MembershipError, new_registry


class MembershipConflict(RuntimeError):
    """Concurrent update; caller must reload and reconcile, not auto-retry."""


@dataclass(frozen=True)
class StoredSnapshot:
    payload: dict[str, Any] | None
    version: str | None


class ConditionalRegistryStore(Protocol):
    """Store contract: write must use atomic create-if-absent or compare-and-swap.

    read: missing returns (None, None); an existing object returns a nonempty
    version. It MUST return a payload and version from the same object version.
    write: expected_version=None means create-only; otherwise atomic CAS.
    On mismatch, raise MembershipConflict and DO NOT write anything.
    """

    def read(self, path: str) -> StoredSnapshot: ...

    def write(self, path: str, payload: dict[str, Any], *, expected_version: str | None) -> str: ...


def registry_path(*, base_path: str) -> str:
    """Append a membership document under an existing canonical project base path."""
    if not isinstance(base_path, str) or not base_path.strip() or base_path.startswith('/'):
        raise MembershipError('A canonical project base path is required')
    parts = base_path.strip('/').split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise MembershipError('Invalid project base path')
    return f"{base_path.strip('/')}/cyber2/entity_membership/registry.json"


def _validate_scope(payload: Mapping[str, Any], *, workspace: str, client: str, project: str) -> None:
    expected = (workspace, client, project)
    actual = (payload.get('workspace'), payload.get('client'), payload.get('project'))
    if actual != expected:
        raise MembershipError('Registry workspace/client/project does not match request')
    if payload.get('schema_version') != 1 or not isinstance(payload.get('revision'), int):
        raise MembershipError('Invalid registry version or revision')
    if payload['revision'] < 0 or not isinstance(payload.get('entities'), dict) or not isinstance(payload.get('history'), list):
        raise MembershipError('Malformed registry')
    assigned: set[str] = set()
    for entity_id, entry in payload['entities'].items():
        if not isinstance(entity_id, str) or not entity_id.strip() or not isinstance(entry, dict):
            raise MembershipError('Invalid entity entry')
        if entry.get('status') not in {'approved', 'pending'}:
            raise MembershipError('Invalid entity status')
        raw_ids = entry.get('raw_ucids')
        if not isinstance(raw_ids, list) or not raw_ids or any(not isinstance(x,str) or not x.strip() for x in raw_ids):
            raise MembershipError('Invalid RAW UCIDs')
        if len(set(raw_ids)) != len(raw_ids) or assigned.intersection(raw_ids):
            raise MembershipError('Duplicate RAW UCID membership')
        assigned.update(raw_ids)


def load_registry(store: ConditionalRegistryStore, *, path: str, workspace: str, client: str, project: str) -> tuple[dict[str, Any], str | None]:
    """Return an isolated registry and matching version token; never write on read."""
    snapshot = store.read(path)
    if not isinstance(snapshot, StoredSnapshot):
        raise MembershipError('Invalid storage response')
    if snapshot.payload is None:
        if snapshot.version is not None:
            raise MembershipError('Missing registry must not carry a storage version')
        return new_registry(workspace=workspace, client=client, project=project), None
    if not isinstance(snapshot.version, str) or not snapshot.version:
        raise MembershipError('Persisted registry must carry a storage version')
    if not isinstance(snapshot.payload, dict):
        raise MembershipError('Invalid registry payload')
    _validate_scope(snapshot.payload, workspace=workspace, client=client, project=project)
    return deepcopy(snapshot.payload), snapshot.version


def update_registry(store: ConditionalRegistryStore, *, path: str, workspace: str, client: str, project: str,
                    mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """Apply a pure membership operation and write only with atomic concurrency protection.

    Caller must authenticate/authorize before invoking this function and must
    validate source RAW UCIDs with the actual project source population.
    """
    before, version = load_registry(store, path=path, workspace=workspace, client=client, project=project)
    after = mutate(deepcopy(before))
    if not isinstance(after, dict):
        raise MembershipError('Membership mutation must return a registry')
    _validate_scope(after, workspace=workspace, client=client, project=project)
    if after['revision'] != before['revision'] + 1:
        raise MembershipError('Membership operation must advance revision by exactly one')
    if len(after['history']) != len(before['history']) + 1:
        raise MembershipError('Membership operation must append exactly one audit event')
    if after['history'][:len(before['history'])] != before['history']:
        raise MembershipError('Membership history may not be altered')
    if after['history'][-1].get('revision') != after['revision']:
        raise MembershipError('Audit entry revision mismatch')
    new_version = store.write(path, deepcopy(after), expected_version=version)
    if not isinstance(new_version, str) or not new_version:
        raise MembershipError('Storage did not return a committed version')
    return after, new_version
