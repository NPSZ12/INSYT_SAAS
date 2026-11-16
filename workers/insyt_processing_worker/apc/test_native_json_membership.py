
import json
import os
from unittest.mock import patch

from apc.processing_sets import (
    _is_native_deferred_json_parent as set_eligible,
)
from apc.stages.doc_id import (
    _is_native_deferred_json_parent as doc_eligible,
)


def record(extension="json", *, native=True, container=1):
    metadata = {
        "source_filename": "source." + extension,
    }
    if native:
        metadata.update({
            "native_detection_required": True,
            "csv_child_count": 0,
        })
    return {
        "extension": extension,
        "is_container": container,
        "parent_file_id": None,
        "stage_status_json": json.dumps({
            "structured_json_parent": metadata,
        }),
    }


def test_native_json_eligible_in_both_stages():
    with patch.dict(
        os.environ,
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2": "1"},
    ):
        for extension in ("json", "jsonl", "ndjson"):
            row = record(extension)
            assert set_eligible(row)
            assert doc_eligible(row)


def test_legacy_and_unrelated_containers_not_eligible():
    with patch.dict(
        os.environ,
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2": "1"},
    ):
        for row in (
            record("zip"),
            record("json", native=False),
            record("json", container=0),
        ):
            assert not set_eligible(row)
            assert not doc_eligible(row)


def test_flag_disabled_preserves_existing_behavior():
    with patch.dict(
        os.environ,
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2": "0"},
    ):
        row = record()
        assert not set_eligible(row)
        assert not doc_eligible(row)
