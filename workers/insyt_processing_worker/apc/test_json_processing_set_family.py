from __future__ import annotations

import json
import unittest

from apc.processing_sets import (
    _csv_family_parent_file_id,
    _structured_json_parent_file_id,
    _workbook_parent_file_id,
)


class JsonProcessingSetFamilyTests(unittest.TestCase):

    def row(self, status, parent=None):
        return {
            "stage_status_json": json.dumps(status),
            "parent_file_id": parent,
        }

    def test_plain_json_child(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "FILE-PARENT",
                    "child_number": 1,
                }
            },
            parent="FILE-PARENT",
        )

        self.assertEqual(
            _structured_json_parent_file_id(row),
            "FILE-PARENT",
        )

    def test_second_json_child(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "FILE-PARENT",
                    "child_number": 2,
                }
            },
            parent="FILE-PARENT",
        )

        self.assertEqual(
            _structured_json_parent_file_id(row),
            "FILE-PARENT",
        )

    def test_ordinary_csv_remains_standalone(self):
        row = self.row({}, parent=None)

        self.assertEqual(
            _structured_json_parent_file_id(row),
            "",
        )

    def test_parent_mismatch_is_rejected(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "FILE-A",
                    "child_number": 1,
                }
            },
            parent="FILE-B",
        )

        self.assertEqual(
            _structured_json_parent_file_id(row),
            "",
        )

    def test_invalid_child_number_is_rejected(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "FILE-PARENT",
                    "child_number": 0,
                }
            },
            parent="FILE-PARENT",
        )

        self.assertEqual(
            _structured_json_parent_file_id(row),
            "",
        )

    def test_existing_workbook_helper_preserved(self):
        row = self.row(
            {
                "workbook_sheet": {
                    "original_workbook_file_id": "XL-PARENT"
                }
            },
            parent="XL-PARENT",
        )

        self.assertEqual(
            _workbook_parent_file_id(row),
            "XL-PARENT",
        )
        self.assertEqual(
            _structured_json_parent_file_id(row),
            "",
        )


    def test_shared_csv_family_excel_child(self):
        row = self.row(
            {
                "workbook_sheet": {
                    "original_workbook_file_id": "XL-PARENT",
                }
            },
            parent="XL-PARENT",
        )
        self.assertEqual(
            _csv_family_parent_file_id(row),
            "XL-PARENT",
        )

    def test_shared_csv_family_json_child(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "JSON-PARENT",
                    "child_number": 3,
                }
            },
            parent="JSON-PARENT",
        )
        self.assertEqual(
            _csv_family_parent_file_id(row),
            "JSON-PARENT",
        )

    def test_shared_csv_family_ordinary_csv(self):
        self.assertEqual(
            _csv_family_parent_file_id(self.row({})),
            "",
        )

    def test_shared_csv_family_invalid_json_child(self):
        row = self.row(
            {
                "structured_json_child": {
                    "parent_file_id": "JSON-PARENT",
                    "child_number": 0,
                }
            },
            parent="JSON-PARENT",
        )
        self.assertEqual(
            _csv_family_parent_file_id(row),
            "",
        )

    def test_shared_csv_family_conflicting_parents(self):
        row = self.row(
            {
                "workbook_sheet": {
                    "original_workbook_file_id": "XL-PARENT",
                },
                "structured_json_child": {
                    "parent_file_id": "JSON-PARENT",
                    "child_number": 1,
                },
            },
            parent="JSON-PARENT",
        )
        with self.assertRaisesRegex(
            ValueError,
            "Conflicting structured CSV parent IDs",
        ):
            _csv_family_parent_file_id(row)

    def test_shared_csv_family_matching_metadata(self):
        row = self.row(
            {
                "workbook_sheet": {
                    "original_workbook_file_id": "PARENT",
                },
                "structured_json_child": {
                    "parent_file_id": "PARENT",
                    "child_number": 1,
                },
            },
            parent="PARENT",
        )
        self.assertEqual(
            _csv_family_parent_file_id(row),
            "PARENT",
        )


if __name__ == "__main__":
    unittest.main()
