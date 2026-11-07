import pytest

from apc import detection_job_runner as runner
from apc.stages.pii_phi_detection import (
    IncompleteWorksheetDetection,
)


class FakeDB:
    def init_schema(self):
        pass

    def query(self, *args, **kwargs):
        raise AssertionError(
            "Partial detection must not read final result rows."
        )


def payload():
    return {
        "detection_job_id": "DET-SYNTHETIC",
        "workspace": "capture",
        "client": "synthetic-client",
        "project": "synthetic-project",
        "source_job_id": "JOB-SYNTHETIC",
        "documents": [
            {
                "doc_id": "INSYT000000044.1",
                "text_staged_blob_path": "synthetic/path.txt",
                "detection_mode": "worksheet_triage",
            }
        ],
    }


def invoke(monkeypatch, tmp_path, progress, *, bounded=True):
    monkeypatch.setenv(
        "APC_DETECTION_ROOT",
        str(tmp_path),
    )

    monkeypatch.setattr(
        runner,
        "_seed_source_job",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_download_detection_text",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        runner,
        "_seed_detection_document",
        lambda *args, **kwargs: "FILE-SYNTHETIC",
    )

    def incomplete(*args, **kwargs):
        error = IncompleteWorksheetDetection(
            "Worksheet detection is incomplete; "
            "final classification is prohibited."
        )

        if progress is not None:
            error.checkpoint_progress = progress

        raise error

    monkeypatch.setattr(
        runner,
        "run_pii_phi_detection",
        incomplete,
    )

    return runner.run_data_element_detection_job(
        db=FakeDB(),
        payload=payload(),
        worksheet_executor_factory=lambda **kwargs: None,
        max_chunks_per_document=1 if bounded else None,
    )


def test_verified_partial_returns_continuation(
    monkeypatch, tmp_path
):
    progress = {
        "checkpoint_verified": True,
        "completed_units": 1,
        "total_units": 5,
        "job_complete": False,
    }

    result = invoke(
        monkeypatch,
        tmp_path,
        progress,
    )

    assert result["status"] == "continuation_required"
    assert result["completed_units"] == 1
    assert result["total_units"] == 5
    assert result["checkpoint_verified"] is True


@pytest.mark.parametrize("progress", [
    None,
    {
        "checkpoint_verified": False,
        "completed_units": 1,
        "total_units": 5,
        "job_complete": False,
    },
    {
        "checkpoint_verified": True,
        "completed_units": 5,
        "total_units": 5,
        "job_complete": True,
    },
    {
        "checkpoint_verified": True,
        "completed_units": 1,
        "total_units": 5,
        "job_complete": True,
    },
])
def test_invalid_progress_never_continues(
    monkeypatch, tmp_path, progress
):
    with pytest.raises(
        (RuntimeError, IncompleteWorksheetDetection)
    ):
        invoke(monkeypatch, tmp_path, progress)


def test_unbounded_path_does_not_convert_incomplete(
    monkeypatch, tmp_path
):
    progress = {
        "checkpoint_verified": True,
        "completed_units": 1,
        "total_units": 5,
        "job_complete": False,
    }

    with pytest.raises(IncompleteWorksheetDetection):
        invoke(
            monkeypatch,
            tmp_path,
            progress,
            bounded=False,
        )