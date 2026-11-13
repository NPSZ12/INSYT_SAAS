from __future__ import annotations

import json
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from .json_router import detect_json_source_profile


class JsonStreamingDetectorTests(unittest.TestCase):

    def _detect(self, name, payload):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with patch(
                "app.services.structured_intake."
                "json_router.json.load",
                side_effect=AssertionError(
                    "Full-document JSON load prohibited"
                ),
            ):
                return detect_json_source_profile(path)

    def test_salesforce_query_wrapper(self):
        self.assertEqual(
            self._detect("export.json", {
                "totalSize": 1,
                "done": True,
                "records": [{
                    "attributes": {"type": "Contact"},
                    "Id": "003TEST",
                }],
            }),
            "salesforce",
        )

    def test_salesforce_top_level_array(self):
        self.assertEqual(
            self._detect("records.json", [{
                "attributes": {"type": "Account"},
                "Id": "001TEST",
            }]),
            "salesforce",
        )

    def test_slack_signature(self):
        self.assertEqual(
            self._detect("export.json", {
                "channels": [],
                "users": [],
                "messages": [],
            }),
            "slack",
        )

    def test_teams_signature(self):
        self.assertEqual(
            self._detect("export.json", {
                "chatId": "synthetic-chat",
                "messages": [],
            }),
            "teams",
        )

    def test_plain_json(self):
        self.assertEqual(
            self._detect("customers.json", [
                {"name": "Alice", "city": "Nashville"}
            ]),
            "plain",
        )

    def test_large_salesforce_wrapper(self):
        payload = {
            "totalSize": 20001,
            "done": True,
            "records": [
                {
                    "attributes": {"type": "Contact"},
                    "Id": f"003{i:012d}",
                }
                for i in range(20001)
            ],
        }
        self.assertEqual(
            self._detect("large.json", payload),
            "salesforce",
        )


    def test_plain_scalar_array(self):
        self.assertEqual(
            self._detect(
                "numbers.json",
                [101, 202, 303],
            ),
            "plain",
        )

    def test_plain_nested_array(self):
        self.assertEqual(
            self._detect(
                "nested.json",
                [[1, 2], [3, 4]],
            ),
            "plain",
        )

    def test_empty_array(self):
        self.assertEqual(
            self._detect("empty.json", []),
            "plain",
        )

    def test_salesforce_utf8_bom(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.json"
            payload = {
                "totalSize": 1,
                "done": True,
                "records": [{
                    "attributes": {
                        "type": "Contact"
                    },
                    "Id": "003BOM",
                }],
            }

            path.write_bytes(
                b"\xef\xbb\xbf"
                + json.dumps(payload).encode("utf-8")
            )

            self.assertEqual(
                detect_json_source_profile(path),
                "salesforce",
            )


    def test_salesforce_filename_alone_is_not_evidence(self):
        self.assertEqual(
            self._detect(
                "salesforce_notes.json",
                [{"name": "Ordinary data"}],
            ),
            "plain",
        )

    def test_teams_filename_alone_is_not_evidence(self):
        self.assertEqual(
            self._detect(
                "teams_export.json",
                {"name": "Ordinary data"},
            ),
            "plain",
        )


if __name__ == "__main__":
    unittest.main()
