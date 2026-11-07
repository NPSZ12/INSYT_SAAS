import pytest

from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from apc.detection.models import DetectionCandidate
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


def make_executor(container, calls):
    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    def engine(text, **kwargs):
        calls.append(text)
        candidates = []

        marker = "first@example.test"
        offset = text.find(marker)

        if offset >= 0:
            candidates.append(
                DetectionCandidate(
                    entity_type="Email",
                    detected_value=marker,
                    start_offset=offset,
                    end_offset=offset + len(marker),
                )
            )

        return {
            "candidates": candidates,
            "azure_candidate_count": 0,
            "structured_candidate_count": len(candidates),
            "merged_candidate_count": len(candidates),
        }

    return WorksheetCheckpointExecutor(
        store=store,
        detection_job_id="DET-TEST001",
        doc_id="INSYT000000001",
        protocol_fingerprint="sha256:synthetic-rules",
        detection_mode="worksheet_triage",
        include_phi=True,
        enable_azure=False,
        structured_rules=[],
        engine=engine,
        protocol_name="Capture Rules",
        protocol_version="test-v1",
    )


def make_units(tmp_path):
    path = tmp_path / "worksheet.csv"

    rows = ["ordinary,data\n"] * 1001
    rows[0] = "email,first@example.test\n"

    path.write_text(
        "".join(rows),
        encoding="utf-8",
        newline="\n",
    )

    return list(iter_worksheet_work_units(path))


def test_completed_chunks_restore_without_redetection(tmp_path):
    container = FakeContainer()
    calls = []
    units = make_units(tmp_path)

    first = make_executor(container, calls)

    original = [first(unit) for unit in units]

    assert len(calls) == 3

    # Simulated new worker: new executor instance,
    # same durable storage contents.
    second = make_executor(container, calls)

    restored = [second(unit) for unit in units]

    assert len(calls) == 3
    assert restored == original


def test_interrupted_job_resumes_remaining_chunks(tmp_path):
    container = FakeContainer()
    calls = []
    units = make_units(tmp_path)

    first = make_executor(container, calls)

    first(units[0])

    assert len(calls) == 1

    # Simulated worker restart.
    second = make_executor(container, calls)

    results = [second(unit) for unit in units]

    assert len(calls) == 3
    assert len(results) == 3


def test_corrupt_checkpoint_result_is_rejected(tmp_path):
    container = FakeContainer()
    calls = []
    unit = make_units(tmp_path)[0]

    executor = make_executor(container, calls)
    executor(unit)

    fingerprint = executor._fingerprint(unit)
    checkpoint = executor._checkpoint(unit, fingerprint)

    path = executor.store.result_path(checkpoint)

    container.records[path] = b'{"corrupt":true}'

    with pytest.raises(ValueError):
        executor(unit)

    assert len(calls) == 1

def test_protocol_parameters_forwarded_to_engine(tmp_path):
    container = FakeContainer()
    calls = []
    unit = make_units(tmp_path)[0]

    executor = make_executor(container, calls)

    observed = {}

    original_engine = executor.engine

    def recording_engine(text, **kwargs):
        observed.update(kwargs)
        return original_engine(text, **kwargs)

    executor.engine = recording_engine

    executor(unit)

    assert observed["protocol_name"] == "Capture Rules"
    assert observed["protocol_version"] == "test-v1"
    assert observed["include_phi"] is True
    assert observed["enable_azure"] is False


def test_protocol_parameters_survive_checkpoint_restore(tmp_path):
    container = FakeContainer()
    calls = []
    unit = make_units(tmp_path)[0]

    first = make_executor(container, calls)
    initial = first(unit)

    assert len(calls) == 1

    second = make_executor(container, calls)
    restored = second(unit)

    assert len(calls) == 1
    assert restored == initial

def test_mid_worksheet_interruption_recovers(tmp_path):
    from apc.stages.pii_phi_detection import (
        _run_worksheet_triage_engine,
    )

    container = FakeContainer()
    calls = []

    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Test",
    )

    # Build the same 1,001-row worksheet used by the
    # existing checkpoint executor regressions.
    units = make_units(tmp_path)
    path = tmp_path / "worksheet.csv"

    assert len(units) == 3

    first_worker = make_executor(container, calls)

    def interrupted_executor(unit):
        if unit.unit_id == "chunk-000002":
            raise RuntimeError(
                "Synthetic worker interruption."
            )

        return first_worker(unit)

    options = {
        "path": path,
        "include_phi": True,
        "protocol_name": None,
        "protocol_version": None,
        "enable_azure": False,
        "structured_rules": [],
    }

    # The first chunk finishes and is checkpointed.
    # Processing terminates before chunk two.
    with pytest.raises(
        RuntimeError,
        match="Synthetic worker interruption",
    ):
        _run_worksheet_triage_engine(
            **options,
            chunk_executor=interrupted_executor,
        )

    assert len(calls) == 1

    first_unit = units[0]
    fingerprint = first_worker._fingerprint(first_unit)
    expected = first_worker._checkpoint(
        first_unit,
        fingerprint,
    )

    assert store.load_reusable(expected) is not None

    # A completely new executor resumes the worksheet.
    second_worker = make_executor(container, calls)

    result = _run_worksheet_triage_engine(
        **options,
        chunk_executor=second_worker,
    )

    # Three chunks in total, with no duplicate
    # processing of the first completed chunk.
    assert len(calls) == 3

    assert result["rows_scanned"] == 1001
    assert result["scan_complete"] is True
    assert result["type_profile_complete"] is True

    assert len(result["candidates"]) == 1
    assert result["candidates"][0].entity_type == "Email"

    assert (
        result["candidates"][0].metadata[
            "profile_first_hit_row"
        ] == 1
    )

    # Another restart should perform zero new
    # detection calls.
    third_worker = make_executor(container, calls)

    repeated = _run_worksheet_triage_engine(
        **options,
        chunk_executor=third_worker,
    )

    assert len(calls) == 3
    assert repeated == result