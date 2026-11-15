from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from apc.detection.engine import run_detection_engine
from apc.detection.json_native_text import (
    IncompleteJsonNativeScan,
    prepare_json_detection_text,
)


class JsonNativeDetectionRegression(unittest.TestCase):

    def test_native_preserved_and_protocol_values_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "source.json"

            native.write_text(
                json.dumps({
                    "records": [
                        {"part": "123"},
                        {"part": "45"},
                        {"part": "6789"},
                        {
                            "Email": "jane@example.com",
                            "Phone": "202-555-0142",
                        },
                        {
                            "Email": "alex@example.com",
                            "Phone": "202-555-0187",
                        },
                    ]
                }),
                encoding="utf-8",
            )

            before = hashlib.sha256(native.read_bytes()).digest()

            prepared = prepare_json_detection_text(
                native, root / "detection.txt"
            )

            content = Path(prepared["text_path"]).read_text(
                encoding="utf-8"
            )

            result = run_detection_engine(
                content,
                enable_azure=False,
                enable_structured_rules=True,
            )

            types = [
                str(getattr(item, "entity_type", ""))
                for item in result.get("candidates") or []
            ]

            self.assertEqual(types.count("Email"), 2)
            self.assertEqual(types.count("PhoneNumber"), 2)
            self.assertNotIn("USSocialSecurityNumber", types)

            self.assertEqual(
                hashlib.sha256(native.read_bytes()).digest(),
                before,
            )

            lineage = [
                json.loads(line)
                for line in Path(
                    prepared["lineage_path"]
                ).read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(
                len(lineage), prepared["values_scanned"]
            )
            self.assertTrue(
                all("json_path" in row for row in lineage)
            )
            self.assertEqual(list(root.rglob("*.csv")), [])

    def test_malformed_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.json"
            target = root / "detection.txt"
            source.write_text(
                '{"Email":"incomplete"',
                encoding="utf-8",
            )

            with self.assertRaises(IncompleteJsonNativeScan):
                prepare_json_detection_text(source, target)

            self.assertFalse(target.exists())

    def test_incomplete_scan_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "values.json"
            target = root / "detection.txt"
            source.write_text(
                '{"a":"first","b":"second"}',
                encoding="utf-8",
            )

            with self.assertRaises(IncompleteJsonNativeScan):
                prepare_json_detection_text(
                    source, target, max_values=1
                )

            self.assertFalse(target.exists())

    def test_jsonl_without_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "records.jsonl"
            source.write_text(
                '{"Email":"one@example.com"}\n'
                '{"Email":"two@example.com"}\n',
                encoding="utf-8",
            )

            result = prepare_json_detection_text(
                source, root / "detection.txt"
            )

            self.assertEqual(result["values_scanned"], 2)
            self.assertEqual(list(root.rglob("*.csv")), [])


if __name__ == "__main__":
    unittest.main()