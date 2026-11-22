"""Regression tests for native JSON Detection V2 storage publication.

Uses the production uploader method with fake Blob clients.
No Azure connection, source-file mutation, or application credentials.
"""

import ast
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parent / "azure_blob_adapter.py"


def load_uploader():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "upload_review_promotion_outputs"
    ]
    assert len(methods) == 1

    module = ast.Module(body=[methods[0]], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"Path": Path}
    exec(compile(module, str(SOURCE), "exec"), namespace)

    class Adapter:
        pass

    Adapter.upload_review_promotion_outputs = namespace[
        "upload_review_promotion_outputs"
    ]
    return Adapter


class FakeDownload:
    def __init__(self, data):
        self.data = data

    def chunks(self):
        for offset in range(0, len(self.data), 7):
            yield self.data[offset:offset + 7]


class FakeBlob:
    def __init__(self, container, path):
        self.container = container
        self.path = path

    def exists(self):
        return self.path in self.container.data

    def upload_blob(self, data, overwrite=False, **kwargs):
        if self.container.fail_next_upload:
            self.container.fail_next_upload = False
            raise RuntimeError("Simulated storage interruption")
        if self.exists() and not overwrite:
            raise ValueError("Blob already exists")
        if hasattr(data, "read"):
            data = data.read()
        self.container.data[self.path] = bytes(data)

    def download_blob(self):
        return FakeDownload(self.container.data[self.path])


class FakeContainer:
    def __init__(self):
        self.data = {}
        self.fail_next_upload = False

    def get_blob_client(self, path):
        return FakeBlob(self, path)


def make_case(tmp_path, extension="json"):
    adapter = load_uploader()()
    adapter.routing = type(
        "Routing", (), {"prefix": "test/capture/project"}
    )()
    adapter.review_container = FakeContainer()
    adapter.processing_container = FakeContainer()
    adapter._content_settings_cls = lambda **kwargs: kwargs

    doc_id = "TEST001"
    native = b'{"synthetic":true}'
    text = b'{"email":"test@example.org"}'

    native_dir = tmp_path / "source" / "native"
    text_dir = tmp_path / "source" / "text"
    native_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    (native_dir / f"{doc_id}.{extension}").write_bytes(native)
    (text_dir / f"{doc_id}.txt").write_bytes(text)

    plan = [{
        "doc_id": doc_id,
        "extension": extension,
        "native_blob_path": f"source/native/{doc_id}.{extension}",
        "text_blob_path": f"source/text/{doc_id}.txt",
    }]

    prefix = (
        "test/capture/project/"
        "processing_center/staged/JOB-TEST"
    )
    native_path = f"{prefix}/native/{doc_id}.{extension}"
    text_path = f"{prefix}/text/{doc_id}.txt"

    return adapter, plan, native_path, text_path, native, text


def publish(adapter, plan, root, promote=False):
    return adapter.upload_review_promotion_outputs(
        plan,
        str(root),
        "JOB-TEST",
        overwrite=False,
        promote_to_source=promote,
    )


@pytest.mark.parametrize("extension", ["json", "jsonl", "ndjson"])
def test_native_json_publishes_detection_text(tmp_path, extension):
    a, plan, native_path, text_path, native, text = make_case(
        tmp_path, extension
    )
    results = publish(a, plan, tmp_path)
    assert a.review_container.data[native_path] == native
    assert a.review_container.data[text_path] == text
    assert a.processing_container.data[text_path] == text
    assert native_path not in a.processing_container.data
    assert len(results) == 2


def test_identical_retry_is_idempotent(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    publish(a, plan, tmp_path)
    before_review = dict(a.review_container.data)
    before_processing = dict(a.processing_container.data)

    publish(a, plan, tmp_path)

    assert a.review_container.data == before_review
    assert a.processing_container.data == before_processing


def test_retry_after_interrupted_processing_upload(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    a.processing_container.fail_next_upload = True

    with pytest.raises(RuntimeError, match="Simulated storage interruption"):
        publish(a, plan, tmp_path)

    assert a.review_container.data[native_path] == native
    assert a.review_container.data[text_path] == text
    assert text_path not in a.processing_container.data

    publish(a, plan, tmp_path)

    assert a.processing_container.data[text_path] == text


def test_conflicting_review_text_rejected(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    a.review_container.data[text_path] = b"CONFLICT"

    with pytest.raises(ValueError, match="Review staging integrity mismatch"):
        publish(a, plan, tmp_path)

    assert a.review_container.data[text_path] == b"CONFLICT"
    assert text_path not in a.processing_container.data


def test_conflicting_processing_text_rejected(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    a.processing_container.data[text_path] = b"CONFLICT"

    with pytest.raises(ValueError, match="Processing text integrity mismatch"):
        publish(a, plan, tmp_path)

    assert a.processing_container.data[text_path] == b"CONFLICT"


def test_empty_detection_text_rejected(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    (tmp_path / "source" / "text" / "TEST001.txt").write_bytes(b"")

    with pytest.raises(ValueError, match="Empty native JSON Detection text"):
        publish(a, plan, tmp_path)

    assert text_path not in a.processing_container.data


def test_non_json_processing_storage_unchanged(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(
        tmp_path, "pdf"
    )
    publish(a, plan, tmp_path)

    assert a.review_container.data[native_path] == native
    assert a.review_container.data[text_path] == text
    assert a.processing_container.data == {}


def test_final_promotion_does_not_publish_processing_text(tmp_path):
    a, plan, native_path, text_path, native, text = make_case(tmp_path)
    publish(a, plan, tmp_path, promote=True)

    assert a.processing_container.data == {}
    assert a.review_container.data["source/native/TEST001.json"] == native
    assert a.review_container.data["source/text/TEST001.txt"] == text
