import sys
import unittest
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents
    if (p / "backend").is_dir() and (p / "frontend").is_dir()
)
sys.path.insert(0, str(ROOT / "backend"))

from app.services.structured_intake.promotion_profile import (
    classify_promoted_json,
)


class PromotionProfileTests(unittest.TestCase):
    def test_six_profiles(self):
        samples = [
            (b'{"people":[]}', "plain"),
            (b'{"channels":[],"users":[],"messages":[]}', "slack"),
            (b'{"records":[],"totalSize":0,"done":true}', "salesforce"),
            (b'{"teamId":"synthetic"}', "teams"),
            (b'{"spaces":[]}', "google"),
            (b'{"custom_records":[]}', "custom_api"),
        ]
        for raw, expected in samples:
            with self.subTest(expected=expected):
                self.assertEqual(
                    classify_promoted_json(raw, "sample.json", ".json"),
                    expected,
                )

    def test_jsonl_ndjson(self):
        raw = b'{"name":"One"}\n{"name":"Two"}\n'
        for ext in (".jsonl", ".ndjson"):
            with self.subTest(ext=ext):
                self.assertEqual(
                    classify_promoted_json(raw, "sample" + ext, ext),
                    "plain",
                )

    def test_csv_and_invalid_rejected(self):
        for raw, ext in [
            (b"", ".json"),
            (b"{invalid", ".json"),
            (b'{"value":1}', ".csv"),
        ]:
            with self.subTest(ext=ext, raw=raw):
                with self.assertRaises(ValueError):
                    classify_promoted_json(raw, "sample" + ext, ext)

    def test_source_unchanged(self):
        raw = b'{"records":[],"totalSize":0}'
        before = bytes(raw)
        classify_promoted_json(raw, "sample.json", ".json")
        self.assertEqual(raw, before)

    def test_unrecognized_defaults_plain(self):
        self.assertEqual(
            classify_promoted_json(
                b'{"arbitrary":{"value":1}}',
                "sample.json",
                ".json",
            ),
            "plain",
        )


if __name__ == "__main__":
    unittest.main()
