import json

import pytest

from apc.detection_continuation_queue import (
    enqueue_detection_continuation,
)


class FakeQueue:
    def __init__(self):
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)


def test_continuation_preserves_original_payload():
    queue = FakeQueue()

    payload = {
        "detection_job_id": "DET-SYNTHETIC",
        "workspace": "capture",
        "client": "synthetic-client",
        "project": "synthetic-project",
        "source_job_id": "JOB-SYNTHETIC",
        "documents": [
            {"doc_id": "INSYT000000044.1"},
            {"doc_id": "INSYT000000045.1"},
        ],
    }

    original = json.loads(json.dumps(payload))

    enqueue_detection_continuation(
        payload,
        queue_client=queue,
    )

    assert payload == original
    assert len(queue.messages) == 1

    # The existing Function trigger expects plain JSON.
    decoded = json.loads(queue.messages[0])

    assert decoded["detection_continuation"] is True
    assert decoded["detection_job_id"] == "DET-SYNTHETIC"
    assert decoded["documents"] == payload["documents"]
    assert decoded["source_job_id"] == "JOB-SYNTHETIC"


def test_missing_job_id_rejected():
    queue = FakeQueue()

    with pytest.raises(ValueError):
        enqueue_detection_continuation(
            {"documents": []},
            queue_client=queue,
        )

    assert queue.messages == []


def test_oversized_message_rejected():
    queue = FakeQueue()

    with pytest.raises(ValueError):
        enqueue_detection_continuation(
            {
                "detection_job_id": "DET-SYNTHETIC",
                "data": "X" * 70000,
            },
            queue_client=queue,
        )

    assert queue.messages == []


def test_queue_failure_propagates():
    class FailingQueue:
        def send_message(self, message):
            raise RuntimeError("Synthetic queue failure")

    with pytest.raises(
        RuntimeError,
        match="Synthetic queue failure",
    ):
        enqueue_detection_continuation(
            {"detection_job_id": "DET-SYNTHETIC"},
            queue_client=FailingQueue(),
        )


def test_unicode_message_uses_utf8_byte_limit():
    queue = FakeQueue()

    with pytest.raises(ValueError):
        enqueue_detection_continuation(
            {
                "detection_job_id": "DET-SYNTHETIC",
                "data": "\u00e9" * 40000,
            },
            queue_client=queue,
        )

    assert queue.messages == []