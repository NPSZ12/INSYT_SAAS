import hashlib
import json
import unittest

from json_mapped_preview import (
    JsonTransformError,
    preview_json_mapped_rows,
    decisions_from_approved_json_mapping,
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

    def test_keep_unapproved_secondary_identifier(self):
        data = json.dumps([{
            "first_name": "Avery",
            "email": "avery@example.invalid",
        }]).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = []

        for field in evidence["fields"]:
            pointer = field["json_pointer"]
            is_name = pointer == "/first_name"
            decisions.append({
                "json_pointer": pointer,
                "action": "map" if is_name else "keep",
                "header": (
                    "First Name (or Initial)" if is_name
                    else "collection.people.[].email"
                ),
                "treatment": "text",
                "reviewed": True,
            })

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["First Name (or Initial)"],
            hashlib.sha256(data).hexdigest(),
        )

        values = result["preview"][0]["values"]
        self.assertEqual(
            values["First Name (or Initial)"], "Avery"
        )
        self.assertEqual(
            values["collection.people.[].email"],
            "avery@example.invalid",
        )
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["source_modified"])

    def test_unapproved_protocol_mapping_still_rejected(self):
        data = json.dumps([{
            "email": "avery@example.invalid"
        }]).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = [{
            "json_pointer": field["json_pointer"],
            "action": "map",
            "header": "Email",
            "treatment": "text",
            "reviewed": True,
        } for field in evidence["fields"]]

        with self.assertRaises(JsonTransformError):
            preview_json_mapped_rows(
                data,
                "json",
                decisions,
                ["First Name (or Initial)"],
                hashlib.sha256(data).hexdigest(),
            )

    def test_kept_headers_receive_duplicate_suffixes(self):
        data = json.dumps([{
            "email": "first@example.invalid",
            "alternate_email": "second@example.invalid",
        }]).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = [{
            "json_pointer": field["json_pointer"],
            "action": "keep",
            "header": "Secondary Email",
            "treatment": "text",
            "reviewed": True,
        } for field in evidence["fields"]]

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["First Name (or Initial)"],
            hashlib.sha256(data).hexdigest(),
        )

        self.assertEqual(
            result["output_headers"],
            ["Secondary Email", "Secondary Email_2"],
        )
        self.assertEqual(
            set(result["preview"][0]["values"].values()),
            {
                "first@example.invalid",
                "second@example.invalid",
            },
        )

    def test_explicit_person_record_boundary(self):
        data = json.dumps({
            "collection": {
                "people": [
                    {
                        "first_name": "Avery",
                        "fname": "Avery",
                        "email": "avery@example.invalid",
                    },
                    {
                        "first_name": "Jordan",
                        "fname": "Jordan",
                        "email": "jordan@example.invalid",
                    },
                ]
            }
        }).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = []

        for field in evidence["fields"]:
            pointer = field["json_pointer"]

            if pointer.endswith(("/first_name", "/fname")):
                action = "map"
                header = "First Name (or Initial)"
                treatment = "text"
            elif pointer.endswith("/email"):
                action = "keep"
                header = "Secondary Email"
                treatment = "text"
            else:
                action = "discard"
                header = ""
                treatment = "discard"

            decisions.append({
                "json_pointer": pointer,
                "action": action,
                "header": header,
                "treatment": treatment,
                "reviewed": True,
            })

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["First Name (or Initial)"],
            hashlib.sha256(data).hexdigest(),
            record_array_path="/collection/people",
        )

        self.assertEqual(result["record_count"], 2)
        self.assertEqual(
            [r["source_pointer"] for r in result["preview"]],
            ["/collection/people/0", "/collection/people/1"],
        )

        headers = result["output_headers"]
        self.assertIn("First Name (or Initial)", headers)
        self.assertIn("First Name (or Initial)_2", headers)
        self.assertIn("Secondary Email", headers)

        first = result["preview"][0]["values"]
        second = result["preview"][1]["values"]

        for name, row, email in [
            ("Avery", first, "avery@example.invalid"),
            ("Jordan", second, "jordan@example.invalid"),
        ]:
            self.assertEqual(row["First Name (or Initial)"], name)
            self.assertEqual(row["First Name (or Initial)_2"], name)
            self.assertEqual(row["Secondary Email"], email)

        self.assertFalse(result["source_modified"])
        self.assertFalse(result["csv_generated"])

    def test_invalid_explicit_boundary_rejected(self):
        data = json.dumps({
            "collection": {
                "people": [{"first_name": "Avery"}]
            }
        }).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = []

        for field in evidence["fields"]:
            selected = field["json_pointer"].endswith("/first_name")
            decisions.append({
                "json_pointer": field["json_pointer"],
                "action": "map" if selected else "discard",
                "header": "First Name" if selected else "",
                "treatment": "text" if selected else "discard",
                "reviewed": True,
            })

        with self.assertRaises(JsonTransformError):
            preview_json_mapped_rows(
                data,
                "json",
                decisions,
                ["First Name"],
                hashlib.sha256(data).hexdigest(),
                record_array_path="/collection/missing",
            )

    def test_repeated_person_values_are_not_collapsed(self):
        data = json.dumps({
            "collection": {
                "people": [{
                    "first_name": "Avery",
                    "phones": ["111", "222"],
                }]
            }
        }).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        decisions = []

        for field in evidence["fields"]:
            pointer = field["json_pointer"]
            selected = pointer.endswith(
                ("/first_name", "/phones/[]")
            )
            decisions.append({
                "json_pointer": pointer,
                "action": "keep" if selected else "discard",
                "header": pointer if selected else "",
                "treatment": "text" if selected else "discard",
                "reviewed": True,
            })

        with self.assertRaises(JsonTransformError):
            preview_json_mapped_rows(
                data,
                "json",
                decisions,
                ["First Name"],
                hashlib.sha256(data).hexdigest(),
                record_array_path="/collection/people",
            )

    def test_reviewer_approved_custom_rename(self):
        data = json.dumps([
            {"secondary_id": "SYNTHETIC-001"}
        ]).encode("utf-8")

        evidence = discover_json_header_evidence(
            data, "json"
        )

        decisions = [{
            "json_pointer": field["json_pointer"],
            "action": "rename",
            "header": "Secondary Identifier",
            "treatment": "text",
            "reviewed": True,
        } for field in evidence["fields"]]

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["First Name (or Initial)"],
            hashlib.sha256(data).hexdigest(),
        )

        self.assertEqual(
            result["output_headers"],
            ["Secondary Identifier"],
        )
        self.assertEqual(
            result["preview"][0]["values"][
                "Secondary Identifier"
            ],
            "SYNTHETIC-001",
        )
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["source_modified"])

    def test_saved_approval_converts_to_existing_json_decisions(self):
        data = json.dumps({
            "collection": {
                "people": [
                    {
                        "first_name": "Avery",
                        "fname": "Avery",
                        "email": "avery@example.invalid",
                        "batch_key": "DROP",
                    },
                    {
                        "first_name": "Jordan",
                        "fname": "Jordan",
                        "email": "jordan@example.invalid",
                        "batch_key": "DROP",
                    },
                ]
            }
        }).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")
        columns = []

        for field in evidence["fields"]:
            pointer = field["json_pointer"]

            if field["kind"] != "scalar":
                continue

            if pointer.endswith(("/first_name", "/fname")):
                disposition = "approve"
                header = "First Name (or Initial)"
            elif pointer.endswith("/email"):
                disposition = "keep"
                header = "collection.people.[].email"
            else:
                disposition = "delete"
                header = ""

            columns.append({
                "json_pointer": pointer,
                "disposition": disposition,
                "final_header": header,
                "delete_column": disposition == "delete",
            })

        decisions = decisions_from_approved_json_mapping(
            {"columns": columns},
            evidence,
            ["First Name (or Initial)"],
        )

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["First Name (or Initial)"],
            hashlib.sha256(data).hexdigest(),
            record_array_path="/collection/people",
        )

        self.assertEqual(result["record_count"], 2)
        self.assertEqual(
            result["output_headers"],
            [
                "collection.people.[].email",
                "First Name (or Initial)",
                "First Name (or Initial)_2",
            ],
        )
        self.assertEqual(
            result["preview"][1]["values"]["First Name (or Initial)"],
            "Jordan",
        )
        self.assertEqual(
            result["preview"][1]["values"][
                "collection.people.[].email"
            ],
            "jordan@example.invalid",
        )
        self.assertNotIn(
            "DROP", str(result["preview"])
        )
        self.assertFalse(result["csv_generated"])

    def test_saved_mapping_rejects_missing_scalar_decision(self):
        data = json.dumps({"name": "Avery"}).encode("utf-8")
        evidence = discover_json_header_evidence(data, "json")

        with self.assertRaises(JsonTransformError):
            decisions_from_approved_json_mapping(
                {"columns": []}, evidence, ["Name"]
            )

    def test_saved_mapping_rejects_unapproved_protocol_target(self):
        data = json.dumps({"email": "a@example.invalid"}).encode("utf-8")
        evidence = discover_json_header_evidence(data, "json")

        with self.assertRaises(JsonTransformError):
            decisions_from_approved_json_mapping(
                {"columns": [{
                    "json_pointer": "/email",
                    "disposition": "map",
                    "final_header": "Email",
                    "delete_column": False,
                }]},
                evidence,
                ["First Name (or Initial)"],
            )

    def test_full_rows_exceed_preview_limit(self):
        data = json.dumps([
            {"name": f"Person-{i:03d}"}
            for i in range(30)
        ]).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")

        decisions = [{
            "json_pointer": field["json_pointer"],
            "action": "map",
            "header": "Name",
            "treatment": "text",
            "reviewed": True,
        } for field in evidence["fields"]]

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["Name"],
            hashlib.sha256(data).hexdigest(),
            include_all_rows=True,
        )

        self.assertEqual(result["record_count"], 30)
        self.assertEqual(len(result["preview"]), 25)
        self.assertTrue(result["preview_truncated"])
        self.assertEqual(len(result["all_rows"]), 31)
        self.assertEqual(result["all_rows"][0], ["Name"])
        self.assertEqual(result["all_rows"][1], ["Person-000"])
        self.assertEqual(result["all_rows"][30], ["Person-029"])
        self.assertEqual(
            len(result["row_source_pointers"]), 30
        )
        self.assertEqual(
            result["row_source_pointers"][-1], "/29"
        )
        self.assertFalse(result["csv_generated"])
        self.assertFalse(result["source_modified"])

    def test_default_preview_does_not_materialize_csv_rows(self):
        data = json.dumps([
            {"name": "Avery"}
        ]).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")

        decisions = [{
            "json_pointer": field["json_pointer"],
            "action": "map",
            "header": "Name",
            "treatment": "text",
            "reviewed": True,
        } for field in evidence["fields"]]

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["Name"],
            hashlib.sha256(data).hexdigest(),
        )

        self.assertIsNone(result["all_rows"])
        self.assertIsNone(result["row_source_pointers"])
        self.assertFalse(result["csv_generated"])

    def test_full_rows_retain_nested_source_pointers(self):
        data = json.dumps({
            "collection": {
                "people": [
                    {"name": "Avery"},
                    {"name": "Jordan"},
                ]
            }
        }).encode("utf-8")

        evidence = discover_json_header_evidence(data, "json")

        decisions = []
        for field in evidence["fields"]:
            selected = field["json_pointer"].endswith("/name")
            decisions.append({
                "json_pointer": field["json_pointer"],
                "action": "map" if selected else "discard",
                "header": "Name" if selected else "",
                "treatment": "text" if selected else "discard",
                "reviewed": True,
            })

        result = preview_json_mapped_rows(
            data,
            "json",
            decisions,
            ["Name"],
            hashlib.sha256(data).hexdigest(),
            record_array_path="/collection/people",
            include_all_rows=True,
        )

        self.assertEqual(
            result["all_rows"],
            [["Name"], ["Avery"], ["Jordan"]],
        )
        self.assertEqual(
            result["row_source_pointers"],
            ["/collection/people/0", "/collection/people/1"],
        )
        self.assertFalse(result["csv_generated"])

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