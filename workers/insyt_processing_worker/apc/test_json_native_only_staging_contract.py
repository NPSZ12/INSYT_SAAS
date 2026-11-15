import json
from unittest.mock import MagicMock
from types import SimpleNamespace

from apc.azure_layout import build_xl_files_staging_plan


def test_json_parent_is_staged_native_only():
    job_id = "JOB-JSON-CONTRACT"

    db = MagicMock()
    db.query.return_value = [{
        "file_id": "FILE-JSON-1",
        "doc_id": "INSYT000000001",
        "parent_file_id": None,
        "original_path": "/tmp/original.json",
        "normalized_path": "/tmp/original.json",
        "extension": "json",
        "stage_status_json": json.dumps({
            "structured_json_parent": {
                "source_filename": "original.json",
                "source_profile": "plain_json",
            }
        }),
        "is_container": 1,
    }]

    routing = SimpleNamespace(
        prefix="TestClient/capture/TestProject",
        azure_write=False,
    )

    plan = build_xl_files_staging_plan(
        db, job_id, routing
    )

    assert len(plan) == 1, plan

    parent = plan[0]

    assert parent["doc_id"] == "INSYT000000001"
    assert parent["is_structured_parent"] is True
    assert parent["is_csv_child"] is False
    assert parent["extension"] == "json"

    expected = (
        "TestClient/capture/TestProject/"
        "processing_center/staged/"
        "JOB-JSON-CONTRACT/xl/native/"
        "INSYT000000001.json"
    )

    assert parent["native_staged_blob_path"] == expected
    assert parent["text_staged_blob_path"] == ""

    assert not any(
        item["is_csv_child"] for item in plan
    )

    assert not any(
        "/source/native/" in item["staged_blob_path"]
        for item in plan
    )