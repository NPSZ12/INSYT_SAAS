"""Regression tests for manual native JSON source-profile classification."""
import sys
import unittest
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents
    if (p / "backend").is_dir() and (p / "frontend").is_dir()
)
sys.path.insert(0, str(ROOT / "backend"))

from app.services.structured_intake.promotion_profile import classify_promoted_json


class PromotionProfileTests(unittest.TestCase):
    def test_six_profiles(self):
        samples = [
            (b'{"people":[]}', "plain"),
            (b'{"type":"message","ts":"1.01","text":"test","user":"U1"}', "slack"),
            (b'{"records":[],"totalSize":0,"done":true}', "salesforce"),
            (b'{"teamId":"synthetic","channelId":"channel"}', "teams"),
            (b'{"messages":[{"name":"spaces/a/messages/b","createTime":"2026-11-21T00:00:00Z","sender":{"name":"users/a"}}]}', "google"),
            (b'{"custom_records":[]}', "custom_api"),
        ]
        for raw, expected in samples:
            with self.subTest(expected=expected):
                self.assertEqual(classify_promoted_json(raw, "sample.json", ".json"), expected)

    def test_jsonl_ndjson(self):
        raw = b'{"name":"One"}\n{"name":"Two"}\n'
        for ext in (".jsonl", ".ndjson"):
            with self.subTest(ext=ext):
                self.assertEqual(classify_promoted_json(raw, "sample" + ext, ext), "custom_api")

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

    def test_unrecognized_defaults_custom_api(self):
        self.assertEqual(classify_promoted_json(b'{"arbitrary":{"value":1}}', "sample.json", ".json"), "custom_api")

    def test_weak_vendor_lookalikes_are_not_proof(self):
        for raw in (b'{"channels":[],"users":[],"messages":[]}',
                    b'{"teamId":"synthetic"}',
                    b'{"spaces":[]}'):
            with self.subTest(raw=raw):
                self.assertEqual(classify_promoted_json(raw, "salesforce.json", ".json"), "custom_api")

if __name__ == "__main__":
    unittest.main()
