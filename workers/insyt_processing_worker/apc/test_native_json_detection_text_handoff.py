import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parent / "azure_blob_adapter.py"
tree = ast.parse(
    SOURCE.read_text(encoding="utf-8-sig"),
    filename=str(SOURCE),
)

functions = [
    n for n in tree.body
    if isinstance(n, ast.FunctionDef)
    and n.name == "_stage_native_json_detection_text"
]

if len(functions) != 1:
    raise RuntimeError("JSON staging helper missing or duplicated")

module = ast.Module(body=functions, type_ignores=[])
ast.fix_missing_locations(module)

namespace = {"Path": Path}
exec(compile(module, str(SOURCE), "exec"), namespace)
handoff = namespace["_stage_native_json_detection_text"]


class FakeBlob:
    def __init__(self, initial=None):
        self.data = initial
        self.writes = 0

    def exists(self):
        return self.data is not None

    def upload_blob(self, stream, *, overwrite, content_settings):
        if overwrite or self.data is not None:
            raise AssertionError("Existing blob overwrite attempted")
        self.data = stream.read()
        self.writes += 1

    def download_blob(self):
        return SimpleNamespace(chunks=lambda: iter([self.data]))


class FakeContainer:
    def __init__(self, initial=None):
        self.blob = FakeBlob(initial)
        self.paths = []

    def get_blob_client(self, path):
        self.paths.append(path)
        return self.blob


class NativeJsonDetectionHandoffTests(unittest.TestCase):
    DOC_ID = "INSYT000000020"
    JOB_ID = "JOB-2A4D8B80DC8649FD"
    PREFIX = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"
    CONTENT = b'{"name":"Synthetic Example"}'

    def run_case(self, extension, existing=None, review_status="uploaded"):
        blob_path = (
            f"{self.PREFIX}/processing_center/staged/"
            f"{self.JOB_ID}/text/{self.DOC_ID}.txt"
        )

        container = FakeContainer(existing)
        adapter = SimpleNamespace(
            routing=SimpleNamespace(prefix=self.PREFIX),
            processing_container=container,
            _content_settings_cls=lambda **kwargs: kwargs,
        )

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "source" / "text"
            folder.mkdir(parents=True)
            (folder / f"{self.DOC_ID}.txt").write_bytes(self.CONTENT)

            handoff(
                adapter=adapter,
                promotion_plan=[{
                    "doc_id": self.DOC_ID,
                    "extension": extension,
                }],
                uploads=[{
                    "doc_id": self.DOC_ID,
                    "kind": "text",
                    "status": review_status,
                    "blob_path": blob_path,
                }],
                local_review_root=temp,
                job_id=self.JOB_ID,
            )

        return container, blob_path

    def check_json(self, extension):
        container, path = self.run_case(extension)
        self.assertEqual(container.blob.data, self.CONTENT)
        self.assertEqual(container.blob.writes, 1)
        self.assertEqual(container.paths, [path])

    def test_json(self):
        self.check_json("json")

    def test_jsonl(self):
        self.check_json("jsonl")

    def test_ndjson(self):
        self.check_json("ndjson")

    def test_identical_existing_blob(self):
        container, _ = self.run_case(
            "json", existing=self.CONTENT
        )
        self.assertEqual(container.blob.writes, 0)

    def test_conflicting_blob_rejected(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.run_case("json", existing=b"wrong content")

    def test_missing_review_upload_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Review text staging"):
            self.run_case("json", review_status="missing_local_file")

    def check_non_json(self, extension):
        container, _ = self.run_case(extension)
        self.assertEqual(container.blob.writes, 0)
        self.assertIsNone(container.blob.data)
        self.assertEqual(container.paths, [])

    def test_pdf_unchanged(self):
        self.check_non_json("pdf")

    def test_csv_unchanged(self):
        self.check_non_json("csv")

    def test_xlsx_unchanged(self):
        self.check_non_json("xlsx")

    def test_docx_unchanged(self):
        self.check_non_json("docx")


if __name__ == "__main__":
    unittest.main()
