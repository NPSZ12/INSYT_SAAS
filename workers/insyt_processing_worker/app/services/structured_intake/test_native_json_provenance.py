import json
from pathlib import Path

import pytest

from app.services.structured_intake.provenance import (
    apply_structured_json_provenance,
)


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
        self.updates = []

    def query(self, sql, params):
        self.queries.append((sql, params))
        return self.rows

    def execute(self, sql, params):
        self.updates.append((sql, params))


@pytest.mark.parametrize("extension", ["json", "jsonl", "ndjson"])
def test_original_json_provenance(tmp_path: Path, extension):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    native = uploads / ("original." + extension)
    original = b'{"name":"Example","nested":{"dob":"1984-06-17"}}'
    native.write_bytes(original)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "packages": [{
                "status": "native_deferred",
                "source_filename": native.name,
                "original_source_path": str(native),
                "source_profile": "plain",
                "package_id": "JSON-PKG-000001",
                "package_count": 1,
                "record_count": 0,
            }]
        }),
        encoding="utf-8",
    )

    db = FakeDB([{"file_id": "FILE1"}])

    result = apply_structured_json_provenance(
        db=db,
        job_id="JOB-JSON-1",
        staging_dir=uploads,
        manifest_path=manifest,
    )

    assert result["updated_count"] == 1
    assert result["missing_count"] == 0
    assert len(db.updates) == 1

    sql, values = db.updates[0]
    payload = json.loads(values[1])["structured_source"]

    assert payload["source_format"] == "json"
    assert payload["source_extension"] == extension
    assert payload["original_json_filename"] == native.name
    assert payload["csv_generation_status"] == "not_started"
    assert payload["adapter"] == "json_native"
    assert "json_patch" in sql

    assert native.read_bytes() == original
    assert not list(uploads.glob("*.csv"))


def test_missing_inventory_row_is_reported(tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    native = uploads / "original.json"
    native.write_text("{}", encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "packages": [{
                "status": "native_deferred",
                "source_filename": native.name,
                "original_source_path": str(native),
                "source_profile": "plain",
            }]
        }),
        encoding="utf-8",
    )

    db = FakeDB([])
    result = apply_structured_json_provenance(
        db=db,
        job_id="JOB-JSON-1",
        staging_dir=uploads,
        manifest_path=manifest,
    )

    assert result["missing_count"] == 1
    assert result["updated_count"] == 0
    assert db.updates == []
