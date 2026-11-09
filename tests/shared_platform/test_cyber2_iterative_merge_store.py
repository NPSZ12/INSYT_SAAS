from copy import deepcopy

import pytest

from app.services.cyber2.merge_set_store import (
    Cyber2MergeSetStore,
    MergeSetStoreError,
)
from app.services.cyber2.iterative_merge_execution import (
    build_iterative_child,
)
from test_cyber2_iterative_merge_input import parent
from test_cyber2_merge_set_store import FakeContainer


def make_store():
    return Cyber2MergeSetStore(
        FakeContainer(),
        "ACME/capture/CaseA",
        content_settings_factory=lambda: {
            "content_type": "application/json"
        },
    )


def make_child():
    return build_iterative_child(
        parent(), ["First Name", "DOB"], ["SSN", "DOB"]
    )


def save_child(store, derived):
    return store.save(
        derived=derived,
        workspace="capture",
        client="ACME",
        project="CaseA",
        approved_mapping_path="approved-mapping.json",
        executed_by="TEST-ADMIN",
    )


def test_child_metadata_persisted_with_integrity():
    store = make_store()
    child = make_child()
    original = deepcopy(child)

    receipt = save_child(store, child)
    saved = store.load(receipt["merge_set_id"])

    assert saved["parent_merge_set_id"] == parent()["merge_set_id"]
    assert saved["pass_number"] == 2
    assert saved["input_working_record_count"] == 2
    assert saved["working_record_count"] == 2
    assert saved["conflict_group_count"] == 1
    assert saved["integrity_sha256"]
    assert child == original


def test_missing_parent_rejected_before_write():
    store = make_store()
    child = make_child()
    del child["parent_merge_set_id"]

    with pytest.raises(MergeSetStoreError):
        save_child(store, child)


def test_invalid_parent_id_rejected_before_write():
    store = make_store()
    child = make_child()
    child["parent_merge_set_id"] = "UNKNOWN"

    with pytest.raises(MergeSetStoreError):
        save_child(store, child)


def test_invalid_pass_number_rejected_before_write():
    store = make_store()
    child = make_child()
    child["pass_number"] = 1

    with pytest.raises(MergeSetStoreError):
        save_child(store, child)
