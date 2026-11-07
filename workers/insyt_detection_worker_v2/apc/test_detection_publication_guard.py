import json

import pytest

from apc.detection_publication_guard import (
    PublicationBusy,
    publish_detection_once,
)


class FakeBlob:
    def __init__(self):
        self.data = b""

    def download_blob(self):
        return self

    def readall(self):
        return self.data


class FakeClaim:
    def __init__(self, blob):
        self.blob = blob
        self.released = False
        self.verified = 0

    def renew(self):
        self.verified += 1

    def assert_active(self):
        self.verified += 1

    def publish_completion(self, payload):
        self.blob.data = json.dumps(
            payload
        ).encode("utf-8")

    def release(self):
        self.released = True


class FakeStore:
    def __init__(self):
        self.blob = FakeBlob()
        self.claims = []
        self.busy = False

    def try_acquire(self, checkpoint):
        if self.busy:
            return None

        claim = FakeClaim(self.blob)
        self.claims.append(claim)
        return claim


def result():
    return {
        "status": "completed",
        "detection_job_id": "DET-SYNTHETIC",
        "documents_scanned": 5,
    }


def invoke(store, publisher):
    return publish_detection_once(
        detection_job_id="DET-SYNTHETIC",
        claim_store=store,
        publish_results=publisher,
    )


def test_first_publication_writes_completion():
    store = FakeStore()
    calls = []

    def publisher():
        calls.append(1)
        return result()

    output = invoke(store, publisher)

    assert output == result()
    assert len(calls) == 1
    assert store.claims[0].released is True

    saved = json.loads(store.blob.data)

    assert saved["state"] == "completed"
    assert saved["result"] == result()


def test_duplicate_delivery_reuses_completion():
    store = FakeStore()
    calls = []

    def publisher():
        calls.append(1)
        return result()

    first = invoke(store, publisher)
    second = invoke(store, publisher)

    assert first == second
    assert len(calls) == 1
    assert len(store.claims) == 2


def test_competing_publication_does_not_run():
    store = FakeStore()
    store.busy = True

    executed = []

    with pytest.raises(PublicationBusy):
        invoke(
            store,
            lambda: executed.append(1),
        )

    assert executed == []


def test_publisher_failure_does_not_complete():
    store = FakeStore()

    def fail():
        raise RuntimeError("Synthetic publication failure")

    with pytest.raises(
        RuntimeError,
        match="Synthetic publication failure",
    ):
        invoke(store, fail)

    assert store.blob.data == b""
    assert store.claims[0].released is True


def test_nonterminal_publication_rejected():
    store = FakeStore()

    with pytest.raises(ValueError):
        invoke(
            store,
            lambda: {
                "status": "continuation_required",
                "detection_job_id": "DET-SYNTHETIC",
            },
        )

    assert store.blob.data == b""


def test_corrupt_completion_fails_closed():
    store = FakeStore()
    store.blob.data = b'{"state":"completed"}'

    with pytest.raises(ValueError):
        invoke(store, result)

    assert store.claims[0].released is True

def test_lease_renewal_failure_blocks_completion():
    store = FakeStore()

    def fail_renew():
        raise RuntimeError("Synthetic lease lost")

    def publisher():
        claim = store.claims[-1]
        claim.renew = fail_renew
        # Ensure the heartbeat runs before returning.
        import time
        time.sleep(1.1)
        return result()

    store.lease_seconds = 15

    # Accelerate the heartbeat only in this test.
    import threading
    original_wait = threading.Event.wait

    def accelerated_wait(self, timeout=None):
        if timeout is not None:
            timeout = min(timeout, 0.02)
        return original_wait(self, timeout)

    from unittest.mock import patch

    with patch.object(threading.Event,
                      "wait", accelerated_wait):
        with pytest.raises(RuntimeError,
                           match="renewal failed"):
            invoke(store, publisher)

    assert store.blob.data == b''
    assert store.claims[0].released is True
