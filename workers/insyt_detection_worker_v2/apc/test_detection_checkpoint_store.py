import json

import pytest

from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from apc.detection_checkpoint import (
    CHECKPOINT_COMPLETED,
    DetectionCheckpoint,
)
from apc.detection_checkpoint_store import (
    DetectionCheckpointStore,
)


class FakeBlob:
    def __init__(self, blobs, path):
        self.blobs = blobs
        self.path = path

    def upload_blob(self, data, *, overwrite=False):
        if self.path in self.blobs and not overwrite:
            raise ResourceExistsError("Already exists.")
        self.blobs[self.path] = data

    def download_blob(self):
        if self.path not in self.blobs:
            raise ResourceNotFoundError("Missing.")
        return self

    def readall(self):
        return self.blobs[self.path]

    def get_blob_properties(self):
        if self.path not in self.blobs:
            raise ResourceNotFoundError("Missing.")
        return {"size": len(self.blobs[self.path])}


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, path):
        return FakeBlob(self.blobs, path)


def make_checkpoint(store, **overrides):
    values = {
        "detection_job_id": "DET-TEST001",
        "doc_id": "INSYT000000001",
        "unit_id": "chunk-000001",
        "protocol_fingerprint": "sha256:test",
        "state": CHECKPOINT_COMPLETED,
        "completed_at": "2026-11-06T12:00:00Z",
    }

    values.update(overrides)

    provisional = DetectionCheckpoint(
        result_blob_path="placeholder",
        **values,
    )

    return DetectionCheckpoint(
        result_blob_path=store.result_path(provisional),
        **values,
    )


def test_completed_checkpoint_roundtrip():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    assert store.save_completed(
        checkpoint,
        result_payload={"hits": ["synthetic"]},
    )

    assert store.load_reusable(checkpoint) == checkpoint


def test_duplicate_completion_does_not_overwrite():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    assert store.save_completed(
        checkpoint,
        result_payload={"version": 1},
    )

    assert not store.save_completed(
        checkpoint,
        result_payload={"version": 2},
    )

    stored = json.loads(
        container.blobs[store.result_path(checkpoint)]
    )

    assert stored["version"] == 1


def test_missing_result_cannot_be_reused():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    store.save_completed(
        checkpoint,
        result_payload={"hits": []},
    )

    del container.blobs[store.result_path(checkpoint)]

    assert store.load_reusable(checkpoint) is None


def test_changed_protocol_cannot_reuse_checkpoint():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    store.save_completed(
        checkpoint,
        result_payload={"hits": []},
    )

    changed = make_checkpoint(
        store,
        protocol_fingerprint="sha256:changed",
    )

    assert store.load_reusable(changed) is None


def test_result_path_mismatch_rejected():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = DetectionCheckpoint(
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id="chunk-000001",
        protocol_fingerprint="sha256:test",
        state=CHECKPOINT_COMPLETED,
        result_blob_path="wrong/path.json",
        completed_at="2026-11-06T12:00:00Z",
    )

    with pytest.raises(ValueError):
        store.save_completed(
            checkpoint,
            result_payload={},
        )


def test_unsafe_unit_identifier_rejected():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = DetectionCheckpoint(
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        unit_id="../other",
        protocol_fingerprint="sha256:test",
    )

    with pytest.raises(ValueError):
        store.checkpoint_path(checkpoint)

def test_interrupted_result_write_can_recover():
    """
    A completed result without a checkpoint marker
    must be recoverable on retry if its bytes match.
    """
    container = FakeContainer()

    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    result = {"hits": ["synthetic"]}

    result_bytes = json.dumps(
        result,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    # Simulate worker termination after saving result,
    # but before publishing completion marker.
    container.blobs[
        store.result_path(checkpoint)
    ] = result_bytes

    assert store.load_reusable(checkpoint) is None

    assert store.save_completed(
        checkpoint,
        result_payload=result,
    )

    assert store.load_reusable(checkpoint) == checkpoint


def test_conflicting_orphan_result_is_not_overwritten():
    """
    A retry must never adopt a different worker's
    result artifact as its own completed output.
    """
    container = FakeContainer()

    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    checkpoint = make_checkpoint(store)

    original_result = {"hits": ["original"]}

    original_bytes = json.dumps(
        original_result,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    container.blobs[
        store.result_path(checkpoint)
    ] = original_bytes

    assert not store.save_completed(
        checkpoint,
        result_payload={"hits": ["different"]},
    )

    assert (
        container.blobs[store.result_path(checkpoint)]
        == original_bytes
    )

    assert store.load_reusable(checkpoint) is None

def test_different_rule_versions_can_coexist():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    original = make_checkpoint(
        store,
        protocol_fingerprint="sha256:rules-v1",
    )

    updated = make_checkpoint(
        store,
        protocol_fingerprint="sha256:rules-v2",
    )

    assert (
        store.result_path(original)
        != store.result_path(updated)
    )

    assert (
        store.checkpoint_path(original)
        != store.checkpoint_path(updated)
    )

    assert store.save_completed(
        original,
        result_payload={"rules": "v1"},
    )

    assert store.save_completed(
        updated,
        result_payload={"rules": "v2"},
    )

    assert store.load_reusable(original) == original
    assert store.load_reusable(updated) == updated

    original_result = json.loads(
        container.blobs[store.result_path(original)]
    )

    updated_result = json.loads(
        container.blobs[store.result_path(updated)]
    )

    assert original_result == {"rules": "v1"}
    assert updated_result == {"rules": "v2"}


def test_mismatched_fingerprint_cannot_reuse_result():
    container = FakeContainer()
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    original = make_checkpoint(
        store,
        protocol_fingerprint="sha256:original",
    )

    store.save_completed(
        original,
        result_payload={"hits": ["synthetic"]},
    )

    changed = make_checkpoint(
        store,
        protocol_fingerprint="sha256:changed",
    )

    assert store.load_reusable(changed) is None