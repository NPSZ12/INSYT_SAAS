"""Offline iterative API-to-store integration tests.

Uses the actual Cyber2MergeSetStore with the existing fake Azure
Blob container. No network, Azure, RAW, or membership writes.
"""

from copy import deepcopy

import pytest
from fastapi import HTTPException

from app.services.cyber2.merge_set_store import Cyber2MergeSetStore
from test_cyber2_membership_api import harness
from test_cyber2_iterative_merge_input import parent
from test_cyber2_merge_set_store import FakeContainer


PARENT_REQUEST = "a82bea4e-86f6-449c-a8a2-aa76c15cdf97"
CHILD_REQUEST = "d992a20e-2d55-4d1d-8de7-e047ad012990"


def setup(api, monkeypatch):
    container = FakeContainer()

    store = Cyber2MergeSetStore(
        container,
        "ACME/capture/CaseA",
        content_settings_factory=lambda: {
            "content_type": "application/json",
        },
    )

    original = parent()
    derived = deepcopy(original)
    derived["status"] = "derived_not_persisted"

    # A persisted Pass 1 set must include the original Merge Index
    # and merged-group count. The lightweight iterative fixture
    # intentionally omits these persistence-specific fields.
    derived["merge_index"] = ["First Name", "SSN"]
    derived["merged_group_count"] = 1

    receipt = store.save(
        derived=derived,
        workspace="capture",
        client="ACME",
        project="CaseA",
        approved_mapping_path="approved-mapping.json",
        executed_by="TEST-ADMIN",
    )

    parent_id = receipt["merge_set_id"]
    saved_parent = store.load(parent_id)

    monkeypatch.setattr(
        api,
        "_cyber2_merge_store_for",
        lambda workspace, client, project: store,
    )

    monkeypatch.setattr(
        api,
        "_cyber2_execution_actor",
        lambda user: "TEST-ADMIN",
    )

    return store, container, parent_id, saved_parent


def preview(api, user, parent_id):
    return api.preview_cyber2_iterative_merge(
        "capture",
        api.IterativePreviewBody(
            client="ACME",
            project="CaseA",
            parent_merge_set_id=parent_id,
            merge_index=["First Name", "DOB"],
        ),
        user,
    )


def execute(api, user, parent_id, fingerprint, request_id):
    return api.execute_cyber2_iterative_merge(
        "capture",
        api.IterativeExecuteBody(
            client="ACME",
            project="CaseA",
            parent_merge_set_id=parent_id,
            merge_index=["First Name", "DOB"],
            snapshot_fingerprint=fingerprint,
            request_id=request_id,
        ),
        user,
    )


def test_actual_store_child_save_and_idempotent_retry(
    harness, monkeypatch
):
    api, user, registry = harness

    store, container, parent_id, original_parent = setup(
        api, monkeypatch
    )

    original_parent = deepcopy(original_parent)
    result = preview(api, user, parent_id)

    first = execute(
        api,
        user,
        parent_id,
        result["snapshot_fingerprint"],
        CHILD_REQUEST,
    )

    assert first["status"] == "completed"
    assert first["pass_number"] == 2
    assert first["parent_merge_set_id"] == parent_id
    assert first["idempotent_replay"] is False

    child_id = first["merge_set_id"]
    saved_child = store.load(child_id)

    assert saved_child["parent_merge_set_id"] == parent_id
    assert saved_child["pass_number"] == 2
    assert saved_child["input_working_record_count"] == 2
    assert saved_child["raw_record_count"] == 4
    assert saved_child["working_record_count"] == 2
    assert saved_child["conflict_group_count"] == 1
    assert saved_child["integrity_sha256"]

    parent_after_first = store.load(parent_id)
    assert parent_after_first == original_parent

    retry = execute(
        api,
        user,
        parent_id,
        result["snapshot_fingerprint"],
        CHILD_REQUEST,
    )

    assert retry["merge_set_id"] == child_id
    assert retry["idempotent_replay"] is True

    assert store.load(child_id) == saved_child
    assert store.load(parent_id) == original_parent
    assert registry["writes"] == 0


def test_stale_preview_creates_no_child(
    harness, monkeypatch
):
    api, user, registry = harness

    store, container, parent_id, original_parent = setup(
        api, monkeypatch
    )

    result = preview(api, user, parent_id)

    with pytest.raises(HTTPException) as error:
        execute(
            api,
            user,
            parent_id,
            "0" * 64,
            CHILD_REQUEST,
        )

    assert error.value.status_code == 409
    assert store.load(parent_id) == original_parent
    assert registry["writes"] == 0

    # A rejected execution must not leave a child blob behind.
    child_id = "MSET-" + CHILD_REQUEST.replace("-", "").upper()
    assert not any(
        child_id in path for path in container.storage
    )
