import unittest

from json_record_boundaries import discover_record_boundaries


def field(pointer, kind):
    return {
        "json_pointer": pointer,
        "json_kind": kind,
    }


class JsonRecordBoundaryTests(unittest.TestCase):

    def test_root_object(self):
        result = discover_record_boundaries([
            field("/first_name", "scalar"),
            field("/last_name", "scalar"),
        ])
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["record_array_path"])

    def test_nested_object_array(self):
        result = discover_record_boundaries([
            field("/collection", "object"),
            field("/collection/people", "array"),
            field("/collection/people/[]", "object"),
            field("/collection/people/[]/first_name", "scalar"),
        ])
        self.assertEqual(
            result[1]["record_array_path"],
            "/collection/people",
        )

    def test_multiple_record_arrays(self):
        result = discover_record_boundaries([
            field("/people", "array"),
            field("/people/[]", "object"),
            field("/contacts", "array"),
            field("/contacts/[]", "object"),
        ])
        self.assertEqual(
            [x["selection_id"] for x in result],
            ["root", "/contacts", "/people"],
        )

    def test_primitive_array_not_record_boundary(self):
        result = discover_record_boundaries([
            field("/phone_numbers", "array"),
            field("/phone_numbers/[]", "scalar"),
        ])
        self.assertEqual(len(result), 1)

    def test_mixed_array_not_record_boundary(self):
        result = discover_record_boundaries([
            field("/records", "array"),
            field("/records/[]", "mixed"),
        ])
        self.assertEqual(len(result), 1)

    def test_embedded_child_array_not_flattened(self):
        result = discover_record_boundaries([
            field("/people", "array"),
            field("/people/[]", "object"),
            field("/people/[]/policies", "array"),
            field("/people/[]/policies/[]", "object"),
        ])
        self.assertEqual(
            [x["selection_id"] for x in result],
            ["root", "/people"],
        )

    def test_duplicate_pointer_rejected(self):
        with self.assertRaises(ValueError):
            discover_record_boundaries([
                field("/people", "array"),
                field("/people", "object"),
            ])

    def test_missing_pointer_rejected(self):
        with self.assertRaises(ValueError):
            discover_record_boundaries([
                {"json_kind": "scalar"},
            ])

    def test_no_definitive_record_counts(self):
        result = discover_record_boundaries([
            field("/people", "array"),
            field("/people/[]", "object"),
        ])
        for candidate in result:
            self.assertNotIn("record_count", candidate)
            self.assertNotIn("row_count", candidate)



from copy import deepcopy

from json_record_boundaries import (
    approved_record_boundary_options,
)


class ApprovedBoundaryIntegrationTests(unittest.TestCase):

    def setUp(self):
        identity = {
            "doc_id": "INSYT000000077",
            "source_kind": "native_json",
            "source_sha256": "a" * 64,
            "source_native_path": "synthetic/native/doc077.json",
            "source_format": "json",
        }

        columns = [
            {
                "column_index": 0,
                "json_pointer": "/collection/people/[]/first_name",
                "json_kind": "scalar",
                "final_header": "First Name (or Initial)",
                "delete_column": False,
            },
            {
                "column_index": 1,
                "json_pointer": "/collection/people/[]/fname",
                "json_kind": "scalar",
                "final_header": "First Name (or Initial)",
                "delete_column": False,
            },
        ]

        self.approved = {
            "status": "approved",
            "documents": [{
                **identity,
                "columns": deepcopy(columns),
            }],
        }

        self.identification = {
            "documents": [{
                **identity,
                "identification_status": "COMPLETED",
                "columns": deepcopy(columns),
                "structural_fields": [
                    field("/collection", "object"),
                    field("/collection/people", "array"),
                    field("/collection/people/[]", "object"),
                ],
            }],
        }

    def options(self):
        return approved_record_boundary_options(
            self.approved,
            self.identification,
        )["INSYT000000077"]

    def test_existing_approved_mapping(self):
        result = self.options()

        self.assertEqual(result["status"], "available")
        self.assertEqual(
            [x["selection_id"] for x in result["options"]],
            ["/collection/people"],
        )

    def test_approved_mapping_not_mutated(self):
        original = deepcopy(self.approved)
        self.options()
        self.assertEqual(self.approved, original)

    def test_identification_not_mutated(self):
        original = deepcopy(self.identification)
        self.options()
        self.assertEqual(self.identification, original)

    def test_source_hash_mismatch(self):
        self.identification["documents"][0][
            "source_sha256"
        ] = "b" * 64

        self.assertEqual(
            self.options()["status"],
            "needs_review",
        )

    def test_source_path_mismatch(self):
        self.identification["documents"][0][
            "source_native_path"
        ] = "synthetic/native/other.json"

        self.assertEqual(
            self.options()["status"],
            "needs_review",
        )

    def test_missing_structural_evidence(self):
        del self.identification["documents"][0][
            "structural_fields"
        ]

        self.assertEqual(
            self.options()["status"],
            "needs_review",
        )

    def test_missing_approved_field(self):
        self.approved["documents"][0]["columns"].pop()

        self.assertEqual(
            self.options()["status"],
            "needs_review",
        )

    def test_missing_identification_document(self):
        self.identification["documents"] = []

        self.assertEqual(
            self.options()["status"],
            "needs_review",
        )

    def test_duplicate_identification_document(self):
        self.identification["documents"].append(
            deepcopy(self.identification["documents"][0])
        )

        with self.assertRaises(ValueError):
            self.options()

    def test_unapproved_mapping_returns_no_options(self):
        self.assertEqual(
            approved_record_boundary_options(
                None,
                self.identification,
            ),
            {},
        )

    def test_root_record_candidate(self):
        for document in (
            self.approved["documents"][0],
            self.identification["documents"][0],
        ):
            document["columns"] = [{
                "column_index": 0,
                "json_pointer": "/first_name",
                "json_kind": "scalar",
                "delete_column": False,
            }]

        self.identification["documents"][0][
            "structural_fields"
        ] = []

        result = self.options()

        self.assertEqual(result["status"], "available")
        self.assertEqual(
            result["options"][0]["selection_id"],
            "root",
        )

    def test_regular_csv_unchanged(self):
        self.approved["documents"].append({
            "doc_id": "CSV001",
            "source_kind": "csv",
        })

        self.assertNotIn(
            "CSV001",
            approved_record_boundary_options(
                self.approved,
                self.identification,
            ),
        )


if __name__ == "__main__":
    unittest.main()
