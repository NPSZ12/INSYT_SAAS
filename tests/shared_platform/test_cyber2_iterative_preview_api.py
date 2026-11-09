from copy import deepcopy

import pytest
from fastapi import HTTPException

from test_cyber2_membership_api import harness
from test_cyber2_iterative_merge_input import parent


def configure(api, monkeypatch, *, scope_override=None):
    saved = parent()
    saved.update({
        "workspace": "capture",
        "client": "ACME",
        "project": "CaseA",
        "integrity_sha256": "a" * 64,
    })

    if scope_override:
        saved.update(scope_override)

    class FakeStore:
        def load(self, merge_set_id):
            assert merge_set_id == saved["merge_set_id"]
            return deepcopy(saved)

    monkeypatch.setattr(
        api, "_cyber2_merge_store_for",
        lambda workspace, client, project: FakeStore()
    )

    return saved


def request(api, user):
    return api.preview_cyber2_iterative_merge(
        "capture",
        api.IterativePreviewBody(
            client="ACME",
            project="CaseA",
            parent_merge_set_id="MSET-" + "A" * 32,
            merge_index=["First Name", "DOB"],
        ),
        user,
    )


def test_authorized_preview_reads_parent_without_write(
    harness, monkeypatch
):
    api, user, registry = harness
    saved = configure(api, monkeypatch)
    original = deepcopy(saved)

    response = request(api, user)

    assert response["status"] == "iterative_preview"
    assert response["input_working_record_count"] == 2
    assert response["original_source_record_count"] == 4
    assert response["conflict_group_count"] == 1
    assert response["execution_enabled"] is False
    assert len(response["snapshot_fingerprint"]) == 64
    assert registry["writes"] == 0
    assert saved == original


def test_cross_project_parent_rejected(harness, monkeypatch):
    api, user, _ = harness
    configure(api, monkeypatch, scope_override={"project": "Other"})

    with pytest.raises(HTTPException) as exc:
        request(api, user)

    assert exc.value.status_code == 409


def test_invalid_parent_integrity_rejected(harness, monkeypatch):
    api, user, _ = harness
    configure(
        api, monkeypatch,
        scope_override={"integrity_sha256": "invalid"}
    )

    with pytest.raises(HTTPException) as exc:
        request(api, user)

    assert exc.value.status_code == 409


def test_authorization_denied_before_storage(harness, monkeypatch):
    api, user, _ = harness
    touched = []

    monkeypatch.setattr(
        api, "require_scoped_project_access",
        lambda *args: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="Access denied")
        ),
    )
    monkeypatch.setattr(
        api, "_cyber2_merge_store_for",
        lambda *args: touched.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        request(api, user)

    assert exc.value.status_code == 403
    assert touched == []
