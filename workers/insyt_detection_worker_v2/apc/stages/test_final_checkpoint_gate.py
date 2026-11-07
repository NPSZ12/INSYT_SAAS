import ast
import inspect

from apc.stages import pii_phi_detection as stage


def test_final_checkpoint_gate_precedes_run_completion():
    tree = ast.parse(
        inspect.getsource(stage.run_pii_phi_detection)
    )

    function = tree.body[0]

    final_gate = [
        n for n in function.body
        if isinstance(n, ast.If)
        and any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "_verify_selected_worksheet_progress"
            for c in ast.walk(n)
        )
    ]

    assert len(final_gate) == 1

    gate = final_gate[0]

    updates = [
        n for n in function.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == "execute"
        and any(
            isinstance(a, ast.Constant)
            and isinstance(a.value, str)
            and "UPDATE processing_detection_run" in a.value
            for a in ast.walk(n)
        )
    ]

    assert len(updates) == 1
    assert gate.lineno < updates[0].lineno

    errors = [
        n for n in ast.walk(gate)
        if isinstance(n, ast.Raise)
    ]

    assert errors


def test_final_gate_is_bounded_only():
    source = inspect.getsource(
        stage.run_pii_phi_detection
    )

    tree = ast.parse(source)

    guards = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "remaining_chunks"
        and any(
            isinstance(op, ast.IsNot)
            for op in n.test.ops
        )
        and any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "_verify_selected_worksheet_progress"
            for c in ast.walk(n)
        )
    ]

    assert len(guards) == 1