import json
import unittest

from json_header_evidence import (
    JsonEvidenceError,
    discover_json_header_evidence,
)


def discover(obj, ext="json"):
    data = (
        obj if isinstance(obj, bytes)
        else json.dumps(obj).encode("utf-8")
    )
    return discover_json_header_evidence(data, ext)


class JsonHeaderEvidenceTests(unittest.TestCase):

    def test_plain_and_nested_fields(self):
        result = discover([{
            "person": {
                "first_name": "John",
                "address": {"city": "Nashville"},
            },
        }])
        paths = {
            field["json_pointer"]
            for field in result["fields"]
        }
        self.assertIn("/person/first_name", paths)
        self.assertIn("/person/address/city", paths)

    def test_array_fields_preserve_relationships(self):
        result = discover([{
            "phones": [
                {"type": "Mobile", "number": "555-0101"},
                {"type": "Home", "number": "555-0102"},
            ]
        }])
        entry = next(
            f for f in result["fields"]
            if f["json_pointer"] == "/phones/[]/number"
        )
        self.assertEqual(
            entry["sample_values"],
            ["555-0101", "555-0102"]
        )
        self.assertEqual(
            entry["sample_source_pointers"],
            ["/0/phones/0/number", "/0/phones/1/number"]
        )
        self.assertEqual(entry["record_count_with_field"], 1)

    def test_nested_array_presence(self):
        result = discover([{
            "financial": {
                "payments": [{"amount": 25}, {"amount": 30}]
            }
        }])
        paths = {f["json_pointer"]: f for f in result["fields"]}
        self.assertEqual(
            paths["/financial/payments"]["kind"], "array"
        )
        self.assertEqual(
            paths["/financial/payments/[]/amount"]["occurrence_count"],
            2,
        )

    def test_missing_field_counts(self):
        result = discover([
            {"person": {"first": "John"}},
            {"other": 1},
        ])
        field = next(
            f for f in result["fields"]
            if f["json_pointer"] == "/person/first"
        )
        self.assertEqual(field["record_count_without_field"], 1)

    def test_jsonl(self):
        result = discover(
            b'{"x":1}\n{"x":2}\n',
            "jsonl"
        )
        self.assertEqual(result["record_count"], 2)

    def test_full_source_not_just_preview(self):
        records = [{"value": i} for i in range(30)]
        records[29]["extra"] = "last record"
        result = discover(records)
        self.assertIn(
            "/extra",
            [f["json_pointer"] for f in result["fields"]],
        )

    def test_original_unchanged_no_csv(self):
        data = b'[{"name":"Jane"}]'
        result = discover(data)
        self.assertEqual(data, b'[{"name":"Jane"}]')
        self.assertFalse(result["source_modified"])
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["ai_invoked"])

    def test_malformed_fails_closed(self):
        with self.assertRaises(JsonEvidenceError):
            discover(b'{"notvalid":', "json")

    def test_large_source_fails_closed(self):
        with self.assertRaises(JsonEvidenceError):
            discover(b" " * (4 * 1024 * 1024 + 1))

    def test_escaped_source_pointer(self):
        result = discover([{"a/b": {"x~y": "yes"}}])
        paths = [f["json_pointer"] for f in result["fields"]]
        self.assertIn("/a~1b/x~0y", paths)


if __name__ == "__main__":
    unittest.main()