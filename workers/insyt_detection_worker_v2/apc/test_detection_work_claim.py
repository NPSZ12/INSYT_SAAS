import pytest

from azure.core.exceptions import ResourceExistsError

from apc.detection_checkpoint import DetectionCheckpoint
from apc.detection_work_claim import DetectionWorkClaimStore


class FakeLease:
    def __init__(self, record):
        self.record = record
        self.active = True
        self.renewals = 0

    def renew(self):
        if not self.active:
            raise RuntimeError("Lease inactive.")
        self.renewals += 1

    def release(self):
        if not self.active:
            raise RuntimeError("Lease already released.")
        self.active = False
        self.record["leased"] = False


class FakeBlob:
    def __init__(self, records, path):
        self.records = records
        self.path = path

    def upload_blob(
        self,
        data,
        *,
        overwrite=False,
        lease=None,
    ):
        record = self.records.get(self.path)

        if record is None:
            self.records[self.path] = {
                "leased": False,
                "owner": None,
                "data": data,
            }
            return

        if not overwrite:
            raise ResourceExistsError("Blob already exists.")

        if (
            lease is None
            or not lease.active
            or not record["leased"]
            or record["owner"] is not lease
        ):
            raise RuntimeError("Lease mismatch.")

        record["data"] = data

    def acquire_lease(self, *, lease_duration):
        record = self.records[self.path]

        if record["leased"]:
            raise ResourceExistsError("Lease already present.")

        record["leased"] = True
        lease = FakeLease(record)
        record["owner"] = lease
        return lease


class FakeContainer:
    def __init__(self):
        self.records = {}

    def get_blob_client(self, path):
        return FakeBlob(self.records, path)


def checkpoint(doc_id="INSYT000000001", unit_id="chunk-000001"):
    return DetectionCheckpoint(
        detection_job_id="DET-TEST001",
        doc_id=doc_id,
        unit_id=unit_id,
        protocol_fingerprint="sha256:test",
    )


def make_store(container):
    return DetectionWorkClaimStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )


def test_first_worker_acquires_claim():
    store = make_store(FakeContainer())
    claim = store.try_acquire(checkpoint())

    assert claim is not None
    assert claim.released is False


def test_second_worker_cannot_claim_same_unit():
    container = FakeContainer()
    worker_a = make_store(container)
    worker_b = make_store(container)

    first = worker_a.try_acquire(checkpoint())

    assert first is not None
    assert worker_b.try_acquire(checkpoint()) is None


def test_claim_can_be_reacquired_after_release():
    store = make_store(FakeContainer())
    first = store.try_acquire(checkpoint())

    first.release()

    assert store.try_acquire(checkpoint()) is not None


def test_lease_can_be_renewed():
    store = make_store(FakeContainer())
    claim = store.try_acquire(checkpoint())

    claim.renew()

    assert claim.lease.renewals == 1


def test_released_lease_cannot_be_renewed():
    store = make_store(FakeContainer())
    claim = store.try_acquire(checkpoint())

    claim.release()

    with pytest.raises(RuntimeError):
        claim.renew()


def test_different_units_can_be_claimed():
    store = make_store(FakeContainer())

    first = store.try_acquire(checkpoint())
    second = store.try_acquire(
        checkpoint(unit_id="chunk-000002")
    )

    assert first is not None
    assert second is not None


def test_invalid_lease_duration_rejected():
    with pytest.raises(ValueError):
        DetectionWorkClaimStore(
            FakeContainer(),
            project_prefix="INSYT_Demo/capture/Test",
            lease_seconds=120,
        )


def test_unsafe_project_prefix_rejected():
    with pytest.raises(ValueError):
        DetectionWorkClaimStore(
            FakeContainer(),
            project_prefix="../capture/Test",
        )

def test_expired_worker_must_not_publish():
    """
    A worker must not retain publication authority
    after losing its Azure Blob lease.

    This establishes the required ownership contract
    before integrating checkpoint publication.
    """
    container = FakeContainer()
    store = make_store(container)
    unit = checkpoint()

    worker_a = store.try_acquire(unit)
    assert worker_a is not None

    # Simulate the original ownership ending.
    worker_a.release()

    worker_b = store.try_acquire(unit)
    assert worker_b is not None

    # Worker A is no longer authorized to publish.
    with pytest.raises(RuntimeError):
        worker_a.assert_active()

    # Worker B still owns the unit.
    worker_b.assert_active()

def test_active_worker_can_publish_completion():
    import json

    container = FakeContainer()
    store = make_store(container)

    claim = store.try_acquire(checkpoint())
    assert claim is not None

    claim.publish_completion({
        "state": "completed",
        "unit_id": "chunk-000001",
    })

    record = container.records[claim.blob_path]

    assert json.loads(record["data"]) == {
        "state": "completed",
        "unit_id": "chunk-000001",
    }


def test_stale_worker_cannot_publish_completion():
    import json

    container = FakeContainer()
    store = make_store(container)
    unit = checkpoint()

    worker_a = store.try_acquire(unit)
    assert worker_a is not None

    worker_a.release()

    worker_b = store.try_acquire(unit)
    assert worker_b is not None

    worker_b.publish_completion({
        "owner": "worker-b",
    })

    with pytest.raises(RuntimeError):
        worker_a.publish_completion({
            "owner": "worker-a",
        })

    record = container.records[worker_b.blob_path]

    assert json.loads(record["data"]) == {
        "owner": "worker-b",
    }


def test_publication_requires_matching_lease():
    container = FakeContainer()
    store = make_store(container)

    worker_a = store.try_acquire(checkpoint())
    worker_b = store.try_acquire(
        checkpoint(unit_id="chunk-000002")
    )

    assert worker_a is not None
    assert worker_b is not None

    # A valid lease from a different work unit
    # must not authorize this write.
    with pytest.raises(RuntimeError):
        worker_a.blob.upload_blob(
            b"invalid",
            overwrite=True,
            lease=worker_b.lease,
        )


def test_publication_rejects_non_json_payload():
    container = FakeContainer()
    store = make_store(container)

    claim = store.try_acquire(checkpoint())

    with pytest.raises(TypeError):
        claim.publish_completion({
            "invalid": {1, 2, 3},
        })