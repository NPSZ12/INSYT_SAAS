import json

import pytest

from app.workers import detection_worker as worker
from apc import detection_continuation_queue as queue_module


class FakeDB:
    def __init__(self, path):
        self.path = path

    def close(self):
        pass


def make_payload(continuation=False):
    payload = {
        "detection_job_id": "DET-SYNTHETIC",
        "source_job_id": "JOB-SYNTHETIC",
        "workspace": "capture",
        "client": "synthetic-client",
        "project": "synthetic-project",
        "status_blob_path": "synthetic/status.json",
        "documents": [
            {
                "doc_id": "INSYT000000044.1",
                "text_staged_blob_path": "synthetic/a.txt",
            },
        ],
    }

    if continuation:
        payload["detection_continuation"] = True

    return payload


def setup_worker(monkeypatch, result):
    statuses = []
    messages = []

    monkeypatch.setattr(
        worker,
        "_validate_payload",
        lambda payload: (
            "DET-SYNTHETIC",
            "capture",
            "synthetic-client",
            "synthetic-project",
            "synthetic/status.json",
        ),
    )

    monkeypatch.setattr(
        worker,
        "_db_path",
        lambda job_id: "synthetic.db",
    )

    monkeypatch.setattr(worker, "LedgerDB", FakeDB)

    def status_update(**kwargs):
        statuses.append(kwargs)

    monkeypatch.setattr(
        worker,
        "_update_status",
        status_update,
    )

    def run_job(**kwargs):
        return result

    monkeypatch.setattr(
        worker,
        "run_data_element_detection_job",
        run_job,
    )

    monkeypatch.setattr(
        queue_module,
        "enqueue_detection_continuation",
        lambda payload: messages.append(dict(payload)),
    )

    monkeypatch.delenv(
        "INSYT_DETECTION_BOUNDED_ENABLED",
        raising=False,
    )

    monkeypatch.delenv(
        "INSYT_DETECTION_WORKSHEET_CHECKPOINTS_ENABLED",
        raising=False,
    )

    return statuses, messages


PARTIAL = {
    "status": "continuation_required",
    "checkpoint_verified": True,
    "completed_units": 1,
    "total_units": 5,
    "job_complete": False,
}


def test_initial_invocation_queues_without_finalizing(monkeypatch):
    statuses, messages = setup_worker(monkeypatch, PARTIAL)

    worker.process_detection_message(
        json.dumps(make_payload())
    )

    assert len(messages) == 1

    assert any(
        item["stage"] == "processing_detection"
        for item in statuses
    )

    assert not any(
        item["stage"] == "finalizing_detection"
        or item["status"] in {
            "completed",
            "completed_with_exceptions",
        }
        for item in statuses
    )


def test_continuation_does_not_reset_progress(monkeypatch):
    statuses, messages = setup_worker(monkeypatch, PARTIAL)

    worker.process_detection_message(
        json.dumps(make_payload(continuation=True))
    )

    assert len(messages) == 1

    assert not any(
        item["stage"] in {
            "starting",
            "preparing_detection",
        }
        for item in statuses
    )

    processing = [
        item for item in statuses
        if item["stage"] == "processing_detection"
    ]

    assert len(processing) == 1
    assert processing[0]["progress_pct"] > 15


@pytest.mark.parametrize("invalid", [
    {
        "status": "continuation_required",
        "checkpoint_verified": False,
        "completed_units": 1,
        "total_units": 5,
    },
    {
        "status": "continuation_required",
        "checkpoint_verified": True,
        "completed_units": 5,
        "total_units": 5,
    },
])
def test_invalid_progress_never_enqueues(monkeypatch, invalid):
    statuses, messages = setup_worker(monkeypatch, invalid)

    with pytest.raises(RuntimeError):
        worker.process_detection_message(
            json.dumps(make_payload(continuation=True))
        )

    assert messages == []

    assert not any(
        item["status"] == "completed"
        for item in statuses
    )


def test_queue_failure_does_not_report_completion(monkeypatch):
    statuses, messages = setup_worker(monkeypatch, PARTIAL)

    def fail_enqueue(payload):
        raise RuntimeError("Synthetic queue failure")

    monkeypatch.setattr(
        queue_module,
        "enqueue_detection_continuation",
        fail_enqueue,
    )

    with pytest.raises(
        RuntimeError,
        match="Synthetic queue failure",
    ):
        worker.process_detection_message(
            json.dumps(make_payload(continuation=True))
        )

    assert messages == []

    assert not any(
        item["status"] == "completed"
        for item in statuses
    )