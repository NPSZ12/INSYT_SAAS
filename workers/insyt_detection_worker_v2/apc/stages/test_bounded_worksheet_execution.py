import pytest

from apc.stages import pii_phi_detection as stage


def empty_result(unit):
    return {
        "candidates": [],
        "azure_candidate_count": 0,
        "structured_candidate_count": 0,
        "merged_candidate_count": 0,
    }


def run(path, *, limit=None, executor=empty_result):
    return stage._run_worksheet_triage_engine(
        path=path,
        include_phi=True,
        protocol_name=None,
        protocol_version=None,
        enable_azure=False,
        structured_rules=[],
        chunk_executor=executor,
        max_chunks=limit,
    )


def test_bounded_stops_before_second_chunk(
    tmp_path, monkeypatch
):
    path = tmp_path / "worksheet.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    calls = []

    def executor(unit):
        calls.append(unit.unit_id)
        return empty_result(unit)

    result = run(
        path, limit=1, executor=executor
    )

    assert calls == ["chunk-000001"]
    assert result["scan_complete"] is False
    assert result["rows_scanned"] == 500
    assert result["new_chunks_processed"] == 1


def test_exact_eof_is_complete(
    tmp_path, monkeypatch
):
    path = tmp_path / "worksheet.csv"
    path.write_text(
        "synthetic,data\n" * 500,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    result = run(path, limit=1)

    assert result["scan_complete"] is True
    assert result["rows_scanned"] == 500
    assert result["new_chunks_processed"] == 1


def test_unbounded_behavior_preserved(
    tmp_path, monkeypatch
):
    path = tmp_path / "worksheet.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    result = run(path)

    assert result["scan_complete"] is True
    assert result["rows_scanned"] == 1001
    assert result["new_chunks_processed"] == 3


@pytest.mark.parametrize(
    "limit", [-1, True, 1.5]
)
def test_invalid_limit_rejected(tmp_path, limit):
    path = tmp_path / "worksheet.csv"
    path.write_text("a,b\n", encoding="utf-8")

    with pytest.raises(ValueError):
        run(path, limit=limit)


def test_limit_requires_chunk_executor(tmp_path):
    path = tmp_path / "worksheet.csv"
    path.write_text("a,b\n", encoding="utf-8")

    with pytest.raises(ValueError):
        stage._run_worksheet_triage_engine(
            path=path,
            include_phi=True,
            protocol_name=None,
            protocol_version=None,
            enable_azure=False,
            structured_rules=[],
            max_chunks=1,
        )

def test_completed_chunks_do_not_consume_new_work_budget(
    tmp_path, monkeypatch
):
    path = tmp_path / "checkpoint_recovery.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    class CheckpointExecutor:
        def __init__(self):
            self.new_work = []
            self.restored = []

        def load_completed(self, unit):
            if unit.unit_id == "chunk-000001":
                self.restored.append(unit.unit_id)
                return empty_result(unit)
            return None

        def __call__(self, unit):
            if unit.unit_id == "chunk-000001":
                return empty_result(unit)

            self.new_work.append(unit.unit_id)
            return empty_result(unit)

    executor = CheckpointExecutor()

    result = run(
        path,
        limit=1,
        executor=executor,
    )

    assert executor.new_work == ["chunk-000002"]
    assert executor.restored == ["chunk-000001"]

    # Chunk three remains unfinished.
    assert result["scan_complete"] is False
    assert result["rows_scanned"] == 1000
    assert result["new_chunks_processed"] == 1


def test_restored_chunks_allow_eof_with_one_new_unit(
    tmp_path, monkeypatch
):
    path = tmp_path / "checkpoint_finish.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    class CheckpointExecutor:
        def __init__(self):
            self.new_work = []

        def load_completed(self, unit):
            if unit.unit_id in {
                "chunk-000001",
                "chunk-000002",
            }:
                return empty_result(unit)
            return None

        def __call__(self, unit):
            if self.load_completed(unit) is not None:
                return empty_result(unit)
            self.new_work.append(unit.unit_id)
            return empty_result(unit)

    executor = CheckpointExecutor()

    result = run(
        path, limit=1, executor=executor
    )

    assert executor.new_work == ["chunk-000003"]
    assert result["scan_complete"] is True
    assert result["rows_scanned"] == 1001
    assert result["new_chunks_processed"] == 1



def test_zero_budget_restores_without_executor_calls(
    tmp_path, monkeypatch
):
    path = tmp_path / "restored.csv"
    path.write_text("a,b\n" * 1001, encoding="utf-8")

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    class Executor:
        def __init__(self):
            self.executed = []

        def load_completed(self, unit):
            return empty_result(unit)

        def __call__(self, unit):
            self.executed.append(unit.unit_id)
            raise AssertionError("Cached chunk was executed")

    executor = Executor()
    result = run(path, limit=0, executor=executor)

    assert executor.executed == []
    assert result["scan_complete"] is True
    assert result["new_chunks_processed"] == 0
    assert result["rows_scanned"] == 1001


def test_zero_budget_stops_at_first_unfinished_chunk(
    tmp_path, monkeypatch
):
    path = tmp_path / "unfinished.csv"
    path.write_text("a,b\n" * 1001, encoding="utf-8")

    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 500
    )

    class Executor:
        def __init__(self):
            self.executed = []

        def load_completed(self, unit):
            if unit.unit_id == "chunk-000001":
                return empty_result(unit)
            return None

        def __call__(self, unit):
            self.executed.append(unit.unit_id)
            raise AssertionError("Budget exceeded")

    executor = Executor()
    result = run(path, limit=0, executor=executor)

    assert executor.executed == []
    assert result["scan_complete"] is False
    assert result["new_chunks_processed"] == 0
    assert result["rows_scanned"] == 500


def test_zero_budget_requires_checkpoint_interface(tmp_path):
    path = tmp_path / "worksheet.csv"
    path.write_text("a,b\n", encoding="utf-8")

    with pytest.raises(ValueError):
        run(path, limit=0)
