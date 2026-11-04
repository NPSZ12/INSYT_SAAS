"""Isolated endpoint tests; no Azure calls, no new databases."""
from __future__ import annotations
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))


def _load_api(monkeypatch):
    # Stub only the heavyweight INSYT imports; test real pure Cyber2 services.
    pc = types.ModuleType("app.api.processing_center_azure")
    pc._project_base_path = lambda *, workspace, client, project: f"{client}/{workspace}/{project}"
    pc._processing_container_client = lambda: object()
    ent = types.ModuleType("app.api.entities")
    ent.load_cyber2_raw_capture_records = lambda workspace, client, project: []
    auth = types.ModuleType("app.services.authorization")
    auth.PERMISSION_REVIEW = "Can: Review"
    auth.require_scoped_project_access = lambda *args: None
    auth.require_permission = lambda *args: None
    sec = types.ModuleType("app.services.security")
    sec.get_current_user = lambda: None
    for key, value in {
        "app.api.processing_center_azure": pc,
        "app.api.entities": ent,
        "app.services.authorization": auth,
        "app.services.security": sec,
    }.items():
        monkeypatch.setitem(sys.modules, key, value)
    path = BACKEND / "app/api/cyber2/field_evidence_api.py"
    spec = importlib.util.spec_from_file_location("isolated_cyber2_field_evidence_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raw():
    records = []
    for i in range(100):
        metadata = {"Full Name": "Example Person"}
        if i in (4, 52, 80):
            metadata["SSN"] = "000-00-1234"  # synthetic, never returned
        records.append({
            "ucid": f"RAW-{i:03d}", "doc_id": f"DOC-{i:03d}",
            "metadata": metadata,
            "provenance": {"source_row_number": i + 1},
        })
    return records


def _setup(monkeypatch):
    a = _load_api(monkeypatch)
    raw = _raw()
    from app.services.cyber2.entity_membership import new_registry, register_entity
    registry = register_entity(
        new_registry(workspace="capture", client="ACME", project="CaseA"),
        entity_id="E1", raw_ucids=[r["ucid"] for r in raw],
        known_raw_ucids=[r["ucid"] for r in raw],
        actor="reviewer", status="approved",
    )
    a._processing_container_client = lambda: object()
    a.AzureBlobMembershipStore = lambda container: object()
    a.load_registry = lambda *args, **kwargs: (registry, '"etag1"')
    a.load_cyber2_raw_capture_records = lambda w, c, p: raw
    return a


def test_100_raw_three_ssn_docs_and_no_values(monkeypatch):
    a = _setup(monkeypatch)
    response = a.get_cyber2_entity_field_evidence(
        workspace="capture", entity_id="E1", client="ACME",
        project="CaseA", field="SSN", current_user=SimpleNamespace(),
    )
    assert response["entity_raw_record_count"] == 100
    assert response["matching_document_count"] == 3
    assert {d["source_doc_id"] for d in response["documents"]} == {"DOC-004", "DOC-052", "DOC-080"}
    assert "000-00-1234" not in str(response)


def test_no_matches_returns_empty_not_all(monkeypatch):
    a = _setup(monkeypatch)
    response = a.get_cyber2_entity_field_evidence(
        workspace="capture", entity_id="E1", client="ACME",
        project="CaseA", field="MRN", current_user=SimpleNamespace(),
    )
    assert response["matching_document_count"] == 0
    assert response["documents"] == []


def test_scoped_access_failure_before_any_storage_access(monkeypatch):
    a = _setup(monkeypatch)
    touched = []
    def deny(*args):
        raise HTTPException(status_code=403, detail="Denied")
    a.require_scoped_project_access = deny
    a._processing_container_client = lambda: touched.append(True)
    with pytest.raises(HTTPException) as e:
        a.get_cyber2_entity_field_evidence(
            workspace="discovery", entity_id="E1", client="OTHER",
            project="CaseA", field="SSN", current_user=SimpleNamespace(),
        )
    assert e.value.status_code == 403
    assert not touched


def test_review_permission_failure_before_storage(monkeypatch):
    a = _setup(monkeypatch)
    touched = []
    a.require_permission = lambda *args: (_ for _ in ()).throw(HTTPException(status_code=403))
    a._processing_container_client = lambda: touched.append(True)
    with pytest.raises(HTTPException) as e:
        a.get_cyber2_entity_field_evidence(
            workspace="capture", entity_id="E1", client="ACME",
            project="CaseA", field="SSN", current_user=SimpleNamespace(),
        )
    assert e.value.status_code == 403
    assert not touched


def test_unapproved_entity_not_visible(monkeypatch):
    a = _setup(monkeypatch)
    with pytest.raises(HTTPException) as e:
        a.get_cyber2_entity_field_evidence(
            workspace="capture", entity_id="UNKNOWN", client="ACME",
            project="CaseA", field="SSN", current_user=SimpleNamespace(),
        )
    assert e.value.status_code == 404


def test_missing_raw_member_fail_closed(monkeypatch):
    a = _setup(monkeypatch)
    a.load_cyber2_raw_capture_records = lambda w,c,p: _raw()[:99]
    with pytest.raises(HTTPException) as e:
        a.get_cyber2_entity_field_evidence(
            workspace="capture", entity_id="E1", client="ACME",
            project="CaseA", field="SSN", current_user=SimpleNamespace(),
        )
    assert e.value.status_code == 409


def test_conflict_fail_closed(monkeypatch):
    a = _setup(monkeypatch)
    from app.services.cyber2.membership_persistence import MembershipConflict
    a.load_registry = lambda *args, **kwargs: (_ for _ in ()).throw(MembershipConflict("race"))
    with pytest.raises(HTTPException) as e:
        a.get_cyber2_entity_field_evidence(
            workspace="capture", entity_id="E1", client="ACME",
            project="CaseA", field="SSN", current_user=SimpleNamespace(),
        )
    assert e.value.status_code == 409
