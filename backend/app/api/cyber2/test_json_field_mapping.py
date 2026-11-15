import json
import unittest

from json_field_mapping import (
    JsonMappingError,
    validate_json_field_mapping,
)


def mapping(data, columns, ext="json", **kwargs):
    if not isinstance(data, bytes):
        data = json.dumps(data).encode("utf-8")
    return validate_json_field_mapping(
        data, ext, columns, **kwargs
    )


class JsonFieldMappingTests(unittest.TestCase):

    def test_record_relative_email(self):
        result = mapping(
            {"records": [
                {"Email": "a@example.com"},
                {"Email": "b@example.com"},
            ]},
            [{"json_pointer": "/Email", "header": "Email"}],
        )
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(
            result["preview"][1]["values"]["Email"],
            "b@example.com",
        )
        self.assertEqual(
            result["preview"][1]["source_pointer"],
            "/records/1",
        )
        self.assertFalse(result["csv_generated"])

    def test_nested_field(self):
        result = mapping(
            [{"Name": {"First": "Jane"}}],
            [{"json_pointer": "/Name/First", "header": "First Name"}],
        )
        self.assertEqual(
            result["preview"][0]["values"]["First Name"],
            "Jane",
        )

    def test_jsonl(self):
        result = mapping(
            b'{"id":1}\n{"id":2}\n',
            [{"json_pointer": "/id", "header": "Identifier"}],
            "jsonl",
        )
        self.assertEqual(result["record_count"], 2)

    def test_missing_fields_are_counted(self):
        result = mapping(
            [{"a": 1}, {"b": 2}],
            [{"json_pointer": "/a", "header": "A"}],
        )
        self.assertEqual(
            result["columns"][0]["missing_count"], 1
        )
        self.assertEqual(
            result["columns"][0]["present_count"], 1
        )

    def test_full_source_validation_beyond_preview(self):
        rows = [{"a": i} for i in range(40)]
        rows[39]["a"] = [1, 2]
        with self.assertRaises(JsonMappingError):
            mapping(
                rows,
                [{"json_pointer": "/a", "header": "A"}],
                preview_limit=5,
            )

    def test_duplicate_headers_rejected(self):
        with self.assertRaises(JsonMappingError):
            mapping(
                [{"a": 1}],
                [
                    {"json_pointer": "/a", "header": "Name"},
                    {"json_pointer": "/a", "header": "name"},
                ],
            )

    def test_arrays_not_silently_flattened(self):
        with self.assertRaises(JsonMappingError):
            mapping(
                [{"Phones": ["123", "456"]}],
                [{"json_pointer": "/Phones", "header": "Phones"}],
            )

    def test_pointer_escaping(self):
        result = mapping(
            [{"a/b": {"x~y": "value"}}],
            [{"json_pointer": "/a~1b/x~0y", "header": "Field"}],
        )
        self.assertEqual(
            result["preview"][0]["values"]["Field"],
            "value",
        )

    def test_unsupported_format_rejected(self):
        with self.assertRaises(JsonMappingError):
            mapping(
                [{"a": 1}],
                [{"json_pointer": "/a", "header": "A"}],
                "csv",
            )

    def test_no_mutation_or_approval(self):
        data = b'[{"id":1}]'
        original = bytes(data)
        result = mapping(
            data,
            [{"json_pointer": "/id", "header": "ID"}],
        )
        self.assertEqual(data, original)
        self.assertFalse(result["mapping_saved"])
        self.assertFalse(result["mapping_approved"])
        self.assertFalse(result["source_modified"])


if __name__ == "__main__":
    unittest.main()