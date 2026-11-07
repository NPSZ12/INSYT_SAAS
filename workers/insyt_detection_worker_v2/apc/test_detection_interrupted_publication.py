import json

import pytest
from azure.core.exceptions import ResourceExistsError

from apc import detection_job_runner as runner
from apc.detection_publication_guard import (
    publish_detection_once,
)
from apc.detection_publication_snapshot import (
    load_or_create_publication_snapshot,
)


JOB = "DET-SYNTHETIC"
BASE = "synthetic/capture/project"
PREFIX = (
    f"{BASE}/processing_center/detection/jobs/{JOB}"
)


class FakeBlob:
    def __init__(self, data=None):
        self.data = data
        self.fail_once = False
        self.writes = 0

    def exists(self):
        return self.data is not None

    def upload_blob(
        self, data, *, overwrite, content_settings=None,
    ):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Synthetic interrupted upload")

        if self.data is not None and not overwrite:
            raise ResourceExistsError("Already exists")

        self.data = bytes(data)
        self.writes += 1

    def download_blob(self):
        return self

    def readall(self):
        if self.data is None:
            raise FileNotFoundError()
        return self.data


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, path):
        return self.blobs.setdefault(
            path, FakeBlob()
        )


class FakeService:
    def __init__(self, container):
        self.container = container

    def get_container_client(self, name):
        return self.container


class FakeClaim:
    def __init__(self, blob):
        self.blob = blob
        self.released = False
        self.renewals = 0

    def assert_active(self):
        if self.released:
            raise RuntimeError("Claim released")
        self.renewals += 1

    def renew(self):
        self.assert_active()

    def publish_completion(self, payload):
        self.assert_active()
        self.blob.data = json.dumps(
            payload
        ).encode("utf-8")

    def release(self):
        self.released = True


class FakeStore:
    lease_seconds = 60
    project_prefix = BASE

    def __init__(self):
        self.container = FakeContainer()
        self.coordination_blob = FakeBlob(b"")
        self.claims = []
        self.acquisitions = 0

    def try_acquire(self, checkpoint):
        self.acquisitions += 1
        claim = FakeClaim(
            self.coordination_blob
        )
        self.claims.append(claim)
        return claim


def make_plan(timestamp):
    return {
        "result": {
            "status": "completed",
            "detection_job_id": JOB,
            "completed_at": timestamp,
        },
        "writes": [
            {
                "blob_path": (
                    f"{PREFIX}/results/summary.json"
                ),
                "payload": {
                    "completed_at": timestamp,
                    "documents_scanned": 5,
                },
                "overwrite": False,
            },
            {
                "blob_path": (
                    f"{PREFIX}/results/documents.json"
                ),
                "payload": [
                    {"doc_id": f"DOC-{i}"}
                    for i in range(5)
                ],
                "overwrite": False,
            },
            {
                "blob_path": (
                    f"{BASE}/processing_center/"
                    "detection/documents/DOC-0.json"
                ),
                "payload": {
                    "latest_detection_job_id": JOB
                },
                "overwrite": True,
            },
        ],
    }


def publish(store, timestamp, constructed):
    def publication(claim):
        def build_plan():
            constructed.append(timestamp)
            return make_plan(timestamp)

        plan = load_or_create_publication_snapshot(
            container=store.container,
            blob_path=(
                f"{PREFIX}/publication_snapshot.json"
            ),
            detection_job_id=JOB,
            build_plan=build_plan,
            assert_owner=claim.assert_active,
        )

        for item in plan["writes"]:
            claim.assert_active()
            runner._write_processing_json(
                item["blob_path"],
                item["payload"],
                overwrite=item["overwrite"],
            )

        return plan["result"]

    return publish_detection_once(
        detection_job_id=JOB,
        claim_store=store,
        publish_results=lambda: (_ for _ in ()).throw(
            AssertionError("Unguarded publication")
        ),
        publish_results_with_claim=publication,
    )


def setup(monkeypatch):
    store = FakeStore()

    monkeypatch.setattr(
        runner,
        "_processing_blob_service",
        lambda: FakeService(store.container),
    )
    monkeypatch.setattr(
        runner,
        "_processing_container",
        lambda: "synthetic-processing",
    )
    monkeypatch.setattr(
        runner,
        "_processing_account",
        lambda: "synthetic-account",
    )

    return store


def test_interrupted_publication_recovers_original(
    monkeypatch,
):
    store = setup(monkeypatch)
    constructed = []

    second_path = (
        f"{PREFIX}/results/documents.json"
    )

    store.container.get_blob_client(
        second_path
    ).fail_once = True

    with pytest.raises(
        RuntimeError,
        match="Synthetic interrupted upload",
    ):
        publish(store, "first-time", constructed)

    # First output exists, but publication is not complete.
    summary = store.container.get_blob_client(
        f"{PREFIX}/results/summary.json"
    )

    assert summary.data is not None
    assert store.coordination_blob.data == b""
    assert store.claims[0].released is True

    initial_bytes = summary.data

    # A later invocation has fresh timestamps, but
    # must replay the original durable snapshot.
    recovered = publish(
        store, "changed-time", constructed
    )

    assert recovered["completed_at"] == "first-time"
    assert constructed == ["first-time"]
    assert summary.data == initial_bytes
    assert summary.writes == 1

    documents = store.container.get_blob_client(
        second_path
    )

    assert documents.data is not None
    assert documents.writes == 1

    saved = json.loads(
        store.coordination_blob.data
    )

    assert saved["state"] == "completed"
    assert saved["result"] == recovered

    prior_counts = {
        key: blob.writes
        for key, blob in store.container.blobs.items()
    }

    # Duplicate delivery must reuse durable completion.
    duplicate = publish(
        store, "third-time", constructed
    )

    assert duplicate == recovered
    assert constructed == ["first-time"]
    assert prior_counts == {
        key: blob.writes
        for key, blob in store.container.blobs.items()
    }
    assert all(c.released for c in store.claims)


def test_conflicting_immutable_result_blocks_commit(
    monkeypatch,
):
    store = setup(monkeypatch)
    constructed = []

    path = f"{PREFIX}/results/summary.json"
    blob = store.container.get_blob_client(path)
    blob.data = b'{"unexpected":"prior-result"}'

    with pytest.raises(
        RuntimeError,
        match="Immutable detection result conflict",
    ):
        publish(store, "first-time", constructed)

    assert blob.data == b'{"unexpected":"prior-result"}'
    assert store.coordination_blob.data == b""
    assert all(c.released for c in store.claims)