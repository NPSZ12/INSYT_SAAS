"""Permanent multi-parent native JSON provenance regressions."""

import hashlib
import json
import unittest
from copy import deepcopy

from app.api.cyber2.json_header_evidence import (
    discover_json_header_evidence,
)

from app.api.cyber2.json_mapped_preview import (
    construct_approved_json_csv_rows,
    JsonTransformError,
)

from app.services.cyber2.mapped_processing_set import (
    _validated_native_json_pointers,
    MappedProcessingSetError,
)


class MultiParentJsonHandoffTests(unittest.TestCase):

    def construct(self, native, extension="json"):

        if extension in {"jsonl", "ndjson"}:
            data = "\n".join(
                json.dumps(record) for record in native
            ).encode("utf-8")
        else:
            data = json.dumps(native).encode("utf-8")

        source_hash = hashlib.sha256(data).hexdigest()

        evidence = discover_json_header_evidence(
            data, extension
        )

        columns = []

        for field in evidence["fields"]:

            if field["kind"] != "scalar":
                continue

            keep = field["json_pointer"].endswith("/first_name")

            columns.append({
                "column_index": len(columns),
                "json_pointer": field["json_pointer"],
                "json_kind": "scalar",
                "source_header": field["source_path"],
                "final_header": (
                    "First Name (or Initial)" if keep else ""
                ),
                "disposition": "map" if keep else "delete",
                "delete_column": not keep,
                "mapped_to_protocol": keep,
            })

        approved = {
            "doc_id": "SYNTHETIC001",
            "source_kind": "native_json",
            "source_native_path": (
                f"synthetic/native/test.{extension}"
            ),
            "source_sha256": source_hash,
            "source_format": extension,
            "source_bytes": len(data),
            "columns": columns,
        }

        original = deepcopy(approved)

        result = construct_approved_json_csv_rows(
            data,
            extension,
            approved,
            ["First Name (or Initial)"],
            source_hash,
            record_array_path="/people",
        )

        self.assertEqual(approved, original)
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            source_hash,
        )

        return result, approved

    def parents(self):

        return [
            {"people": [
                {"first_name": "Avery"},
                {"first_name": "Jordan"},
            ]},
            {"people": [
                {"first_name": "Morgan"},
            ]},
        ]

    def verify_valid(self, native, pointers, extension="json"):

        result, approved = self.construct(
            native, extension
        )

        self.assertEqual(
            result["rows"],
            [
                ["First Name (or Initial)"],
                ["Avery"],
                ["Jordan"],
                ["Morgan"],
            ],
        )

        self.assertEqual(result["mapped_row_count"], 3)
        self.assertEqual(result["row_source_pointers"], pointers)

        self.assertEqual(
            _validated_native_json_pointers(
                result, approved, 3
            ),
            pointers,
        )

    def test_multiple_parent_arrays(self):

        self.verify_valid(
            self.parents(),
            [
                "/0/people/0",
                "/0/people/1",
                "/1/people/0",
            ],
        )

    def test_records_container_parents(self):

        self.verify_valid(
            {"records": self.parents()},
            [
                "/records/0/people/0",
                "/records/0/people/1",
                "/records/1/people/0",
            ],
        )

    def test_jsonl_parents(self):

        self.verify_valid(
            self.parents(),
            [
                "/0/people/0",
                "/0/people/1",
                "/1/people/0",
            ],
            "jsonl",
        )

    def test_ndjson_parents(self):

        self.verify_valid(
            self.parents(),
            [
                "/0/people/0",
                "/0/people/1",
                "/1/people/0",
            ],
            "ndjson",
        )

    def test_duplicate_pointer_rejected(self):

        result, approved = self.construct(self.parents())

        result["row_source_pointers"][1] = "/0/people/0"

        with self.assertRaises(MappedProcessingSetError):
            _validated_native_json_pointers(
                result, approved, 3
            )

    def test_wrong_boundary_rejected(self):

        result, approved = self.construct(self.parents())

        result["row_source_pointers"][1] = "/0/other/1"

        with self.assertRaises(MappedProcessingSetError):
            _validated_native_json_pointers(
                result, approved, 3
            )

    def test_skipped_child_rejected(self):

        result, approved = self.construct(self.parents())

        result["row_source_pointers"][1] = "/0/people/2"

        with self.assertRaises(MappedProcessingSetError):
            _validated_native_json_pointers(
                result, approved, 3
            )

    def test_parent_order_rejected(self):

        result, approved = self.construct(self.parents())

        result["row_source_pointers"].reverse()

        with self.assertRaises(MappedProcessingSetError):
            _validated_native_json_pointers(
                result, approved, 3
            )

    def test_mixed_container_prefix_rejected(self):

        result, approved = self.construct(self.parents())

        result["row_source_pointers"][2] = (
            "/records/1/people/0"
        )

        with self.assertRaises(MappedProcessingSetError):
            _validated_native_json_pointers(
                result, approved, 3
            )

    def test_missing_later_array_rejected(self):

        with self.assertRaises(JsonTransformError):
            self.construct([
                {"people": [{"first_name": "Avery"}]},
                {"other": "Synthetic"},
            ])

    def test_mixed_array_rejected(self):

        with self.assertRaises(JsonTransformError):
            self.construct({
                "people": [
                    {"first_name": "Avery"},
                    "invalid_record",
                ],
            })


if __name__ == "__main__":
    unittest.main()
