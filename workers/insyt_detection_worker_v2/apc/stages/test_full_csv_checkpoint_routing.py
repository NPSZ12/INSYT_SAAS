"""Regression coverage for bounded worksheet selection.

Ordinary CSVs use full detection. Only worksheet-triage
documents participate in bounded checkpoint verification.
"""

import ast
import inspect
import textwrap

from apc.stages import pii_phi_detection as stage


def _function_tree():
    return ast.parse(
        textwrap.dedent(
            inspect.getsource(stage.run_pii_phi_detection)
        )
    ).body[0]


def _selected_worksheets(rows, options):
    """Evaluate the actual worksheet selection expression."""
    function = _function_tree()

    assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "worksheet_rows"
            for target in node.targets
        )
    ]

    assert len(assignments) == 1

    expression = ast.Expression(
        body=assignments[0].value
    )

    ast.fix_missing_locations(expression)

    namespace = {
        "rows": rows,
        "document_options": options,
        "_normalized_detection_mode":
            stage._normalized_detection_mode,
        "_row_get": stage._row_get,
        "WORKSHEET_TRIAGE_MODE":
            stage.WORKSHEET_TRIAGE_MODE,
    }

    return eval(
        compile(expression, "<worksheet-selection>", "eval"),
        namespace,
    )


def test_salesforce_full_csv_excluded():
    rows = [{"doc_id": "INSYT000000008.1"}]
    options = {
        "INSYT000000008.1": {
            "detection_mode": "full",
            "is_workbook_sheet": False,
        }
    }

    assert _selected_worksheets(rows, options) == []


def test_existing_excel_worksheet_retained():
    rows = [{"doc_id": "INSYT000000001.1"}]
    options = {
        "INSYT000000001.1": {
            "detection_mode": "worksheet_triage",
            "is_workbook_sheet": True,
        }
    }

    assert _selected_worksheets(rows, options) == rows


def test_mixed_population_selects_only_worksheets():
    rows = [
        {"doc_id": "EXCEL-1"},
        {"doc_id": "SALESFORCE-1"},
        {"doc_id": "EXCEL-2"},
        {"doc_id": "SLACK-1"},
    ]
    options = {
        "EXCEL-1": {"detection_mode": "worksheet_triage"},
        "SALESFORCE-1": {"detection_mode": "full"},
        "EXCEL-2": {"detection_mode": "worksheet_triage"},
        "SLACK-1": {"detection_mode": "full"},
    }

    assert [
        row["doc_id"]
        for row in _selected_worksheets(rows, options)
    ] == ["EXCEL-1", "EXCEL-2"]


def test_missing_mode_does_not_become_worksheet():
    rows = [{"doc_id": "PLAIN-CSV"}]

    assert _selected_worksheets(
        rows,
        {"PLAIN-CSV": {}},
    ) == []


def test_final_gate_preserves_checkpoint_verification():
    function = _function_tree()

    gates = [
        node
        for node in function.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "remaining_chunks"
        and any(
            isinstance(op, ast.IsNot)
            for op in node.test.ops
        )
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_verify_selected_worksheet_progress"
            for call in ast.walk(node)
        )
    ]

    assert len(gates) == 1

    gate = gates[0]

    worksheet_guards = [
        node
        for node in gate.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "worksheet_rows"
    ]

    assert len(worksheet_guards) == 1

    calls = [
        node
        for node in ast.walk(worksheet_guards[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_verify_selected_worksheet_progress"
    ]

    assert len(calls) == 1

    kwargs = {
        keyword.arg: keyword.value
        for keyword in calls[0].keywords
    }

    assert isinstance(kwargs["rows"], ast.Name)
    assert kwargs["rows"].id == "worksheet_rows"

    assert isinstance(kwargs["selected_doc_ids"], ast.Name)
    assert kwargs["selected_doc_ids"].id == "worksheet_doc_ids"

    assert any(
        isinstance(node, ast.Raise)
        for node in ast.walk(worksheet_guards[0])
    )