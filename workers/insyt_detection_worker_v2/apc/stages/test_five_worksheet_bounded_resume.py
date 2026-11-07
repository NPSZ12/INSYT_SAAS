from collections import Counter

from apc.stages import pii_phi_detection as stage


DOC_IDS = [
    f"INSYT0000000{number}.1"
    for number in range(44, 49)
]


def empty_result():
    return {
        "candidates": [],
        "azure_candidate_count": 0,
        "structured_candidate_count": 0,
        "merged_candidate_count": 0,
    }


class DurableExecutor:
    def __init__(self, document_id, records, executions):
        self.document_id = document_id
        self.records = records
        self.executions = executions

    def load_completed(self, unit):
        key = (self.document_id, unit.unit_id)
        return self.records.get(key)

    def __call__(self, unit):
        key = (self.document_id, unit.unit_id)

        cached = self.load_completed(unit)
        if cached is not None:
            return cached

        self.executions.append(key)
        result = empty_result()
        self.records[key] = result
        return result


def run_invocation(paths, records, executions, budget):
    remaining = budget
    results = {}

    for doc_id, path in paths.items():
        executor = DurableExecutor(
            doc_id, records, executions
        )

        result = stage._run_worksheet_triage_engine(
            path=path,
            include_phi=True,
            protocol_name="synthetic",
            protocol_version="1",
            enable_azure=False,
            structured_rules=[],
            chunk_executor=executor,
            max_chunks=remaining,
        )

        consumed = result["new_chunks_processed"]

        assert type(consumed) is int
        assert 0 <= consumed <= remaining

        remaining -= consumed
        results[doc_id] = result

        if result["scan_complete"] is not True:
            break

    complete = (
        len(results) == len(paths)
        and all(
            result["scan_complete"] is True
            for result in results.values()
        )
    )

    return complete, results, budget - remaining


def test_five_worksheets_resume_and_replay(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 2
    )
    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_CHARS", 100000
    )

    paths = {}

    for doc_id in DOC_IDS:
        path = tmp_path / f"{doc_id}.csv"
        path.write_text(
            "synthetic,data\n" * 5,
            encoding="utf-8",
            newline="\n",
        )
        paths[doc_id] = path

    # The record dictionary models durable checkpoints
    # shared across fresh Function invocations.
    records = {}
    executions = []
    invocation_counts = []
    complete = False

    for _ in range(12):
        complete, results, new_count = run_invocation(
            paths, records, executions, budget=2
        )

        invocation_counts.append(new_count)

        if complete:
            break

        assert new_count > 0
        assert new_count <= 2

    assert complete is True

    # Five worksheets, three chunks each.
    assert len(records) == 15
    assert len(executions) == 15
    assert len(set(executions)) == 15

    assert len(invocation_counts) == 8
    assert invocation_counts == [2] * 7 + [1]

    for doc_id in DOC_IDS:
        assert results[doc_id]["scan_complete"] is True
        assert results[doc_id]["rows_scanned"] == 5
        assert results[doc_id]["candidates"] == []

    counts = Counter(
        doc_id for doc_id, _ in executions
    )

    assert all(
        counts[doc_id] == 3 for doc_id in DOC_IDS
    )

    # Duplicate delivery after completion must
    # reconstruct all results without new execution.
    prior_executions = len(executions)

    replay_complete, replay_results, replay_new = (
        run_invocation(
            paths, records, executions, budget=2
        )
    )

    assert replay_complete is True
    assert replay_new == 0
    assert len(executions) == prior_executions

    assert set(replay_results) == set(DOC_IDS)


def test_missing_checkpoint_resumes_only_missing_work(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_ROWS", 2
    )
    monkeypatch.setattr(
        stage, "WORKSHEET_TRIAGE_CHUNK_CHARS", 100000
    )

    doc_id = DOC_IDS[0]
    path = tmp_path / "recovery.csv"

    path.write_text(
        "synthetic,data\n" * 5,
        encoding="utf-8",
        newline="\n",
    )

    records = {}
    executions = []

    first_complete, _, first_count = run_invocation(
        {doc_id: path},
        records,
        executions,
        budget=2,
    )

    assert first_complete is False
    assert first_count == 2

    second_complete, _, second_count = run_invocation(
        {doc_id: path},
        records,
        executions,
        budget=2,
    )

    assert second_complete is True
    assert second_count == 1
    assert len(executions) == 3