"""Step 3: CAS and project isolation tests. No Azure access or credentials needed."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.services.cyber2.entity_membership import MembershipError, register_entity, new_registry
from app.services.cyber2.membership_persistence import (
    StoredSnapshot, MembershipConflict, registry_path, load_registry, update_registry,
)


class FakeCAS:
    def __init__(self):
        self.data = {}
        self.counter = 0
        self.before_write = None

    def read(self, path):
        if path not in self.data:
            return StoredSnapshot(None, None)
        record, version = self.data[path]
        return StoredSnapshot(deepcopy(record), version)

    def write(self, path, payload, *, expected_version):
        if self.before_write:
            hook, self.before_write = self.before_write, None
            hook()
        actual = self.data[path][1] if path in self.data else None
        if actual != expected_version:
            raise MembershipConflict('Concurrent write')
        self.counter += 1
        version = f'v{self.counter}'
        self.data[path] = (deepcopy(payload), version)
        return version


P = 'acme/capture/case-a/cyber2/entity_membership/registry.json'

def mutate_add(r):
    return register_entity(r, entity_id='E1', raw_ucids=['RAW1'], known_raw_ucids=['RAW1'], actor='reviewer', status='approved')


def save(store, *, path=P, workspace='capture', client='acme', project='case-a', mutate=mutate_add):
    return update_registry(store, path=path, workspace=workspace, client=client, project=project, mutate=mutate)


def test_registry_path():
    assert registry_path(base_path='acme/capture/case-a') == P


def test_new_read_has_no_side_effects():
    s = FakeCAS()
    r, ver = load_registry(s, path=P, workspace='capture', client='acme', project='case-a')
    assert r == new_registry(workspace='capture', client='acme', project='case-a')
    assert ver is None and not s.data


def test_create_load_membership():
    s = FakeCAS()
    r, v = save(s)
    assert r['revision'] == 1 and v == 'v1'
    reread, token = load_registry(s, path=P, workspace='capture', client='acme', project='case-a')
    assert reread['entities']['E1']['raw_ucids'] == ['RAW1'] and token == v


def test_scope_mismatch_fails_closed():
    s = FakeCAS()
    save(s)
    with pytest.raises(MembershipError):
        load_registry(s, path=P, workspace='discovery', client='acme', project='case-a')
    with pytest.raises(MembershipError):
        load_registry(s, path=P, workspace='capture', client='acme', project='other')


def test_two_writers_conflict_no_lost_update():
    s = FakeCAS()
    save(s)
    def other_writer():
        current, _ = s.data[P]
        s.counter += 1
        s.data[P] = (deepcopy(current), f'v{s.counter}')
    s.before_write = other_writer
    with pytest.raises(MembershipConflict):
        save(s, mutate=lambda r: register_entity(r, entity_id='E2', raw_ucids=['RAW2'], known_raw_ucids=['RAW1','RAW2'], actor='reviewer', status='approved'))
    assert 'E2' not in s.data[P][0]['entities']


def test_reject_cross_project_payload():
    s = FakeCAS()
    with pytest.raises(MembershipError):
        save(s, mutate=lambda r: {**r, 'project':'wrong', 'revision':1, 'history':[{'revision':1}]})
    assert not s.data


def test_reject_revision_without_event():
    s = FakeCAS()
    with pytest.raises(MembershipError):
        save(s, mutate=lambda r: {**r, 'revision':1})
    assert not s.data


def test_reject_mutated_history():
    s = FakeCAS()
    save(s)
    def bad(r):
        r['history'][0]['actor']='tampered'
        r['revision']=2
        r['history'].append({'revision':2})
        return r
    with pytest.raises(MembershipError):
        save(s, mutate=bad)


def test_returned_snapshot_is_not_live_reference():
    s=FakeCAS()
    record, _ = save(s)
    record['entities']['E1']['raw_ucids'].append('BAD')
    persisted, _ = load_registry(s, path=P, workspace='capture', client='acme', project='case-a')
    assert persisted['entities']['E1']['raw_ucids'] == ['RAW1']
