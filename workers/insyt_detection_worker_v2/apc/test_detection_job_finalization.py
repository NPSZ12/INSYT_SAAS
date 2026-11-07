import pytest

from azure.core.exceptions import ResourceExistsError

from apc.detection_job_finalization import (
    finalize_detection_job_once,
)


class FakeLease:
    def __init__(self, record):
        self.record = record
        self.active = True

    def renew(self):
        if not self.active:
            raise RuntimeError("Lease lost.")

    def release(self):
        self.active = False
        self.record["owner"] = None


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
                "data": data,
                "owner": None,
            }
            return

        if not overwrite:
            raise ResourceExistsError("Already exists.")

        if record["owner"] is not lease or not lease.active:
            raise RuntimeError("Invalid lease.")

        record["data"] = data

    def acquire_lease(self, *, lease_duration):
        record = self.records[self.path]

        if record["owner"] is not None:
            raise ResourceExistsError("Already leased.")

        lease = FakeLease(record)
        record["owner"] = lease
        return lease

    def download_blob(self):
        return self

    def readall(self):
        return self.records[self.path]["data"]


class FakeContainer:
    def __init__(self):
        self.records = {}

    def get_blob_client(self, path):
        return FakeBlob(self.records, path)


def make_claim_store(container):
    from apc.detection_work_claim import (
        DetectionWorkClaimStore,
    )

    return DetectionWorkClaimStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )


def run_once(store, verify, finalize):
    return finalize_detection_job_once(
        claim_store=store,
        detection_job_id="DET-TEST001",
        protocol_fingerprint="sha256:job-identity",
        verify_all_completed=verify,
        finalize=finalize,
    )


def test_finalization_runs_once_after_duplicate_delivery():
    store = make_claim_store(FakeContainer())
    calls = []

    def finalize(claim):
        claim.assert_active()
        calls.append("finalized")

    assert run_once(store, lambda: True, finalize) is True
    assert run_once(store, lambda: True, finalize) is False
    assert calls == ["finalized"]


def test_incomplete_job_cannot_finalize():
    store = make_claim_store(FakeContainer())
    calls = []

    with pytest.raises(RuntimeError, match="incomplete"):
        run_once(
            store,
            lambda: False,
            lambda claim: calls.append("finalized"),
        )

    assert calls == []


def test_finalization_failure_allows_retry():
    store = make_claim_store(FakeContainer())
    calls = []

    def fail(claim):
        calls.append("attempt")
        raise RuntimeError("Synthetic failure")

    with pytest.raises(RuntimeError, match="Synthetic failure"):
        run_once(store, lambda: True, fail)

    assert run_once(
        store,
        lambda: True,
        lambda claim: calls.append("success"),
    ) is True

    assert calls == ["attempt", "success"]


def test_second_worker_cannot_finalize_during_active_lease():
    store = make_claim_store(FakeContainer())
    calls = []

    def finalize(claim):
        competing = run_once(
            store,
            lambda: True,
            lambda other: calls.append("competing"),
        )

        assert competing is False
        calls.append("owner")

    assert run_once(store, lambda: True, finalize) is True
    assert calls == ["owner"]