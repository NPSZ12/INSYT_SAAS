"""C2 storage replay, isolation, and integrity tests."""

from copy import deepcopy
import json

import pytest

from app.services.cyber2.c2_transfer_store import (
    C2TransferConflict,
    C2TransferStoreError,
    Cyber2C2TransferStore,
)


class BlobError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class Reader:
    def __init__(self, payload):
        self.payload = payload

    def readall(self):
        return self.payload


class Blob:
    def __init__(self, container, path):
        self.container = container
        self.path = path

    def upload_blob(self, data, *, overwrite, content_settings):
        assert overwrite is False
        if self.path in self.container.data:
            raise BlobError(409)
        self.container.data[self.path] = data

    def download_blob(self):
        if self.path not in self.container.data:
            raise BlobError(404)
        return Reader(self.container.data[self.path])


class Container:
    def __init__(self):
        self.data = {}

    def get_blob_client(self, path):
        return Blob(self, path)


def fixture(container=None, *, project="Payroll"):
    container = container or Container()
    store = Cyber2C2TransferStore(
        container,
        f"capture/Demo/{project}",
        workspace="capture",
        client="Demo",
        project=project,
        content_settings_factory=lambda: object(),
    )
    projection = {
        "schema_version": 1,
        "workspace": "capture",
        "client": "Demo",
        "project": project,
        "header_set_id": "HDRSET-ABC123",
        "merge_set_id": "MSET-" + "A" * 32,
        "merge_integrity_sha256": "b" * 64,
        "headers": ["Doc ID", "First Name"],
        "working_record_count": 1,
        "original_source_record_count": 2,
        "rows": [{
            "id": "C2-1",
            "Doc ID": "DOC1; DOC2",
            "First Name": "Alex",
        }],
        "records": [{
            "c2_record_id": "C2-1",
            "source_ucids": ["U1", "U2"],
            "source_doc_ids": ["DOC1", "DOC2"],
            "cells": {"First Name": "Alex"},
            "field_provenance": {
                "First Name": [
                    {"ucid": "U1", "original_value": "Alex"},
                    {"ucid": "U2", "original_value": "Alex"},
                ],
            },
        }],
    }
    return container, store, projection


def test_save_and_read_preserve_original_evidence():
    container, store, projection = fixture()
    original = deepcopy(projection)

    result = store.save(projection, authorized_by="admin")

    assert result["status"] == "transferred"
    assert store.display("HDRSET-ABC123")["rows"][0][
        "First Name"
    ] == "Alex"

    saved = store.load("HDRSET-ABC123")
    assert saved["projection"] == original
    assert saved["projection"]["records"][0][
        "source_ucids"
    ] == ["U1", "U2"]
    assert projection == original
    assert len(container.data) == 1


def test_exact_replay_does_not_duplicate():
    container, store, projection = fixture()
    assert store.save(
        projection, authorized_by="admin"
    )["status"] == "transferred"

    result = store.save(projection, authorized_by="admin")

    assert result["status"] == "already_transferred"
    assert len(container.data) == 1


def test_other_merge_set_cannot_overwrite_snapshot():
    container, store, projection = fixture()
    store.save(projection, authorized_by="admin")

    replacement = deepcopy(projection)
    replacement["merge_set_id"] = "MSET-" + "C" * 32

    with pytest.raises(C2TransferConflict):
        store.save(replacement, authorized_by="admin")

    assert store.load("HDRSET-ABC123")[
        "merge_set_id"
    ] == projection["merge_set_id"]


def test_read_rejects_corrupted_payload():
    container, store, projection = fixture()
    store.save(projection, authorized_by="admin")

    path = next(iter(container.data))
    document = json.loads(container.data[path])
    document["projection"]["records"][0][
        "source_ucids"
    ] = ["REPLACED"]
    container.data[path] = json.dumps(document).encode()

    with pytest.raises(
        C2TransferStoreError, match="integrity"
    ):
        store.load("HDRSET-ABC123")


def test_project_isolation():
    container, store, projection = fixture()
    store.save(projection, authorized_by="admin")

    _, other, _ = fixture(container, project="Other")
    assert other.load("HDRSET-ABC123") is None


def test_missing_snapshot_returns_none():
    _, store, _ = fixture()
    assert store.load("HDRSET-ABC123") is None


def test_missing_actor_rejected():
    _, store, projection = fixture()
    with pytest.raises(C2TransferStoreError):
        store.save(projection, authorized_by="")


def test_wrong_project_projection_rejected():
    _, store, projection = fixture()
    projection["project"] = "Other"
    with pytest.raises(C2TransferStoreError):
        store.save(projection, authorized_by="admin")


def test_invalid_header_set_identifier_rejected():
    _, store, projection = fixture()
    projection["header_set_id"] = "../OTHER"
    with pytest.raises(C2TransferStoreError):
        store.save(projection, authorized_by="admin")


def test_storage_errors_do_not_look_like_empty_table():
    class FailingContainer:
        def get_blob_client(self, path):
            class FailingBlob:
                def download_blob(self):
                    raise BlobError(503)
            return FailingBlob()

    store = Cyber2C2TransferStore(
        FailingContainer(),
        "capture/Demo/Payroll",
        workspace="capture",
        client="Demo",
        project="Payroll",
    )

    with pytest.raises(BlobError):
        store.load("HDRSET-ABC123")
