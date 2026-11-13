from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from apc.azure_job_runner import validate_structured_csv_uploads


class StructuredUploadReconciliationTests(unittest.TestCase):

    def make_rows(self):
        return [
            {
                "file_id": "PARENT",
                "parent_file_id": None,
                "extension": "json",
                "is_container": 1,
                "is_duplicate": 0,
                "is_denisted": 0,
                "doc_id": "INSYT000000001",
                "stage_status_json": json.dumps({
                    "structured_json_parent": {
                        "source_filename": "synthetic.json"
                    }
                }),
            },
            {
                "file_id": "CHILD",
                "parent_file_id": "PARENT",
                "extension": "csv",
                "is_container": 0,
                "is_duplicate": 0,
                "is_denisted": 0,
                "doc_id": "INSYT000000001.1",
                "stage_status_json": json.dumps({
                    "structured_json_child": {
                        "parent_file_id": "PARENT",
                        "child_number": 1,
                    }
                }),
            },
        ]

    def uploaded_child(self):
        return {
            "file_id": "CHILD",
            "doc_id": "INSYT000000001.1",
            "status": "uploaded",
            "is_csv_child": True,
            "detection_ready": True,
            "text_staged_blob_path": "synthetic/text/child.txt",
        }

    def validate(self, rows, uploaded):
        db = Mock()
        db.query.return_value = rows
        result = validate_structured_csv_uploads(
            db=db,
            job_id="TEST",
            upload_result={"uploaded": uploaded},
        )
        db.query.assert_called_once()
        return result

    def test_complete_structured_upload(self):
        self.assertEqual(
            self.validate(
                self.make_rows(),
                [self.uploaded_child()],
            ),
            1,
        )

    def test_zero_uploaded_cannot_pass(self):
        with self.assertRaisesRegex(
            RuntimeError, "reconciliation failed"
        ):
            self.validate(self.make_rows(), [])

    def test_missing_doc_id_cannot_pass(self):
        rows = self.make_rows()
        rows[1]["doc_id"] = None
        with self.assertRaisesRegex(
            RuntimeError, "missing Doc ID"
        ):
            self.validate(rows, [])

    def test_missing_detection_ready_cannot_pass(self):
        uploaded = self.uploaded_child()
        uploaded["detection_ready"] = False
        with self.assertRaisesRegex(
            RuntimeError, "not detection-ready"
        ):
            self.validate(self.make_rows(), [uploaded])

    def test_structured_parent_without_child_cannot_pass(self):
        rows = self.make_rows()[:1]
        with self.assertRaisesRegex(
            RuntimeError, "no registered CSV children"
        ):
            self.validate(rows, [])

    def test_suppressed_duplicate_not_required_for_upload(self):
        rows = self.make_rows()
        rows[1]["is_duplicate"] = 1
        rows[1]["doc_id"] = None
        self.assertEqual(self.validate(rows, []), 0)

    def test_ordinary_csv_not_affected(self):
        rows = [{
            "file_id": "CSV",
            "parent_file_id": None,
            "extension": "csv",
            "is_container": 0,
            "is_duplicate": 0,
            "is_denisted": 0,
            "doc_id": "INSYT000000001",
            "stage_status_json": "{}",
        }]
        self.assertEqual(self.validate(rows, []), 0)


if __name__ == "__main__":
    unittest.main()