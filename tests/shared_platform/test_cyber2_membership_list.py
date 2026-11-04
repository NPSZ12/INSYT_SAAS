"""Tests for the authenticated Cyber2 membership listing endpoint."""

import pytest
from fastapi import HTTPException

from test_cyber2_membership_api import harness, register


def list_entities(api, user):
    return api.list_cyber2_memberships(
        "capture",
        client="ACME",
        project="CaseA",
        current_user=user,
    )


def test_empty_registry_read_only(harness):
    api, user, store = harness

    result = list_entities(api, user)

    assert result["revision"] == 0
    assert result["entity_count"] == 0
    assert result["entities"] == []
    assert result["raw_inventory_count"] == 3
    assert store["writes"] == 0


def test_list_pending_and_approved_entities(harness):
    api, user, store = harness

    register(api, user, "E1", ["R1", "R2"])
    register(api, user, "E2", ["R3"])

    api.approve_cyber2_membership(
        "capture",
        api.ApproveBody(
            client="ACME",
            project="CaseA",
            entity_id="E1",
        ),
        user,
    )

    writes_before = store["writes"]
    result = list_entities(api, user)

    assert result["revision"] == 3
    assert result["entity_count"] == 2
    assert store["writes"] == writes_before

    entries = {
        entity["entity_id"]: entity
        for entity in result["entities"]
    }

    assert entries["E1"]["status"] == "approved"
    assert entries["E1"]["raw_count"] == 2
    assert entries["E1"]["raw_ucids"] == ["R1", "R2"]

    assert entries["E2"]["status"] == "pending"
    assert entries["E2"]["raw_count"] == 1

    assert "history" not in result


def test_project_denial_before_storage(harness):
    api, user, store = harness

    touched = []

    def deny(*args):
        raise HTTPException(status_code=403)

    api.require_scoped_project_access = deny
    api._processing_container_client = lambda: touched.append(True)

    with pytest.raises(HTTPException) as exc:
        list_entities(api, user)

    assert exc.value.status_code == 403
    assert not touched
    assert store["writes"] == 0


def test_review_permission_denial_before_storage(harness):
    api, user, store = harness

    touched = []

    def deny(*args):
        raise HTTPException(status_code=403)

    api.require_permission = deny
    api._processing_container_client = lambda: touched.append(True)

    with pytest.raises(HTTPException) as exc:
        list_entities(api, user)

    assert exc.value.status_code == 403
    assert not touched


def test_admin_denial_before_storage(harness):
    api, user, store = harness

    touched = []

    def deny(*args):
        raise HTTPException(status_code=403)

    api.require_admin = deny
    api._processing_container_client = lambda: touched.append(True)

    with pytest.raises(HTTPException) as exc:
        list_entities(api, user)

    assert exc.value.status_code == 403
    assert not touched


def test_missing_raw_membership_rejected(harness):
    api, user, store = harness

    register(api, user, "E1", ["R1"])

    api.load_cyber2_raw_capture_records = (
        lambda *args: [
            {"ucid": "R2"},
            {"ucid": "R3"},
        ]
    )

    writes_before = store["writes"]

    with pytest.raises(HTTPException) as exc:
        list_entities(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == writes_before