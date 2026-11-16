import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from apc.azure_layout import build_json_structured_staging_plan


class FakeLedger:
    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, params):
        assert params == ("JOB-JSON-1",)
        assert "file_processing_metrics" in sql
        return self.rows


def test_native_json_staging_uses_original_document(tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    native = uploads / "original.json"
    payload = {
        "identity": {
            "name": "Synthetic Example",
            "dob": "1984-06-17",
            "ssn": "900-12-3456",
        },
        "cards": [
            {"number": "4111111111111111"},
            {"number": "5555555555554444"},
        ],
    }

    native_bytes = json.dumps(
        payload, indent=2
    ).encode("utf-8")

    native.write_bytes(native_bytes)

    source_metadata = {
        "structured_source": {
            "source_family": "structured",
            "source_format": "json",
            "source_profile": "plain",
            "original_json_filename": native.name,
            "original_json_path": str(native),
            "csv_generation_status": "not_started",
        }
    }

    row = {
        "file_id": "FILE-JSON-1",
        "doc_id": "INSYT000000010",
        "parent_file_id": None,
        "original_path": str(native),
        "normalized_path": native.name,
        "extension": "json",
        "stage_status_json": json.dumps(source_metadata),
        "requires_ocr": 0,
    }

    db = FakeLedger([row])
    routing = SimpleNamespace(
        prefix="SyntheticClient/capture/ProjectJSONTest",
        azure_write=True
    )

    plan = build_json_structured_staging_plan(
        db,
        "JOB-JSON-1",
        routing,
    )

    assert len(plan) == 1
    item = plan[0]

    assert item["doc_id"] == "INSYT000000010"
    assert item["file_id"] == "FILE-JSON-1"
    assert item["source_type"] == "json_structured"
    assert item["detection_mode"] == "structured_json"
    assert item["extension"] == "json"
    assert item["original_path"] == str(native)

    assert item["native_staged_blob_path"] == (
        "SyntheticClient/capture/ProjectJSONTest/"
        "processing_center/staged/JOB-JSON-1/"
        "structured/native/INSYT000000010.json"
    )

    assert item["text_staged_blob_path"] == (
        "SyntheticClient/capture/ProjectJSONTest/"
        "processing_center/staged/JOB-JSON-1/"
        "structured/text/INSYT000000010.txt"
    )

    assert native.read_bytes() == native_bytes
    assert hashlib.sha256(
        native.read_bytes()
    ).hexdigest() == hashlib.sha256(
        native_bytes
    ).hexdigest()

    assert not list(uploads.glob("*.csv"))
    assert source_metadata["structured_source"][
        "csv_generation_status"
    ] == "not_started"