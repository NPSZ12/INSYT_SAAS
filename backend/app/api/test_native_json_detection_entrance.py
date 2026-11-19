import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).with_name("processing_center_azure.py")
tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

routes = [
    n for n in tree.body
    if isinstance(n, ast.FunctionDef)
    and n.name == "start_data_element_detection"
]
if len(routes) != 1:
    raise RuntimeError("Detection route unavailable")

route = routes[0]
helpers = [
    n for n in ast.walk(route)
    if isinstance(n, ast.FunctionDef)
    and n.name == "native_json_detection_text_ready"
]
if len(helpers) != 1:
    raise RuntimeError("JSON entrance helper unavailable")

module = ast.Module(body=[helpers[0]], type_ignores=[])
ast.fix_missing_locations(module)

BASE = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"
JOB = "JOB-2A4D8B80DC8649FD"
DOC = "INSYT000000020"
TEXT = f"{BASE}/processing_center/staged/{JOB}/text/{DOC}.txt"
CONTENT = b'{"name":"Synthetic Example"}'


class FakeBlob:
    def __init__(self, data):
        self.data = data

    def download_blob(self):
        if self.data is None:
            raise FileNotFoundError("BlobNotFound")

        def chunks():
            yield self.data[:7]
            yield self.data[7:]

        return SimpleNamespace(chunks=chunks)


class NativeJsonDetectionEntranceTests(unittest.TestCase):
    def verify(
        self,
        extension,
        review,
        processing,
        path=TEXT,
    ):
        blocked = []
        calls = {"review": 0, "processing": 0}

        def review_client(*, container, blob):
            self.assertEqual(container, "insyt-capture")
            self.assertEqual(blob, TEXT)
            calls["review"] += 1
            return FakeBlob(review)

        def processing_client(blob_path):
            self.assertEqual(blob_path, TEXT)
            calls["processing"] += 1
            return FakeBlob(processing)

        scope = {
            "workspace": "capture",
            "request": SimpleNamespace(
                client="INSYT_Demo",
                project="Project_Payroll_Dedupe_Test",
                source_job_id=JOB,
            ),
            "blocked_native_json": blocked,
            "_project_base_path": lambda **kw: BASE,
            "_review_container": lambda ws: "insyt-capture",
            "_get_review_blob_service_client": lambda:
                SimpleNamespace(get_blob_client=review_client),
            "_processing_container_client": lambda:
                SimpleNamespace(get_blob_client=processing_client),
        }

        exec(compile(module, str(SOURCE), "exec"), scope)

        result = scope["native_json_detection_text_ready"]({
            "doc_id": DOC,
            "extension": extension,
            "text_staged_blob_path": path,
        })

        return result, blocked, calls

    def test_json(self):
        self.assertTrue(self.verify("json", CONTENT, CONTENT)[0])

    def test_jsonl(self):
        self.assertTrue(self.verify("jsonl", CONTENT, CONTENT)[0])

    def test_ndjson(self):
        self.assertTrue(self.verify("ndjson", CONTENT, CONTENT)[0])

    def test_missing_processing(self):
        ready, blocked, _ = self.verify("json", CONTENT, None)
        self.assertFalse(ready)
        self.assertEqual(blocked, [DOC])

    def test_missing_review(self):
        ready, blocked, _ = self.verify("json", None, CONTENT)
        self.assertFalse(ready)
        self.assertEqual(blocked, [DOC])

    def test_conflicting_text(self):
        ready, blocked, _ = self.verify("json", CONTENT, b"wrong")
        self.assertFalse(ready)
        self.assertEqual(blocked, [DOC])

    def test_empty_text(self):
        ready, blocked, _ = self.verify("json", b"", b"")
        self.assertFalse(ready)
        self.assertEqual(blocked, [DOC])

    def test_wrong_path(self):
        ready, blocked, calls = self.verify(
            "json", CONTENT, CONTENT, path="invalid/path.txt"
        )
        self.assertFalse(ready)
        self.assertEqual(blocked, [DOC])
        self.assertEqual(calls, {"review": 0, "processing": 0})

    def test_non_json_unchanged(self):
        for extension in ("pdf", "csv", "xlsx", "docx"):
            with self.subTest(extension=extension):
                ready, blocked, calls = self.verify(
                    extension, None, None
                )
                self.assertTrue(ready)
                self.assertFalse(blocked)
                self.assertEqual(
                    calls, {"review": 0, "processing": 0}
                )

    def test_gate_precedes_dispatch_selection(self):
        text = ast.get_source_segment(
            SOURCE.read_text(encoding="utf-8-sig"), route
        )
        self.assertLess(
            text.index("if not native_json_detection_text_ready(doc):"),
            text.index("ready_docs.append(doc)"),
        )
        self.assertIn("requested_blocked", text)
        self.assertIn("status_code=409", text)

    def test_no_unbounded_readall(self):
        self.assertFalse(any(
            isinstance(n, ast.Attribute) and n.attr == "readall"
            for n in ast.walk(helpers[0])
        ))


if __name__ == "__main__":
    unittest.main()
