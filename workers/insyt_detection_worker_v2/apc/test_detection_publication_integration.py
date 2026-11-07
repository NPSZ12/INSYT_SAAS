import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apc" / "detection_job_runner.py"
WORKER = ROOT / "app" / "workers" / "detection_worker.py"


def get_function(path, name):
    tree = ast.parse(
        path.read_text(encoding="utf-8-sig")
    )

    return next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )


def test_final_publication_inside_guard_callback():
    runner = get_function(
        RUNNER,
        "run_data_element_detection_job",
    )

    publishers = [
        node for node in runner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_publish_final_results"
    ]

    assert len(publishers) == 1

    writes = [
        node for node in ast.walk(publishers[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_write_processing_json"
    ]

    assert len(writes) >= 4

    guards = [
        node for node in ast.walk(runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "publish_detection_once"
    ]

    assert len(guards) == 1

    callback = {
        kw.arg: kw.value
        for kw in guards[0].keywords
    }["publish_results"]

    assert isinstance(callback, ast.Name)
    assert callback.id == "_publish_final_results"


def test_worker_claim_only_for_bounded_jobs():
    worker = get_function(
        WORKER,
        "process_detection_message",
    )

    calls = [
        node for node in ast.walk(worker)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_data_element_detection_job"
    ]

    assert len(calls) == 1

    keywords = {
        kw.arg: kw.value
        for kw in calls[0].keywords
    }

    claim = keywords["publication_claim_store"]

    assert isinstance(claim, ast.IfExp)
    assert isinstance(claim.test, ast.Name)
    assert claim.test.id == "bounded_enabled"

    assert isinstance(claim.body, ast.Name)
    assert claim.body.id == "claim_store"

    assert isinstance(claim.orelse, ast.Constant)
    assert claim.orelse.value is None