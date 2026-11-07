import ast

import pytest

from apc import detection_job_runner as runner


def test_capture_freezes_json_without_upload(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_processing_account",
        lambda: "synthetic-account",
    )
    monkeypatch.setattr(
        runner,
        "_processing_container",
        lambda: "synthetic-container",
    )

    original = {"documents": [{"doc_id": "DOC-A"}]}
    writes = []

    info = runner._record_publication_write(
        "synthetic/results/documents.json",
        original,
        overwrite=False,
        writes=writes,
    )

    original["documents"][0]["doc_id"] = "CHANGED"

    assert writes == [{
        "blob_path": "synthetic/results/documents.json",
        "payload": {
            "documents": [{"doc_id": "DOC-A"}],
        },
        "overwrite": False,
    }]

    assert info["storage_account"] == "synthetic-account"
    assert info["container"] == "synthetic-container"
    assert info["bytes"] > 0


def test_capture_rejects_invalid_overwrite_policy():
    with pytest.raises(TypeError):
        runner._record_publication_write(
            "synthetic/result.json",
            {"count": 1},
            overwrite="false",
            writes=[],
        )


def test_publication_callback_supports_recording():
    tree = ast.parse(
        open(
            runner.__file__,
            encoding="utf-8-sig",
        ).read()
    )

    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run_data_element_detection_job"
    )

    publisher = next(
        node for node in function.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_publish_final_results"
    )

    assert any(
        arg.arg == "plan_writes"
        for arg in publisher.args.kwonlyargs
    )

    writes = [
        node for node in ast.walk(publisher)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_write_processing_json"
    ]

    assert len(writes) == 5