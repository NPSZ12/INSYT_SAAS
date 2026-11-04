"""Offline Step 4B-2 API tests; no Azure/network calls or client evidence."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2] / 'backend'
sys.path.insert(0, str(BACKEND))


def load_api(monkeypatch):
    processing = types.ModuleType('app.api.processing_center_azure')
    processing._project_base_path = lambda *, workspace, client, project: f'{client}/{workspace}/{project}'
    processing._processing_container_client = lambda: object()
    entities = types.ModuleType('app.api.entities')
    entities.load_cyber2_raw_capture_records = lambda w, c, p: [
        {'ucid': f'R{i}', 'doc_id': f'D{i}'} for i in range(1, 4)
    ]
    auth = types.ModuleType('app.services.authorization')
    auth.PERMISSION_REVIEW = 'Can: Review'
    auth.require_permission = lambda *a: None
    auth.require_scoped_project_access = lambda *a: None
    sec = types.ModuleType('app.services.security')
    sec.get_current_user = lambda: None
    sec.require_admin = lambda user: user
    for k,v in {
        'app.api.processing_center_azure':processing,
        'app.api.entities':entities,
        'app.services.authorization':auth,
        'app.services.security':sec,
    }.items():
        monkeypatch.setitem(sys.modules, k, v)
    spec = importlib.util.spec_from_file_location('isolated_cyber2_membership_api', BACKEND / 'app/api/cyber2/membership_api.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness(monkeypatch):
    api = load_api(monkeypatch)
    from app.services.cyber2.entity_membership import new_registry
    from app.services.cyber2.membership_persistence import StoredSnapshot, MembershipConflict
    registry = {'value': None, 'etag': None, 'version': 0, 'writes': 0}
    class FakeStore:
        def __init__(self, container): pass
        def read(self, path):
            return StoredSnapshot(payload=registry['value'], version=registry['etag'])
        def write(self, path, payload, *, expected_version):
            if expected_version != registry['etag']:
                raise MembershipConflict('stale')
            registry['version'] += 1
            registry['writes'] += 1
            registry['etag'] = str(registry['version'])
            registry['value'] = payload
            return registry['etag']
    api.AzureBlobMembershipStore = FakeStore
    user = SimpleNamespace(username='reviewer')
    return api, user, registry


def register(api, user, id, ids, revision=None):
    return api.register_cyber2_membership('capture', api.RegisterBody(
        client='ACME', project='CaseA', entity_id=id,
        raw_ucids=ids, expected_revision=revision), user)


def test_registration_pending_and_server_actor(harness):
    api,user,store = harness
    result=register(api,user,'E1',['R1'])
    assert result['revision']==1
    assert store['value']['entities']['E1']=={'status':'pending','raw_ucids':['R1']}
    assert store['value']['history'][-1]['actor']=='reviewer'
    assert 'R1' not in str(result)


def test_approval_and_no_duplicate_approval(harness):
    api,user,store = harness
    register(api,user,'E1',['R1'])
    result=api.approve_cyber2_membership('capture',api.ApproveBody(client='ACME',project='CaseA',entity_id='E1'),user)
    assert result['revision']==2
    assert store['value']['entities']['E1']['status']=='approved'
    with pytest.raises(HTTPException) as exc:
        api.approve_cyber2_membership('capture',api.ApproveBody(client='ACME',project='CaseA',entity_id='E1'),user)
    assert exc.value.status_code==409


def test_merge_and_reverse(harness):
    api,user,store = harness
    for entity,ucid in [('E1','R1'),('E2','R2')]:
        register(api,user,entity,[ucid])
        api.approve_cyber2_membership('capture',api.ApproveBody(client='ACME',project='CaseA',entity_id=entity),user)
    api.merge_cyber2_membership('capture',api.MergeBody(client='ACME',project='CaseA',target_entity_id='E1',source_entity_ids=['E2']),user)
    assert store['value']['entities']['E1']['raw_ucids']==['R1','R2']
    api.reverse_cyber2_last_merge('capture',api.ReverseBody(client='ACME',project='CaseA'),user)
    assert set(store['value']['entities'])=={'E1','E2'}
    assert store['value']['entities']['E2']['raw_ucids']==['R2']


def test_unknown_raw_rejected_without_write(harness):
    api,user,store = harness
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['UNKNOWN'])
    assert exc.value.status_code==409
    assert store['writes']==0


def test_duplicate_membership_rejected(harness):
    api,user,store = harness
    register(api,user,'E1',['R1'])
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E2',['R1'])
    assert exc.value.status_code==409
    assert store['writes']==1


def test_stale_revision_rejected_without_write(harness):
    api,user,store = harness
    register(api,user,'E1',['R1'])
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E2',['R2'],revision=0)
    assert exc.value.status_code==409
    assert store['writes']==1


def test_project_denial_before_storage(harness):
    api,user,store = harness
    touched=[]
    api.require_scoped_project_access=lambda *a: (_ for _ in ()).throw(HTTPException(status_code=403))
    api._processing_container_client=lambda: touched.append(True)
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['R1'])
    assert exc.value.status_code==403 and not touched and store['writes']==0


def test_review_permission_denial_before_storage(harness):
    api,user,store = harness
    touched=[]
    api.require_permission=lambda *a: (_ for _ in ()).throw(HTTPException(status_code=403))
    api._processing_container_client=lambda: touched.append(True)
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['R1'])
    assert exc.value.status_code==403 and not touched


def test_admin_denial_before_storage(harness):
    api,user,store = harness
    touched=[]
    api.require_admin=lambda u: (_ for _ in ()).throw(HTTPException(status_code=403))
    api._processing_container_client=lambda: touched.append(True)
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['R1'])
    assert exc.value.status_code==403 and not touched


def test_blank_authenticated_actor_denied(harness):
    api,user,store = harness
    user.username=''
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['R1'])
    assert exc.value.status_code==403 and store['writes']==0


def test_duplicate_or_missing_raw_inventory_rejected(harness):
    api,user,store=harness
    api.load_cyber2_raw_capture_records=lambda *a:[{'ucid':'R1'}, {'ucid':'R1'}]
    with pytest.raises(HTTPException) as exc:
        register(api,user,'E1',['R1'])
    assert exc.value.status_code==409 and store['writes']==0


def test_reverse_cannot_undo_approval(harness):
    api,user,store=harness
    register(api,user,'E1',['R1'])
    api.approve_cyber2_membership('capture',api.ApproveBody(client='ACME',project='CaseA',entity_id='E1'),user)
    with pytest.raises(HTTPException) as exc:
        api.reverse_cyber2_last_merge('capture',api.ReverseBody(client='ACME',project='CaseA'),user)
    assert exc.value.status_code==409
