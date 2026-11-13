from __future__ import annotations

import json
import unittest

from apc.stages.doc_id import (
    _is_structured_json_parent,
    _structured_json_child_metadata,
)


class JsonDocIdFamilyTests(unittest.TestCase):

    def row(
        self,
        *,
        extension,
        parent=None,
        is_container=0,
        metadata=None,
    ):
        return {
            "extension": extension,
            "parent_file_id": parent,
            "is_container": is_container,
            "stage_status_json": json.dumps(metadata or {}),
        }

    def test_native_json_parent(self):
        row = self.row(
            extension="json",
            is_container=1,
            metadata={
                "structured_json_parent": {
                    "source_filename": "payroll.json",
                    "child_count": 2,
                }
            },
        )
        self.assertTrue(_is_structured_json_parent(row))

    def test_jsonl_parent(self):
        row = self.row(
            extension="jsonl",
            is_container=1,
            metadata={
                "structured_json_parent": {
                    "source_filename": "records.jsonl",
                }
            },
        )
        self.assertTrue(_is_structured_json_parent(row))

    def test_unrelated_json_not_parent(self):
        row = self.row(extension="json", is_container=0)
        self.assertFalse(_is_structured_json_parent(row))

    def test_child_one(self):
        row = self.row(
            extension="csv",
            parent="PARENT",
            metadata={
                "structured_json_child": {
                    "parent_file_id": "PARENT",
                    "child_number": 1,
                }
            },
        )
        self.assertEqual(
            _structured_json_child_metadata(row)["child_number"],
            1,
        )

    def test_child_two(self):
        row = self.row(
            extension="csv",
            parent="PARENT",
            metadata={
                "structured_json_child": {
                    "parent_file_id": "PARENT",
                    "child_number": 2,
                }
            },
        )
        self.assertEqual(
            _structured_json_child_metadata(row)["child_number"],
            2,
        )

    def test_mismatched_parent_rejected(self):
        row = self.row(
            extension="csv",
            parent="OTHER",
            metadata={
                "structured_json_child": {
                    "parent_file_id": "PARENT",
                    "child_number": 1,
                }
            },
        )
        self.assertEqual(
            _structured_json_child_metadata(row),
            {},
        )

    def test_ordinary_csv_unchanged(self):
        row = self.row(extension="csv")
        self.assertEqual(
            _structured_json_child_metadata(row),
            {},
        )


if __name__ == "__main__":
    unittest.main()
