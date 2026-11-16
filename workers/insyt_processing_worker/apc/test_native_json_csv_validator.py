import json
import os
from unittest.mock import patch

import pytest

from apc.azure_job_runner import validate_structured_csv_uploads


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, params):
        return self.rows


def parent(*, native, doc_id):
    metadata = {
        "source_filename": "smoke.json",
    }
    if native:
        metadata.update({
            "native_detection_required": True,
        })
    return {
        "file_id": "FILE-TEST",
        "parent_file_id": None,
        "extension": "json",
        "is_container": 1,
        "is_duplicate": 0,
        "is_denisted": 0,
        "doc_id": doc_id,
        "stage_status_json": json.dumps({
            "structured_json_parent": metadata,
        }),
    }


def validate(row, enabled):
    with patch.dict(
        os.environ,
        {"INSYT_JSON_DEFER_CSV_UNTIL_CYBER2":
         "1" if enabled else "0"},
    ):
        return validate_structured_csv_uploads(
            db=FakeDB([row]),
            job_id="JOB-TEST",
            upload_result={"uploaded": []},
        )


def test_native_json_no_csv_with_doc_id():
    assert validate(
        parent(native=True, doc_id="DOC-TEST"),
        enabled=True,
    ) == 0


def test_native_json_missing_doc_id_fails_closed():
    with pytest.raises(RuntimeError, match="no registered Doc ID"):
        validate(
            parent(native=True, doc_id=None),
            enabled=True,
        )


def test_legacy_parent_still_requires_csv_children():
    with pytest.raises(
        RuntimeError,
        match="no registered CSV children",
    ):
        validate(
            parent(native=False, doc_id=None),
            enabled=False,
        )


def test_native_metadata_does_not_bypass_disabled_flag():
    with pytest.raises(
        RuntimeError,
        match="no registered CSV children",
    ):
        validate(
            parent(native=True, doc_id="DOC-TEST"),
            enabled=False,
        )
