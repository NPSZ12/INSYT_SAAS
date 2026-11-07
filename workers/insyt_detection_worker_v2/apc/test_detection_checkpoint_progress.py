from pathlib import Path

import pytest

from apc.detection_checkpoint_progress import (
    verify_detection_checkpoint_progress,
)


class FakeExecutor:
    def __init__(self, completed):
        self.completed = set(completed)
        self.executed = 0
        self.restored = []

    def load_completed(self, unit):
        self.restored.append(unit.unit_id)

        if unit.unit_id in self.completed:
            return {"candidates": []}

        return None

    def __call__(self, unit):
        self.executed += 1
        raise AssertionError("Detection must not execute")


def make_sheet(tmp_path, name, executor, rows=5):
    path = tmp_path / f"{name}.csv"
    path.write_text(
        "synthetic,data\n" * rows,
        encoding="utf-8",
        newline="\n",
    )

    return {
        "doc_id": name,
        "path": path,
        "executor": executor,
    }


def verify(sheets):
    return verify_detection_checkpoint_progress(
        worksheets=sheets,
        max_chars=100000,
        max_rows=2,
    )


def test_counts_completed_and_missing_chunks(tmp_path):
    a = FakeExecutor({"chunk-000001", "chunk-000002"})
    b = FakeExecutor({"chunk-000001"})

    result = verify([
        make_sheet(tmp_path, "DOC-A", a),
        make_sheet(tmp_path, "DOC-B", b),
    ])

    assert result["total_units"] == 6
    assert result["completed_units"] == 3
    assert result["job_complete"] is False
    assert result["checkpoint_verified"] is True
    assert a.executed == b.executed == 0


def test_complete_population(tmp_path):
    executor = FakeExecutor({
        "chunk-000001",
        "chunk-000002",
        "chunk-000003",
    })

    result = verify([
        make_sheet(tmp_path, "DOC-A", executor)
    ])

    assert result["total_units"] == 3
    assert result["completed_units"] == 3
    assert result["job_complete"] is True


def test_missing_source_fails_closed(tmp_path):
    executor = FakeExecutor(set())

    entry = make_sheet(tmp_path, "DOC-A", executor)
    Path(entry["path"]).unlink()

    with pytest.raises(FileNotFoundError):
        verify([entry])


def test_duplicate_documents_rejected(tmp_path):
    executor = FakeExecutor(set())
    entry = make_sheet(tmp_path, "DOC-A", executor)

    with pytest.raises(ValueError, match="duplicate"):
        verify([entry, entry])


def test_missing_restoration_interface_rejected(tmp_path):
    entry = make_sheet(
        tmp_path, "DOC-A", object()
    )

    with pytest.raises(TypeError):
        verify([entry])


def test_invalid_result_rejected(tmp_path):
    class CorruptExecutor:
        def load_completed(self, unit):
            return ["invalid"]

    entry = make_sheet(
        tmp_path, "DOC-A", CorruptExecutor()
    )

    with pytest.raises(ValueError):
        verify([entry])


def test_empty_population_rejected():
    with pytest.raises(ValueError):
        verify([])