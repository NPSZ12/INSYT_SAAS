import ast
import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("mapped_processing_set.py")


def load_validator():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_validated_native_json_pointers"
    ]

    assert len(matches) == 1

    class ValidationError(ValueError):
        pass

    def require(condition, message):
        if not condition:
            raise ValidationError(message)

    namespace = {
        "__name__": "synthetic_validation",
        "_require": require,
        "re": __import__("re"),
    }

    import copy

    function = copy.deepcopy(matches[0])

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )

    exec(
        compile(ast.fix_missing_locations(module), str(SOURCE), "exec"),
        namespace,
    )

    return namespace["_validated_native_json_pointers"], ValidationError


class NativeJsonMappedProvenanceTests(unittest.TestCase):

    def setUp(self):
        self.validate, self.error = load_validator()
        self.approved = {
            "source_kind": "native_json",
            "source_native_path": "synthetic/source/native/DOC077.json",
            "source_sha256": "a" * 64,
        }
        self.document = {
            **self.approved,
            "record_array_path": "/collection/people",
            "row_source_pointers": [
                "/collection/people/0",
                "/collection/people/1",
            ],
        }

    def test_valid_native_record_pointers(self):
        self.assertEqual(
            self.validate(self.document, self.approved, 2),
            [
                "/collection/people/0",
                "/collection/people/1",
            ],
        )

    def test_missing_record_pointer_rejected(self):
        self.document["row_source_pointers"].pop()

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_misordered_record_pointer_rejected(self):
        self.document["row_source_pointers"].reverse()

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_native_hash_mismatch_rejected(self):
        self.document["source_sha256"] = "b" * 64

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_regular_csv_retains_existing_behavior(self):
        self.assertIsNone(
            self.validate(
                {"source_kind": "csv"},
                {"source_kind": "csv"},
                2,
            )
        )

    def test_native_manifest_cannot_impersonate_csv(self):
        with self.assertRaises(self.error):
            self.validate(
                self.document,
                {"source_kind": "csv"},
                2,
            )



class RootJsonProvenanceTests(unittest.TestCase):

    def setUp(self):
        self.validate, self.error = load_validator()

        self.approved = {
            "source_kind": "native_json",
            "source_native_path": "synthetic/native/DOC001.json",
            "source_sha256": "a" * 64,
            "source_format": "json",
        }

        self.document = {
            **self.approved,
            "record_array_path": None,
            "row_source_pointers": ["/0", "/1"],
        }

    def test_root_object(self):
        self.document["row_source_pointers"] = ["/0"]

        self.assertEqual(
            self.validate(self.document, self.approved, 1),
            ["/0"],
        )

    def test_root_array(self):
        self.assertEqual(
            self.validate(self.document, self.approved, 2),
            ["/0", "/1"],
        )

    def test_standard_records_container(self):
        self.document["row_source_pointers"] = [
            "/records/0",
            "/records/1",
        ]

        self.assertEqual(
            self.validate(self.document, self.approved, 2),
            ["/records/0", "/records/1"],
        )

    def test_jsonl_records(self):
        self.approved["source_format"] = "jsonl"
        self.document["source_format"] = "jsonl"

        self.assertEqual(
            self.validate(self.document, self.approved, 2),
            ["/0", "/1"],
        )

    def test_ndjson_records(self):
        self.approved["source_format"] = "ndjson"
        self.document["source_format"] = "ndjson"

        self.assertEqual(
            self.validate(self.document, self.approved, 2),
            ["/0", "/1"],
        )

    def test_missing_boundary_metadata_rejected(self):
        del self.document["record_array_path"]

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_mixed_root_prefixes_rejected(self):
        self.document["row_source_pointers"] = [
            "/0",
            "/records/1",
        ]

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_duplicate_root_pointer_rejected(self):
        self.document["row_source_pointers"] = [
            "/0",
            "/0",
        ]

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_misordered_root_pointers_rejected(self):
        self.document["row_source_pointers"] = [
            "/1",
            "/0",
        ]

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_source_format_mismatch_rejected(self):
        self.document["source_format"] = "jsonl"

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_jsonl_records_container_rejected(self):
        self.approved["source_format"] = "jsonl"
        self.document["source_format"] = "jsonl"

        self.document["row_source_pointers"] = [
            "/records/0",
            "/records/1",
        ]

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)

    def test_root_source_hash_mismatch_rejected(self):
        self.document["source_sha256"] = "b" * 64

        with self.assertRaises(self.error):
            self.validate(self.document, self.approved, 2)


if __name__ == "__main__":
    unittest.main()
