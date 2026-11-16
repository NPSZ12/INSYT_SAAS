import json
from pathlib import Path
from unittest.mock import patch

from app.services.structured_intake.worker_prepare import (
    prepare_json_structured_sources,
)


def test_native_json_preserved_without_csv(tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    document = uploads / "nested.json"
    original = json.dumps(
        {
            "identity": {
                "date_of_birth": "1984-06-17",
                "ssn": "900-12-3456",
            },
            "cards": [
                {"number": "4111111111111111"},
                {"number": "5555555555554444"},
            ],
        },
        indent=2,
    ).encode("utf-8")

    document.write_bytes(original)
    existing_csv = uploads / "existing.csv"
    existing_csv.write_bytes(b"id,name\\n1,Example\\n")
    csv_before = existing_csv.read_bytes()

    with patch.dict(
        "os.environ",
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2": "1"},
    ):
        result = prepare_json_structured_sources(
            staging_dir=uploads
        )

    assert document.is_file()
    assert document.read_bytes() == original
    assert existing_csv.read_bytes() == csv_before
    assert list(uploads.glob("*.csv")) == [existing_csv]
    assert result["normalized_csv_count"] == 0
    assert result["json_package_count"] == 1

    package = result["packages"][0]
    assert package["status"] == "native_deferred"
    assert package["original_source_path"] == str(document)
    assert package["normalized_csv_path"] is None

    manifest = json.loads(
        Path(result["manifest_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert manifest["normalized_csv_count"] == 0
    assert manifest["packages"][0]["status"] == "native_deferred"


def test_legacy_json_conversion_unchanged(tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "legacy.json").write_text(
        json.dumps([{"id": 1, "name": "Example"}]),
        encoding="utf-8",
    )

    with patch.dict(
        "os.environ",
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2": "0"},
    ):
        result = prepare_json_structured_sources(
            staging_dir=uploads
        )

    assert result["normalized_csv_count"] == 1
    assert len(list(uploads.glob("*.csv"))) == 1
