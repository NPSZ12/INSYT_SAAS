import json

import pytest

from app.services.structured_intake.json_detection_text import (
    build_native_json_detection_text,
)


@pytest.mark.parametrize("extension", ["json", "jsonl", "ndjson"])
def test_nested_identifiers(extension):
    record = {
        "patient": {
            "identifiers": {
                "SSN": "464-12-1234",
                "MRN": "MRN-882199",
            },
            "records": [
                {"MRN": "882199"},
                {"email": "patient@example.test"},
            ],
        }
    }

    original = json.dumps(record).encode("utf-8")
    original_copy = bytes(original)

    if extension != "json":
        original += b"\n"
        original_copy = bytes(original)

    detection_text = build_native_json_detection_text(
        original,
        extension,
    )

    assert "SSN: 464-12-1234" in detection_text
    assert "MRN: MRN-882199" in detection_text
    assert "MRN: 882199" in detection_text
    assert "email: patient@example.test" in detection_text
    assert "records[0].MRN" in detection_text
    assert original == original_copy
    assert "Source path:" in detection_text


@pytest.mark.parametrize("extension", ["json", "jsonl", "ndjson"])
def test_invalid_json_fails_closed(extension):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        build_native_json_detection_text(
            b"{invalid",
            extension,
        )


def test_jsonl_multiple_records():
    source = (
        b'{"MRN":"882199"}\n'
        b'{"SSN":"464-12-1234"}\n'
    )

    text = build_native_json_detection_text(
        source,
        "jsonl",
    )

    assert "record[0].MRN" in text
    assert "record[1].SSN" in text
    assert "MRN: 882199" in text


def test_no_csv_generation():
    source = b'{"MRN":"882199"}'

    text = build_native_json_detection_text(
        source,
        "json",
    )

    assert "MRN: 882199" in text
    assert "normalized_csv" not in text
