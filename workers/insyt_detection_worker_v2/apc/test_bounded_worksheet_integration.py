from collections import Counter

from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from apc.detection_bounded_coordinator import (
    execute_bounded_invocation,
)
from apc.detection_checkpoint_store import (
    DetectionCheckpointStore,
)
from apc.worksheet_checkpoint_executor import (
    WorksheetCheckpointExecutor,
)
from apc.worksheet_work_units import (
    iter_worksheet_work_units,
)


class FakeBlob:
    def __init__(self, records, path):
        self.records = records
        self.path = path

    def upload_blob(self, data, *, overwrite=False):
        if self.path in self.records and not overwrite:
            raise ResourceExistsError("Already exists.")
        self.records[self.path] = data

    def download_blob(self):
        if self.path not in self.records:
            raise ResourceNotFoundError("Missing.")
        return self

    def readall(self):
        return self.records[self.path]

    def get_blob_properties(self):
        if self.path not in self.records:
            raise ResourceNotFoundError("Missing.")
        return {"size": len(self.records[self.path])}


class FakeContainer:
    def __init__(self):
        self.records = {}

    def get_blob_client(self, path):
        return FakeBlob(self.records, path)


def test_five_worksheets_across_bounded_invocations(tmp_path):
    container = FakeContainer()

    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Project_Scalable",
    )

    engine_calls = Counter()
    work = {}

    for index in range(5):
        doc_id = f"INSYT{44 + index:09d}.1"
        path = tmp_path / f"sheet_{index}.csv"

        path.write_text(
            "synthetic,data\n" * 1001,
            encoding="utf-8",
            newline="\n",
        )

        for unit in iter_worksheet_work_units(path):
            key = f"{doc_id}:{unit.unit_id}"
            work[key] = (doc_id, unit)

    assert len(work) == 15

    def make_executor(doc_id):
        def engine(text, **kwargs):
            engine_calls[doc_id] += 1
            return {
                "candidates": [],
                "azure_candidate_count": 0,
                "structured_candidate_count": 0,
                "merged_candidate_count": 0,
            }

        return WorksheetCheckpointExecutor(
            store=store,
            detection_job_id="DET-BOUNDED-TEST",
            doc_id=doc_id,
            protocol_fingerprint="sha256:synthetic-rules",
            detection_mode="worksheet_triage",
            include_phi=True,
            enable_azure=False,
            structured_rules=[],
            engine=engine,
        )

    def checkpoint_for(key):
        doc_id, unit = work[key]
        executor = make_executor(doc_id)
        fingerprint = executor._fingerprint(unit)
        return executor._checkpoint(unit, fingerprint)

    def verified_completed():
        return {
            key
            for key in work
            if store.load_reusable(
                checkpoint_for(key)
            ) is not None
        }

    def execute_unit(key):
        doc_id, unit = work[key]
        make_executor(doc_id)(unit)

    state = {
        "enqueued": 0,
        "finalized": 0,
    }

    def enqueue():
        state["enqueued"] += 1

    def finalize():
        assert len(verified_completed()) == 15
        state["finalized"] += 1

    results = []

    for _ in range(4):
        result = execute_bounded_invocation(
            all_unit_ids=list(work),
            max_units_per_invocation=4,
            verified_completed=verified_completed,
            execute_unit=execute_unit,
            enqueue_continuation=enqueue,
            finalize_job=finalize,
        )
        results.append(result)

    assert [
        len(result.executed_units)
        for result in results
    ] == [4, 4, 4, 3]

    assert len(verified_completed()) == 15
    assert sum(engine_calls.values()) == 15
    assert state["enqueued"] == 3
    assert state["finalized"] == 1
    assert results[-1].job_complete is True

    # Simulate a duplicate queue delivery after completion.
    repeated = execute_bounded_invocation(
        all_unit_ids=list(work),
        max_units_per_invocation=4,
        verified_completed=verified_completed,
        execute_unit=execute_unit,
        enqueue_continuation=enqueue,
        finalize_job=finalize,
    )

    assert repeated.executed_units == ()
    assert sum(engine_calls.values()) == 15

    # The current coordinator invokes finalization again
    # on duplicate completed-job deliveries. Production
    # finalization must therefore be idempotent or fenced.
    assert state["finalized"] == 2