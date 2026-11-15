import json
import unittest

from json_header_evidence import discover_json_header_evidence
from json_header_review_contract import (
    JsonHeaderReviewError,
    build_json_header_review,
)


def review(records, headers):
    data = json.dumps(records).encode("utf-8")
    evidence = discover_json_header_evidence(data, "json")
    return build_json_header_review(evidence, headers)


class JsonHeaderReviewContractTests(unittest.TestCase):

    def test_uses_csv_header_column_shape(self):
        result = review(
            [{"Name": "Jane"}],
            ["Name", "Email"],
        )
        row = next(
            c for c in result["columns"]
            if c["json_pointer"] == "/Name"
        )
        self.assertEqual(row["source_header"], "Name")
        self.assertEqual(row["sample_values"], ["Jane"])
        self.assertEqual(
            row["recommended_protocol_header"], "Name"
        )
        self.assertEqual(row["match_method"], "protocol_exact")
        self.assertIsNone(row["ai_confidence"])

    def test_unapproved_field_not_mapped(self):
        result = review(
            [{"secret_internal": "value"}],
            ["First Name"],
        )
        row = result["columns"][0]
        self.assertIsNone(
            row["recommended_protocol_header"]
        )
        self.assertEqual(row["default_disposition"], "delete")

    def test_nested_fields_and_arrays_visible(self):
        result = review(
            [{
                "person": {"first": "John"},
                "phones": [
                    {"number": "555-0101"},
                    {"number": "555-0102"},
                ],
            }],
            ["First Name", "Phone Numbers"],
        )
        paths = {
            row["json_pointer"]: row
            for row in result["columns"]
        }
        self.assertIn("/person/first", paths)
        self.assertIn("/phones/[]/number", paths)
        self.assertEqual(
            paths["/phones/[]/number"]["sample_values"],
            ["555-0101", "555-0102"],
        )

    def test_structural_parent_not_silently_mapped(self):
        result = review(
            [{"Payments": [{"amount": 25}]}],
            ["Payments"],
        )
        parent = next(
            c for c in result["columns"]
            if c["json_pointer"] == "/Payments"
        )
        self.assertIsNone(
            parent["recommended_protocol_header"]
        )

    def test_review_has_no_approval_or_csv(self):
        result = review(
            [{"Name": "Jane"}],
            ["Name"],
        )
        self.assertFalse(result["mapping_approved"])
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["ai_invoked"])

    def test_all_treatment_options_declared(self):
        result = review(
            [{"x": "value"}],
            ["X"],
        )
        treatments = result["columns"][0][
            "allowed_data_treatments"
        ]
        self.assertIn("concatenate", treatments)
        self.assertIn("yes_if_present", treatments)
        self.assertIn("mask", treatments)
        self.assertIn("discard", treatments)

    def test_duplicate_protocol_headers_rejected(self):
        data = discover_json_header_evidence(
            b'[{"a":1}]', "json"
        )
        with self.assertRaises(JsonHeaderReviewError):
            build_json_header_review(
                data, ["First Name", "first_name"]
            )

    def test_incomplete_evidence_rejected(self):
        data = discover_json_header_evidence(
            b'[{"a":1}]', "json"
        )
        data["structure_scan_complete"] = False
        with self.assertRaises(JsonHeaderReviewError):
            build_json_header_review(data, ["A"])


if __name__ == "__main__":
    unittest.main()