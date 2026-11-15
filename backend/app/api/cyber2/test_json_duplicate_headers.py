import unittest

from json_duplicate_headers import (
    DuplicateHeaderError,
    assign_json_output_headers,
)


def decision(pointer, header, treatment="text"):
    return {
        "json_pointer": pointer,
        "header": header,
        "action": "map",
        "treatment": treatment,
        "reviewed": True,
    }


class DuplicateHeaderTests(unittest.TestCase):

    def test_duplicate_headers_keep_2_and_3(self):
        result = assign_json_output_headers(
            [
                decision("/person/email", "Email"),
                decision("/primary/email", "Email"),
                decision("/secondary/email", "Email"),
            ],
            ["Email"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Email", "Email_2", "Email_3"],
        )

    def test_different_protocol_headers(self):
        result = assign_json_output_headers(
            [
                decision("/a", "Email"),
                decision("/b", "Phone"),
                decision("/c", "Email"),
            ],
            ["Email", "Phone"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Email", "Phone", "Email_2"],
        )

    def test_reserved_header_collision(self):
        result = assign_json_output_headers(
            [
                decision("/a", "Email"),
                decision("/b", "Email"),
                decision("/c", "Email_2"),
            ],
            ["Email", "Email_2"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Email", "Email_3", "Email_2"],
        )

    def test_treatments_do_not_merge_columns(self):
        result = assign_json_output_headers(
            [
                decision("/a", "Phone", "text"),
                decision("/b", "Phone", "concatenate"),
            ],
            ["Phone"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Phone", "Phone_2"],
        )
        self.assertEqual(
            result["columns"][1]["data_treatment"],
            "concatenate",
        )

    def test_discard_is_excluded(self):
        ignored = decision("/debug", "Email")
        ignored["action"] = "discard"
        ignored["treatment"] = "discard"

        result = assign_json_output_headers(
            [ignored, decision("/email", "Email")],
            ["Email"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Email"],
        )

    def test_unapproved_header_rejected(self):
        with self.assertRaises(DuplicateHeaderError):
            assign_json_output_headers(
                [decision("/x", "Unapproved")],
                ["Email"],
            )

    def test_unreviewed_decision_rejected(self):
        item = decision("/x", "Email")
        item["reviewed"] = False

        with self.assertRaises(DuplicateHeaderError):
            assign_json_output_headers([item], ["Email"])

    def test_duplicate_source_path_rejected(self):
        with self.assertRaises(DuplicateHeaderError):
            assign_json_output_headers(
                [
                    decision("/email", "Email"),
                    decision("/email", "Email"),
                ],
                ["Email"],
            )

    def test_no_csv_generated(self):
        result = assign_json_output_headers(
            [decision("/email", "Email")],
            ["Email"],
        )
        self.assertFalse(result["csv_generated"])


if __name__ == "__main__":
    unittest.main()