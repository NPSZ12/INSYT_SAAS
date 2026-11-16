
import json
from apc.azure_layout import build_json_structured_staging_plan


class DB:
    def query(self, sql, params):
        assert "is_container=0" in sql
        assert "is_container=1" in sql
        assert "jsonl" in sql
        assert "ndjson" in sql
        return [{
            "file_id": "FILE-TEST",
            "doc_id": "INSYT000000001",
            "parent_file_id": None,
            "original_path": "/tmp/smoke.json",
            "normalized_path": "/tmp/smoke.json",
            "extension": "json",
            "requires_ocr": 0,
            "stage_status_json": json.dumps({
                "structured_source": {
                    "source_family": "structured",
                    "source_format": "json",
                    "source_profile": "plain",
                    "original_json_filename": "smoke.json",
                    "original_json_path": "/tmp/smoke.json",
                    "csv_generation_status": "not_started",
                }
            }),
        }]


class Routing:
    prefix = "TEST/capture/Project_Test"
    azure_write = True


def test_native_json_parent_is_planned_without_csv():
    plan = build_json_structured_staging_plan(
        DB(), "JOB-TEST", Routing()
    )
    assert len(plan) == 1
    row = plan[0]
    assert row["doc_id"] == "INSYT000000001"
    assert row["extension"] == "json"
    assert row["native_staged_blob_path"].endswith(
        "/structured/native/INSYT000000001.json"
    )
    assert row["text_staged_blob_path"].endswith(
        "/structured/text/INSYT000000001.txt"
    )
