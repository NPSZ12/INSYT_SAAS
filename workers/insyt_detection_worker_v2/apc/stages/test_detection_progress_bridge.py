import pytest

from apc.stages import pii_phi_detection as stage


class FakeExecutor:
    def __init__(self, completed):
        self.completed = completed

    def load_completed(self, unit):
        if self.completed:
            return {"candidates": []}
        return None


def test_bridge_uses_selected_documents_and_executors(
    tmp_path, monkeypatch
):
    files = {}

    for doc_id in ("DOC-A", "DOC-B"):
        path = tmp_path / f"{doc_id}.csv"
        path.write_text("a,b\n", encoding="utf-8")
        files[doc_id] = path

    monkeypatch.setattr(
        stage,
        "_find_text_path",
        lambda row: str(files[row["doc_id"]]),
    )

    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeExecutor(
            kwargs["doc_id"] == "DOC-A"
        )

    result = stage._verify_selected_worksheet_progress(
        rows=[
            {"doc_id": "DOC-A"},
            {"doc_id": "DOC-B"},
        ],
        document_options={
            "DOC-A": {"detection_mode": "worksheet_triage"},
            "DOC-B": {"detection_mode": "worksheet_triage"},
        },
        workspace_key="capture",
        structured_rules=[],
        rule_workbook_blob="synthetic-rule-source",
        selected_rule_sheets=("Search Rules",),
        include_phi=True,
        enable_azure_detection=True,
        protocol_name="synthetic",
        protocol_version="1",
        worksheet_executor_factory=factory,
        selected_doc_ids={"DOC-A", "DOC-B"},
    )

    assert result["checkpoint_verified"] is True
    assert result["total_units"] == 2
    assert result["completed_units"] == 1
    assert result["job_complete"] is False

    assert [call["doc_id"] for call in calls] == [
        "DOC-A", "DOC-B"
    ]

    assert all(
        call["rule_source"] == "synthetic-rule-source"
        for call in calls
    )


def test_bridge_rejects_nonworksheet_population(
    tmp_path, monkeypatch
):
    path = tmp_path / "doc.txt"
    path.write_text("synthetic text", encoding="utf-8")

    monkeypatch.setattr(
        stage,
        "_find_text_path",
        lambda row: str(path),
    )

    with pytest.raises(ValueError, match="worksheet-triage"):
        stage._verify_selected_worksheet_progress(
            rows=[{"doc_id": "DOC-A"}],
            document_options={
                "DOC-A": {"detection_mode": "full"},
            },
            workspace_key="capture",
            structured_rules=[],
            rule_workbook_blob="synthetic",
            selected_rule_sheets=(),
            include_phi=True,
            enable_azure_detection=True,
            protocol_name=None,
            protocol_version=None,
            worksheet_executor_factory=lambda **kwargs: FakeExecutor(
                True
            ),
            selected_doc_ids={"DOC-A"},
        )