from copy import deepcopy

import pytest
from fastapi import HTTPException

from test_cyber2_membership_api import harness
from test_cyber2_iterative_merge_input import parent


REQUEST_ID = "a82bea4e-86f6-449c-a8a2-aa76c15cdf97"


def configure(api, monkeypatch):
    saved = parent()
    saved.update({
        "workspace": "capture",
        "client": "ACME",
        "project": "CaseA",
        "approved_mapping_path": "approved-mapping.json",
        "integrity_sha256": "a" * 64,
    })
    writes = []

    class FakeStore:
        def load(self, merge_set_id):
            assert merge_set_id == saved["merge_set_id"]
            return deepcopy(saved)

        def save(self, **kwargs):
            writes.append(kwargs)
            return {
                "merge_set_id": "MSET-" + "B" * 32,
                "status": "completed",
                "idempotent_replay": False,
                "working_record_count":
                    kwargs["derived"]["working_record_count"],
            }

    monkeypatch.setattr(
        api, "_cyber2_merge_store_for",
        lambda *args: FakeStore(),
    )
    monkeypatch.setattr(
        api, "_cyber2_execution_actor",
        lambda user: "TEST-ADMIN",
    )
    return saved, writes


def body(api, fingerprint):
    return api.IterativeExecuteBody(
        client="ACME",
        project="CaseA",
        parent_merge_set_id="MSET-" + "A" * 32,
        merge_index=["First Name", "DOB"],
        snapshot_fingerprint=fingerprint,
        request_id=REQUEST_ID,
    )


def get_preview(api, user):
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


def test_execution_creates_child_without_mutating_parent(
    harness, monkeypatch
):
    api, user, registry = harness
    source, writes = configure(api, monkeypatch)
    original = deepcopy(source)
    preview = get_preview(api, user)

    result = api.execute_cyber2_iterative_merge(
        "capture",
        body(api, preview["snapshot_fingerprint"]),
        user,
    )

    assert result["status"] == "completed"
    assert result["pass_number"] == 2
    assert result["parent_merge_set_id"] == source["merge_set_id"]
    assert result["input_working_record_count"] == 2
    assert result["working_record_count"] == 2
    assert len(writes) == 1
    assert writes[0]["request_id"] == REQUEST_ID
    assert writes[0]["derived"]["raw_record_count"] == 4
    assert registry["writes"] == 0
    assert source == original


def test_stale_fingerprint_prevents_write(harness, monkeypatch):
    api, user, _ = harness
    _, writes = configure(api, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        api.execute_cyber2_iterative_merge(
            "capture",
            body(api, "0" * 64),
            user,
        )

    assert exc.value.status_code == 409
    assert writes == []


def test_parent_integrity_change_prevents_write(
    harness, monkeypatch
):
    api, user, _ = harness
    source, writes = configure(api, monkeypatch)
    preview = get_preview(api, user)

    source["integrity_sha256"] = "b" * 64

    with pytest.raises(HTTPException) as exc:
        api.execute_cyber2_iterative_merge(
            "capture",
            body(api, preview["snapshot_fingerprint"]),
            user,
        )

    assert exc.value.status_code == 409
    assert writes == []


def test_access_denied_before_write(harness, monkeypatch):
    api, user, _ = harness
    _, writes = configure(api, monkeypatch)

    monkeypatch.setattr(
        api, "require_scoped_project_access",
        lambda *args: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="Denied")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        api.execute_cyber2_iterative_merge(
            "capture",
            body(api, "0" * 64),
            user,
        )

    assert exc.value.status_code == 403
    assert writes == []
