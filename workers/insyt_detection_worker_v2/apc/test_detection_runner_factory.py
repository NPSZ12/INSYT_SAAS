import ast
from pathlib import Path


RUNNER = (
    Path(__file__).resolve().parent
    / "detection_job_runner.py"
)


def test_runner_factory_is_optional_and_forwarded():
    tree = ast.parse(
        RUNNER.read_text(encoding="utf-8-sig")
    )

    runner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run_data_element_detection_job"
    )

    keyword_arguments = runner.args.kwonlyargs
    keyword_defaults = runner.args.kw_defaults

    defaults = {
        argument.arg: default
        for argument, default in zip(
            keyword_arguments,
            keyword_defaults,
        )
    }

    assert "worksheet_executor_factory" in defaults
    assert isinstance(
        defaults["worksheet_executor_factory"],
        ast.Constant,
    )
    assert (
        defaults["worksheet_executor_factory"].value
        is None
    )

    calls = [
        node
        for node in ast.walk(runner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_pii_phi_detection"
    ]

    assert len(calls) == 1

    forwarded = [
        keyword
        for keyword in calls[0].keywords
        if keyword.arg == "worksheet_executor_factory"
    ]

    assert len(forwarded) == 1
    assert isinstance(forwarded[0].value, ast.Name)
    assert (
        forwarded[0].value.id
        == "worksheet_executor_factory"
    )