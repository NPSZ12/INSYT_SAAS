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




class JsonHeaderAiIntegrationTests(unittest.TestCase):

    def test_ai_suggestions_are_protocol_bound_and_unapproved(self):
        result = review(
            [{"employee": {
                "first_name": "Taylor",
                "email": "taylor.morgan@example.com",
                "ssn": "123-45-6789",
            }}],
            ["First Name", "Email Address", "Social Security Number"],
        )

        from json_header_review_contract import (
            enrich_json_header_review_with_ai,
        )

        captured = []

        def fake_ai(**kwargs):
            captured.append(kwargs)
            name = kwargs["source_header"].replace("/", ".").rsplit(".", 1)[-1]
            recommendations = {
                "first_name": "First Name",
                "email": "Email Address",
                "ssn": "Social Security Number",
            }
            return {
                "ai_invoked": True,
                "ai_status": "completed",
                "ai_recommendation": recommendations.get(name, ""),
                "ai_confidence": 0.92,
                "ai_reason": "Matches approved protocol meaning.",
            }

        mapped = enrich_json_header_review_with_ai(
            result, ai_resolver=fake_ai
        )

        self.assertTrue(mapped["ai_invoked"])
        self.assertFalse(mapped["mapping_approved"])
        self.assertFalse(mapped["csv_generated"])
        self.assertEqual(len(captured), 3)

        transmitted = str(captured)
        self.assertNotIn("Taylor", transmitted)
        self.assertNotIn("123-45-6789", transmitted)
        self.assertNotIn("taylor.morgan@example.com", transmitted)

        suggestions = {
            col["json_pointer"]: col["recommended_protocol_header"]
            for col in mapped["columns"]
            if col["json_kind"] == "scalar"
        }
        self.assertEqual(
            suggestions["/employee/first_name"], "First Name"
        )
        self.assertEqual(
            suggestions["/employee/email"], "Email Address"
        )
        self.assertEqual(
            suggestions["/employee/ssn"], "Social Security Number"
        )

    def test_ai_cannot_invent_protocol_headers(self):
        from json_header_review_contract import (
            enrich_json_header_review_with_ai,
        )

        result = review(
            [{"unmapped_field": "Example"}],
            ["Approved Header"],
        )

        mapped = enrich_json_header_review_with_ai(
            result,
            ai_resolver=lambda **kwargs: {
                "ai_invoked": True,
                "ai_status": "completed",
                "ai_recommendation": "Unauthorized Header",
                "ai_confidence": 0.99,
                "ai_reason": "Rejected",
            },
        )

        col = mapped["columns"][0]
        self.assertFalse(col["recommended_protocol_header"])
        self.assertFalse(col["approved"])
        self.assertFalse(mapped["csv_generated"])

    def test_normal_json_preview_never_invokes_ai(self):
        result = review(
            [{"first_name": "Taylor"}],
            ["First Name"],
        )
        self.assertFalse(result["ai_invoked"])
        self.assertFalse(result["mapping_approved"])
        self.assertFalse(result["csv_generated"])


if __name__ == "__main__":
    unittest.main()