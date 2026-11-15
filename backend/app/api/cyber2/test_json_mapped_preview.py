import hashlib
import json
import unittest

from json_mapped_preview import (
    JsonTransformError,
    preview_json_mapped_rows,
)
from json_header_evidence import discover_json_header_evidence


def convert(records, selections, headers):
    data = json.dumps(records).encode("utf-8")
    evidence = discover_json_header_evidence(data, "json")
    decision_by_path = {
        path: (header, treatment)
        for path, header, treatment in selections
    }
    decisions = []
    for field in evidence["fields"]:
        path = field["json_pointer"]
        if path in decision_by_path:
            header, treatment = decision_by_path[path]
            action = "map"
        else:
            header, treatment, action = "", "discard", "discard"
        decisions.append({
            "json_pointer": path,
            "header": header,
            "treatment": treatment,
            "action": action,
            "reviewed": True,
        })
    return preview_json_mapped_rows(
        data, "json", decisions, headers,
        hashlib.sha256(data).hexdigest(),
    )


class JsonMappedPreviewTests(unittest.TestCase):

    def test_plain_and_nested_values(self):
        result = convert(
            [{"person": {"first": "Jane"}}],
            [("/person/first", "First Name", "text")],
            ["First Name"],
        )
        self.assertEqual(
            result["preview"][0]["values"]["First Name"], "Jane"
        )

    def test_duplicate_headers(self):
        result = convert(
            [{"a": "one", "b": "two", "c": "three"}],
            [(f"/{x}", "Email", "text") for x in "abc"],
            ["Email"],
        )
        self.assertEqual(
            result["output_headers"], ["Email", "Email_2", "Email_3"]
        )
        self.assertEqual(
            list(result["preview"][0]["values"].values()),
            ["one", "two", "three"],
        )

    def test_concat_distinct_array_values(self):
        result = convert(
            [{"phones": [
                {"number": "111"},
                {"number": "222"},
                {"number": "111"},
            ]}],
            [("/phones/[]/number", "Phone", "concatenate")],
            ["Phone"],
        )
        self.assertEqual(
            result["preview"][0]["values"]["Phone"], "111; 222"
        )

    def test_text_does_not_drop_multiple_values(self):
        with self.assertRaises(JsonTransformError):
            convert(
                [{"phones": [{"number": "1"}, {"number": "2"}]}],
                [("/phones/[]/number", "Phone", "text")],
                ["Phone"],
            )

    def test_yes_if_present(self):
        result = convert(
            [{"payments": [{"amount": 25}]}, {"payments": []}],
            [("/payments", "Payment Present", "yes_if_present")],
            ["Payment Present"],
        )
        self.assertEqual(
            [r["values"]["Payment Present"] for r in result["preview"]],
            ["Yes", ""],
        )

    def test_mask_does_not_disclose_value(self):
        result = convert(
            [{"ssn": "000-00-0000"}],
            [("/ssn", "SSN", "mask")],
            ["SSN"],
        )
        self.assertEqual(
            result["preview"][0]["values"]["SSN"], "****"
        )

    def test_maximum(self):
        result = convert(
            [{"amounts": [5, 25, 10]}],
            [("/amounts/[]", "Maximum", "maximum")],
            ["Maximum"],
        )
        self.assertEqual(
            result["preview"][0]["values"]["Maximum"], "25"
        )

    def test_latest(self):
        result = convert(
            [{"dates": ["2024-01-01", "2026-10-01"]}],
            [("/dates/[]", "Latest Date", "latest")],
            ["Latest Date"],
        )
        self.assertTrue(
            result["preview"][0]["values"]["Latest Date"].startswith(
                "2026-10-01"
            )
        )

    def test_unapproved_data_excluded(self):
        result = convert(
            [{"name": "John", "debug": "secret"}],
            [("/name", "Name", "text")],
            ["Name"],
        )
        self.assertEqual(result["output_headers"], ["Name"])
        self.assertNotIn("secret", str(result["preview"]))

    def test_all_records_validated_not_only_preview(self):
        data = [{"x": i} for i in range(30)]
        result = convert(
            data, [("/x", "X", "text")], ["X"]
        )
        self.assertEqual(result["validated_record_count"], 30)
        self.assertEqual(len(result["preview"]), 25)

    def test_invalid_late_record_fails(self):
        records = [{"x": i} for i in range(30)]
        records[29]["x"] = [1, 2]
        with self.assertRaises(JsonTransformError):
            convert(
                records, [("/x", "X", "text")], ["X"]
            )

    def test_no_csv_or_source_mutation(self):
        result = convert(
            [{"x": "value"}], [("/x", "X", "text")], ["X"]
        )
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["source_modified"])
        self.assertFalse(result["mapping_saved"])


if __name__ == "__main__":
    unittest.main()