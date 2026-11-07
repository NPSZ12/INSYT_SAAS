import ast
from pathlib import Path

import pytest
from azure.core.exceptions import ResourceExistsError

from apc import detection_job_runner as runner


class FakeBlob:
    def __init__(self):
        self.data = None

    def upload_blob(self, data, *, overwrite, content_settings):
        if self.data is not None and not overwrite:
            raise ResourceExistsError("Blob exists")
        self.data = bytes(data)

    def download_blob(self):
        return self

    def readall(self):
        return self.data


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def get_blob_client(self, path):
        return self.blobs.setdefault(path, FakeBlob())


class FakeService:
    def __init__(self, container):
        self.container = container

    def get_container_client(self, name):
        return self.container


def test_create_only_reuse_and_conflict(monkeypatch):
    container = FakeContainer()

    monkeypatch.setattr(
        runner,
        "_processing_blob_service",
        lambda: FakeService(container),
    )
    monkeypatch.setattr(
        runner, "_processing_container",
        lambda: "synthetic",
    )
    monkeypatch.setattr(
        runner, "_processing_account",
        lambda: "synthetic",
    )

    path = "synthetic/results/summary.json"

    first = runner._write_processing_json(
        path, {"count": 5}, overwrite=False
    )

    assert first["blob_path"] == path
    original = container.blobs[path].data

    # Identical retry is accepted without overwrite.
    runner._write_processing_json(
        path, {"count": 5}, overwrite=False
    )
    assert container.blobs[path].data == original

    # Different content must never replace prior output.
    with pytest.raises(
        RuntimeError, match="Immutable detection result conflict"
    ):
        runner._write_processing_json(
            path, {"count": 6}, overwrite=False
        )

    assert container.blobs[path].data == original


def test_job_results_are_immutable_but_indexes_shared():
    path = Path(runner.__file__)
    tree = ast.parse(
        path.read_text(encoding="utf-8-sig")
    )

    function = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "run_data_element_detection_job"
    )

    publisher = next(
        n for n in function.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "_publish_final_results"
    )

    scoped = 0
    shared = 0

    for call in ast.walk(publisher):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_write_processing_json"
        ):
            continue

        names = {
            n.id for n in ast.walk(call.args[0])
            if isinstance(n, ast.Name)
        }
        kwargs = {k.arg: k.value for k in call.keywords}

        if "result_prefix" in names:
            assert "overwrite" in kwargs
            scoped += 1
        elif "document_index_prefix" in names:
            assert "overwrite" not in kwargs
            shared += 1

    assert scoped == 4
    assert shared == 1