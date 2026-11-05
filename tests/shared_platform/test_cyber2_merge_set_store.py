"""Offline tests for isolated, immutable Cyber2 merge-set storage."""

import copy
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.cyber2.merge_set_store import (
    Cyber2MergeSetStore,
    MergeSetStoreError,
    MergeSetConflict,
)
from test_cyber2_merge_execution import fixture, execute


class FakeBlob:
    def __init__(self, storage, path):
        self.storage = storage
        self.path = path

    def upload_blob(self, data, *, overwrite, content_settings):
        if self.path in self.storage and not overwrite:
            error = RuntimeError("Already exists")
            error.status_code = 409
            raise error

        self.storage[self.path] = bytes(data)

    def download_blob(self):
        return self

    def readall(self):
        return self.storage[self.path]


class FakeContainer:
    def __init__(self):
        self.storage = {}

    def get_blob_client(self, path):
        return FakeBlob(self.storage, path)


def setup():
    container = FakeContainer()

    store = Cyber2MergeSetStore(
        container,
        "ACME/capture/CaseA",
        content_settings_factory=lambda: {
            "content_type": "application/json"
        },
    )

    records, preview = fixture()
    derived = execute(records, preview)

    return container, store, records, derived


def save(store, derived):
    return store.save(
        derived=derived,
        workspace="capture",
        client="ACME",
        project="CaseA",
        approved_mapping_path=(
            "ACME/capture/CaseA/cyber2/"
            "header_mapping/HDR-1/approved_mapping.json"
        ),
        executed_by="TEST-ADMIN",
    )


def test_write_once_versioned_merge_set():
    container, store, records, derived = setup()

    result = save(store, derived)

    assert result["status"] == "completed"
    assert result["merge_set_id"].startswith("MSET-")
    assert result["raw_record_count"] == 4
    assert result["working_record_count"] == 3
    assert len(container.storage) == 1

    path = next(iter(container.storage))
    assert path.startswith(
        "ACME/capture/CaseA/cyber2/merge_sets/MSET-"
    )


def test_saved_set_preserves_real_values_and_provenance():
    _, store, _, derived = setup()
    result = save(store, derived)

    document = store.load(result["merge_set_id"])

    assert document["status"] == "completed"
    assert document["working_record_count"] == 3

    merged = document["working_records"][0]

    assert merged["source_ucids"] == ["R1", "R2"]
    assert merged["cells"]["Street 1"] == (
        "100 Main Street; 200 Main Street"
    )
    assert len(merged["field_provenance"]["Street 1"]) == 2


def test_save_does_not_mutate_raw_or_derived():
    _, store, records, derived = setup()
    before_records = copy.deepcopy(records)
    before_derived = copy.deepcopy(derived)

    save(store, derived)

    assert records == before_records
    assert derived == before_derived


def test_separate_executions_get_separate_ids():
    container, store, _, derived = setup()

    first = save(store, derived)
    second = save(store, derived)

    assert first["merge_set_id"] != second["merge_set_id"]
    assert len(container.storage) == 2


def test_tampered_blob_rejected():
    container, store, _, derived = setup()
    result = save(store, derived)

    path = next(iter(container.storage))
    document = json.loads(container.storage[path])
    document["working_records"][0]["cells"]["Street 1"] = "CHANGED"
    container.storage[path] = json.dumps(document).encode("utf-8")

    with pytest.raises(MergeSetStoreError):
        store.load(result["merge_set_id"])


def test_missing_source_lineage_rejected():
    container, store, _, derived = setup()
    derived["working_records"][0]["field_provenance"].pop("Street 1")

    with pytest.raises(MergeSetStoreError):
        save(store, derived)

    assert not container.storage


def test_duplicate_source_ucid_rejected():
    container, store, _, derived = setup()
    derived["working_records"][1]["source_ucids"] = ["R1"]

    with pytest.raises(MergeSetStoreError):
        save(store, derived)

    assert not container.storage


def test_cross_project_base_path_isolated():
    container, store, _, derived = setup()

    first = save(store, derived)

    other_store = Cyber2MergeSetStore(
        container,
        "ACME/capture/CaseB",
        content_settings_factory=lambda: None,
    )

    with pytest.raises(KeyError):
        other_store.load(first["merge_set_id"])


def test_invalid_merge_set_id_rejected():
    _, store, _, _ = setup()

    with pytest.raises(MergeSetStoreError):
        store.load("../../outside")


def test_write_conflict_does_not_overwrite():
    container, store, _, derived = setup()

    original = save(store, derived)
    path = next(iter(container.storage))
    original_bytes = container.storage[path]

    from unittest.mock import patch

    with patch(
        "app.services.cyber2.merge_set_store.uuid4"
    ) as uuid:
        uuid.return_value.hex = original[
            "merge_set_id"
        ].removeprefix("MSET-").lower()

        with pytest.raises(MergeSetConflict):
            save(store, derived)

    assert container.storage[path] == original_bytes
