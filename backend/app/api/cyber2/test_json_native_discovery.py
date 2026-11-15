import hashlib
import json
import unittest

from json_native_discovery import (
    JsonDiscoveryError,
    discover_json_native,
)


class NativeDiscoveryTests(unittest.TestCase):

    def test_record_array_and_hash(self):
        data = b'{"records":[{"Email":"a@example.com"},{"Email":"b@example.com"}]}'
        result = discover_json_native(data, "json")
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        self.assertFalse(result["csv_generated"])
        self.assertEqual(result["preview"][1]["source_pointer"], "/records/1")

    def test_nested_fields(self):
        data = b'{"records":[{"Name":{"First":"Jane"},"Phones":["123","456"]}]}'
        result = discover_json_native(data, "json")
        fields = {field["json_pointer"] for field in result["fields"]}
        self.assertIn("/Name/First", fields)
        self.assertIn("/Phones/0", fields)
        self.assertIn("/Phones/1", fields)

    def test_jsonl(self):
        data = b'{"Name":"Jane"}\n{"Name":"Alex"}\n'
        result = discover_json_native(data, "jsonl")
        self.assertEqual(result["record_count"], 2)

    def test_bounded_preview(self):
        data = json.dumps([{"id": i} for i in range(40)]).encode()
        result = discover_json_native(data, "json", max_preview_records=5)
        self.assertEqual(result["record_count"], 40)
        self.assertEqual(result["preview_record_count"], 5)
        self.assertTrue(result["preview_truncated"])

    def test_malformed_fails_closed(self):
        with self.assertRaises(JsonDiscoveryError):
            discover_json_native(b'{"bad":', "json")

    def test_size_limit_fails_closed(self):
        with self.assertRaises(JsonDiscoveryError):
            discover_json_native(b'{"Name":"Jane"}', "json", max_bytes=5)

    def test_json_pointer_escaping(self):
        result = discover_json_native(b'{"a/b":{"x~y":1}}', "json")
        fields = {f["json_pointer"] for f in result["fields"]}
        self.assertIn("/a~1b/x~0y", fields)


if __name__ == "__main__":
    unittest.main()