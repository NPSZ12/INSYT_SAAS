from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from apc.detection.models import DetectionCandidate
from apc.detection.rules import DetectionRule
from apc.detection_checkpoint_store import DetectionCheckpointStore
from apc.worksheet_executor_factory import (
    make_worksheet_executor_factory,
)
from apc.stages.pii_phi_detection import (
    _run_worksheet_triage_engine,
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


def test_five_worksheets_resume_after_interruption(tmp_path):
    container = FakeContainer()

    store = DetectionCheckpointStore(
        container,
        project_prefix="INSYT_Demo/capture/Project_Scalable",
    )

    calls = []

    def engine(text, **kwargs):
        calls.append(text)
        candidates = []

        markers = (
            ("first@example.test", "Email", ""),
            ("123-45-6789", "IdentificationNumber", "SSN"),
        )

        for marker, entity_type, subtype in markers:
            offset = text.find(marker)

            if offset >= 0:
                candidates.append(
                    DetectionCandidate(
                        entity_type=entity_type,
                        entity_subtype=subtype,
                        detected_value=marker,
                        start_offset=offset,
                        end_offset=offset + len(marker),
                        confidence=0.99,
                        detector_name="synthetic",
                        reportability="REPORTABLE",
                    )
                )

        return {
            "candidates": candidates,
            "azure_candidate_count": len(candidates),
            "structured_candidate_count": 0,
            "merged_candidate_count": len(candidates),
        }

    rules = [
        DetectionRule(
            rule_id="TEST_EMAIL",
            entity_type="Email",
            regex_pattern=r"\b\S+@\S+\b",
        ),
        DetectionRule(
            rule_id="TEST_SSN",
            entity_type="IdentificationNumber",
            entity_subtype="SSN",
            regex_pattern=r"\b\d{3}-\d{2}-\d{4}\b",
        ),
    ]

    worksheets = []

    for index in range(5):
        path = tmp_path / f"worksheet_{index + 1}.csv"

        rows = ["ordinary,data\n"] * 1001
        rows[0] = "email,first@example.test\n"
        rows[-1] = "ssn,123-45-6789\n"

        path.write_text(
            "".join(rows),
            encoding="utf-8",
            newline="\n",
        )

        worksheets.append(
            (f"INSYT000000{44 + index:03d}.1", path)
        )

    def new_factory():
        return make_worksheet_executor_factory(
            store=store,
            detection_job_id="DET-TEST-FIVE",
            engine=engine,
        )

    def process(factory, doc_id, path):
        executor = factory(
            doc_id=doc_id,
            workspace="capture",
            structured_rules=rules,
            rule_source="capture/synthetic_rules.xlsx",
            selected_sheets=("PII",),
            include_phi=True,
            enable_azure=False,
            protocol_name="Capture Rules",
            protocol_version="test-v1",
        )

        return _run_worksheet_triage_engine(
            path=path,
            include_phi=True,
            protocol_name="Capture Rules",
            protocol_version="test-v1",
            enable_azure=False,
            structured_rules=rules,
            chunk_executor=executor,
        )

    # First worker processes two worksheets before interruption.
    first_factory = new_factory()

    first_results = {
        doc_id: process(first_factory, doc_id, path)
        for doc_id, path in worksheets[:2]
    }

    assert len(calls) == 6

    # A new worker resumes the same detection job.
    resumed_factory = new_factory()

    all_results = {
        doc_id: process(resumed_factory, doc_id, path)
        for doc_id, path in worksheets
    }

    # Five worksheets x three chunks = 15 engine calls.
    # Previously completed chunks were not repeated.
    assert len(calls) == 15
    assert len(all_results) == 5

    for doc_id, result in all_results.items():
        assert result["rows_scanned"] == 1001
        assert result["scan_complete"] is True
        assert result["type_profile_complete"] is True
        assert len(result["candidates"]) == 2

        candidates = result["candidates"]

        assert candidates[0].entity_type == "Email"
        assert candidates[1].entity_subtype == "SSN"

        assert candidates[1].metadata[
            "profile_first_hit_row"
        ] == 1001

        if doc_id in first_results:
            assert result == first_results[doc_id]

    # A complete restart must reuse all 15 chunks.
    third_factory = new_factory()

    for doc_id, path in worksheets:
        assert process(third_factory, doc_id, path) == all_results[
            doc_id
        ]

    assert len(calls) == 15