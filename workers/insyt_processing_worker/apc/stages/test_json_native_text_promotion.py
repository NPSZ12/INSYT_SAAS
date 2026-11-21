import hashlib
import tempfile
import unittest
from pathlib import Path

from apc.stages.review_promotion import (
    TEXT_EXTENSIONS,
    _build_text_output,
)


class JsonNativeTextPromotionTests(unittest.TestCase):

    def test_json_jsonl_ndjson_preserve_native_and_generate_text(self):
        for extension in ("json", "jsonl", "ndjson"):
            with self.subTest(extension=extension):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    native = root / f"synthetic.{extension}"

                    if extension == "json":
                        original = (
                            b'{"person":"Synthetic Test",'
                            b'"email":"test@example.org"}'
                        )
                    else:
                        original = (
                            b'{"person":"Synthetic One",'
                            b'"email":"one@example.org"}\n'
                            b'{"person":"Synthetic Two",'
                            b'"email":"two@example.org"}\n'
                        )

                    native.write_bytes(original)
                    source_hash = hashlib.sha256(original).hexdigest()

                    self.assertIn(extension, TEXT_EXTENSIONS)

                    text, method = _build_text_output(
                        {
                            "original_path": str(native),
                            "extension": extension,
                        },
                        workspace="capture",
                    )

                    self.assertTrue(text.strip())
                    self.assertIn("example.org", text)
                    self.assertEqual(method, "native_text_file")
                    self.assertEqual(native.read_bytes(), original)
                    self.assertEqual(
                        hashlib.sha256(native.read_bytes()).hexdigest(),
                        source_hash,
                    )
                    self.assertEqual(list(root.glob("*.csv")), [])


if __name__ == "__main__":
    unittest.main()
