import json

import pytest
from azure.core.exceptions import ResourceExistsError

from apc.detection_publication_snapshot import (
    load_or_create_publication_snapshot,
)


class FakeBlob:
    def __init__(self):
        self.data = None

    def exists(self):
        return self.data is not None

    def upload_blob(self, data, *, overwrite):
        if self.data is not None and not overwrite:
            raise ResourceExistsError("Already exists")
        self.data = bytes(data)

    def download_blob(self):
        if self.data is None:
            raise FileNotFoundError()
        return self

    def readall(self):
        return self.data


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, path):
        return self.blobs.setdefault(path, FakeBlob())


def plan(timestamp="first"):
    return {
        "result": {
            "status": "completed",
            "detection_job_id": "DET-SYNTHETIC",
            "completed_at": timestamp,
        },
        "writes": [
            {
                "blob_path": "synthetic/results/summary.json",
                "payload": {"completed_at": timestamp},
                "overwrite": False,
            },
            {
                "blob_path": "synthetic/results/documents.json",
                "payload": [{"doc_id": "DOC-A"}],
                "overwrite": False,
            },
        ],
    }


def snapshot(container, builder, owner=lambda: None):
    return load_or_create_publication_snapshot(
        container=container,
        blob_path="synthetic/publication_snapshot.json",
        detection_job_id="DET-SYNTHETIC",
        build_plan=builder,
        assert_owner=owner,
    )


def test_snapshot_survives_changed_retry_data():
    container = FakeContainer()
    calls = []

    def first():
        calls.append("first")
        return plan("first")

    original = snapshot(container, first)

    def changed():
        calls.append("changed")
        return plan("second")

    replay = snapshot(container, changed)

    assert original == replay
    assert calls == ["first"]
    assert replay["result"]["completed_at"] == "first"


def test_owner_failure_prevents_creation():
    container = FakeContainer()

    def lost():
        raise RuntimeError("Lease lost")

    with pytest.raises(RuntimeError, match="Lease lost"):
        snapshot(container, lambda: plan(), lost)

    assert all(
        blob.data is None
        for blob in container.blobs.values()
    )


def test_corrupt_snapshot_fails_closed():
    container = FakeContainer()
    snapshot(container, lambda: plan())

    blob = container.blobs[
        "synthetic/publication_snapshot.json"
    ]

    saved = json.loads(blob.data)
    saved["plan"]["result"]["completed_at"] = "corrupted"
    blob.data = json.dumps(saved).encode("utf-8")

    with pytest.raises(ValueError, match="digest"):
        snapshot(container, lambda: plan("replacement"))


def test_duplicate_publication_path_rejected():
    container = FakeContainer()

    def duplicate():
        result = plan()
        result["writes"].append(dict(result["writes"][0]))
        return result

    with pytest.raises(ValueError, match="Duplicate"):
        snapshot(container, duplicate)

    assert all(
        blob.data is None
        for blob in container.blobs.values()
    )


def test_invalid_terminal_result_rejected():
    container = FakeContainer()

    def incomplete():
        result = plan()
        result["result"]["status"] = "continuation_required"
        return result

    with pytest.raises(ValueError, match="terminal"):
        snapshot(container, incomplete)