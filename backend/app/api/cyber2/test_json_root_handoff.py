"""Verify native JSON construction against downstream provenance."""

import hashlib
import unittest
from copy import deepcopy

from json_header_evidence import discover_json_header_evidence
from json_mapped_preview import construct_approved_json_csv_rows

from app.services.cyber2.mapped_processing_set import (
    _validated_native_json_pointers,
)


class RootJsonHandoffTests(unittest.TestCase):

    def verify_handoff(self, data, extension, names, pointers):

        source_hash = hashlib.sha256(data).hexdigest()

        evidence = discover_json_header_evidence(
            data,
            extension,
        )

        columns = []

        for index, field in enumerate(evidence["fields"]):

            if field["kind"] != "scalar":
                continue

            columns.append({
                "column_index": index,
                "json_pointer": field["json_pointer"],
                "json_kind": "scalar",
                "source_header": "first_name",
                "final_header": "First Name (or Initial)",
                "disposition": "map",
                "delete_column": False,
                "mapped_to_protocol": True,
            })

        approved = {
            "doc_id": "SYNTHETIC001",
            "source_kind": "native_json",
            "source_native_path": (
                f"synthetic/native/SYNTHETIC001.{extension}"
            ),
            "source_sha256": source_hash,
            "source_format": extension,
            "source_bytes": len(data),
            "columns": columns,
        }

        original_approval = deepcopy(approved)

        result = construct_approved_json_csv_rows(
            data,
            extension,
            approved,
            ["First Name (or Initial)"],
            source_hash,
            record_array_path=None,
        )

        self.assertEqual(
            result["output_headers"],
            ["First Name (or Initial)"],
        )

        self.assertEqual(
            result["rows"],
            [["First Name (or Initial)"]]
            + [[name] for name in names],
        )

        self.assertEqual(
            result["source_row_count"],
            len(names),
        )

        self.assertEqual(
            result["mapped_row_count"],
            len(names),
        )

        self.assertEqual(
            result["row_source_pointers"],
            pointers,
        )

        self.assertIsNone(result["record_array_path"])

        self.assertEqual(
            _validated_native_json_pointers(
                result,
                approved,
                len(names),
            ),
            pointers,
        )

        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            source_hash,
        )

        self.assertEqual(approved, original_approval)
        self.assertFalse(result["source_modified"])

    def test_root_object(self):

        self.verify_handoff(
            b'{"first_name":"Avery"}',
            "json",
            ["Avery"],
            ["/0"],
        )

    def test_root_array(self):

        self.verify_handoff(
            b'[{"first_name":"Avery"},{"first_name":"Jordan"}]',
            "json",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )

    def test_standard_records_container(self):

        self.verify_handoff(
            b'{"records":[{"first_name":"Avery"},{"first_name":"Jordan"}]}',
            "json",
            ["Avery", "Jordan"],
            ["/records/0", "/records/1"],
        )

    def test_jsonl(self):

        self.verify_handoff(
            b'{"first_name":"Avery"}\n{"first_name":"Jordan"}\n',
            "jsonl",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )

    def test_ndjson(self):

        self.verify_handoff(
            b'{"first_name":"Avery"}\n{"first_name":"Jordan"}\n',
            "ndjson",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )


if __name__ == "__main__":
    unittest.main()
