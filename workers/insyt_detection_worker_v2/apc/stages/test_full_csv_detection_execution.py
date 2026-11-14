"""Exercise actual bounded-enabled full-CSV Detection finalization."""

from apc.stages import pii_phi_detection as stage


class RecordingDB:
    def __init__(self, row):
        self.row = row
        self.statements = []

    def query(self, sql, params=()):
        if "FROM file_processing_metrics" not in sql:
            raise AssertionError(
                f"Unexpected database query: {sql}"
            )
        return [self.row]

    def execute(self, sql, params=()):
        self.statements.append((sql, params))


def test_salesforce_csv_completes_under_bounded_configuration(
    monkeypatch, tmp_path
):
    csv = tmp_path / "salesforce.csv"
    csv.write_text(
        "Name,Email\n"
        "Synthetic Person,synthetic@example.test\n",
        encoding="utf-8",
    )

    doc_id = "INSYT000000008.1"

    row = {
        "doc_id": doc_id,
        "file_id": "FILE-SYNTHETIC",
        "has_native_text": 1,
    }

    db = RecordingDB(row)
    engine_calls = []
    checkpoint_calls = []

    monkeypatch.setattr(
        stage,
        "load_capture_rules_from_azure",
        lambda **kwargs: ([], "synthetic-rules"),
    )

    monkeypatch.setattr(
        stage,
        "_find_text_path",
        lambda row: str(csv),
    )

    monkeypatch.setattr(
        stage,
        "_get_stage_status",
        lambda row: {},
    )

    def full_engine(**kwargs):
        engine_calls.append(kwargs)
        return {
            "candidates": [],
            "azure_candidate_count": 0,
            "structured_candidate_count": 0,
            "merged_candidate_count": 0,
            "scan_complete": True,
        }

    monkeypatch.setattr(
        stage,
        "_run_full_detection_engine",
        full_engine,
    )

    def forbidden_checkpoint(**kwargs):
        checkpoint_calls.append(kwargs)
        raise AssertionError(
            "Ordinary full CSV entered worksheet checkpoint verification."
        )

    monkeypatch.setattr(
        stage,
        "_verify_selected_worksheet_progress",
        forbidden_checkpoint,
    )

    result = stage.run_pii_phi_detection(
        db,
        source_job_id="JOB-SYNTHETIC-SALESFORCE",
        matter_id="MATTER-SYNTHETIC",
        client_id="INSYT_Demo",
        project="Project_Synthetic",
        workspace="capture",
        selected_doc_ids={doc_id},
        document_options={
            doc_id: {
                "detection_mode": "full",
                "is_workbook_sheet": False,
            }
        },
        worksheet_executor_factory=lambda **kwargs: None,
        max_chunks_per_document=1,
    )

    assert len(engine_calls) == 1
    assert checkpoint_calls == []

    assert result["status"] == "completed"
    assert result["documents_total"] == 1
    assert result["documents_scanned"] == 1
    assert result["documents_no_hits"] == 1
    assert result["documents_exception"] == 0

    assert any(
        "UPDATE processing_detection_run" in sql
        for sql, _ in db.statements
    )

import pytest


@pytest.mark.parametrize("checkpoint_complete", [True, False])
def test_mixed_csv_checkpoint_publication(
    monkeypatch, tmp_path, checkpoint_complete
):
    worksheet = tmp_path / "payroll.csv"
    salesforce = tmp_path / "salesforce.csv"

    worksheet.write_text(
        "Name,Email\nExcel Person,excel@example.test\n",
        encoding="utf-8",
    )
    salesforce.write_text(
        "Name,Email\nSalesforce Person,sf@example.test\n",
        encoding="utf-8",
    )

    worksheet_id = "EXCEL-1"
    salesforce_id = "SALESFORCE-1"

    rows = [
        {
            "doc_id": worksheet_id,
            "file_id": "FILE-EXCEL",
            "has_native_text": 1,
        },
        {
            "doc_id": salesforce_id,
            "file_id": "FILE-SALESFORCE",
            "has_native_text": 1,
        },
    ]

    class MixedRecordingDB(RecordingDB):
        def query(self, sql, params=()):
            assert "FROM file_processing_metrics" in sql
            return rows

    db = MixedRecordingDB(rows[0])
    calls = {"full": 0, "worksheet": 0, "verify": 0}

    monkeypatch.setattr(
        stage,
        "load_capture_rules_from_azure",
        lambda **kwargs: ([], "synthetic-rules"),
    )
    monkeypatch.setattr(
        stage,
        "_find_text_path",
        lambda row: str(
            worksheet if row["doc_id"] == worksheet_id
            else salesforce
        ),
    )
    monkeypatch.setattr(
        stage,
        "_get_stage_status",
        lambda row: {},
    )

    def run_full(**kwargs):
        calls["full"] += 1
        return {
            "candidates": [],
            "scan_complete": True,
        }

    def run_worksheet(**kwargs):
        calls["worksheet"] += 1
        return {
            "candidates": [],
            "new_chunks_processed": 1,
            "scan_complete": True,
            "responsive_hit_count": 0,
        }

    def verify_worksheets(**kwargs):
        calls["verify"] += 1
        assert [
            row["doc_id"] for row in kwargs["rows"]
        ] == [worksheet_id]
        assert kwargs["selected_doc_ids"] == {worksheet_id}

        return {
            "checkpoint_verified": True,
            "job_complete": checkpoint_complete,
            "completed_units": 1 if checkpoint_complete else 0,
            "total_units": 1,
        }

    monkeypatch.setattr(
        stage, "_run_full_detection_engine", run_full
    )
    monkeypatch.setattr(
        stage, "_run_worksheet_triage_engine", run_worksheet
    )
    monkeypatch.setattr(
        stage,
        "_verify_selected_worksheet_progress",
        verify_worksheets,
    )

    kwargs = dict(
        source_job_id="JOB-SYNTHETIC-MIXED",
        matter_id="MATTER-SYNTHETIC",
        client_id="INSYT_Demo",
        project="Project_Synthetic",
        workspace="capture",
        selected_doc_ids={worksheet_id, salesforce_id},
        document_options={
            worksheet_id: {
                "detection_mode": "worksheet_triage",
                "is_workbook_sheet": True,
            },
            salesforce_id: {
                "detection_mode": "full",
                "is_workbook_sheet": False,
            },
        },
        worksheet_executor_factory=lambda **kwargs: None,
        max_chunks_per_document=1,
    )

    if checkpoint_complete:
        result = stage.run_pii_phi_detection(db, **kwargs)
        assert result["status"] == "completed"
        assert result["documents_total"] == 2
        assert result["documents_scanned"] == 2
        assert result["documents_exception"] == 0
    else:
        with pytest.raises(
            RuntimeError,
            match="Final checkpoint verification incomplete",
        ):
            stage.run_pii_phi_detection(db, **kwargs)

    assert calls == {
        "full": 1,
        "worksheet": 1,
        "verify": 1,
    }

    final_updates = [
        sql for sql, _ in db.statements
        if "UPDATE processing_detection_run" in sql
    ]

    assert len(final_updates) == (
        1 if checkpoint_complete else 0
    )