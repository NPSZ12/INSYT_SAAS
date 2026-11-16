import ast
from pathlib import Path

SOURCE = Path(__file__).with_name("processing_center_azure.py")


def routing_conditions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "get_processing_center_promotion_population"
    )

    destination = []
    native = []

    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue

        if any(
            isinstance(child, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "destination"
                for target in child.targets
            )
            and isinstance(child.value, ast.Constant)
            and child.value.value == "cyber2"
            for child in node.body
        ):
            destination.append(node.test)

        if any(
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Call)
            and isinstance(child.value.func, ast.Attribute)
            and child.value.func.attr == "append"
            and isinstance(child.value.func.value, ast.Name)
            and child.value.func.value.id == "native_json_hits"
            for child in node.body
        ):
            native.append(node.test)

    assert len(destination) == 1
    assert len(native) == 1
    return destination[0], native[0]


def evaluate(node, **values):
    return eval(
        compile(ast.Expression(body=node), "<routing>", "eval"),
        {"__builtins__": {}, "str": str},
        values,
    )


def test_native_json_hit_routes_to_cyber2():
    destination, native = routing_conditions()
    for ext in ("json", "jsonl", "ndjson"):
        assert evaluate(
            destination,
            classification="HIT",
            is_spreadsheet_data=False,
            extension=ext,
        )
        assert evaluate(
            native,
            destination="cyber2",
            extension=ext,
            is_workbook_sheet=False,
            row={"doc_id": "INSYT000000018"},
        )


def test_other_documents_and_nonhits_not_misrouted():
    destination, native = routing_conditions()

    for ext in ("txt", "pdf", "docx", "msg"):
        assert not evaluate(
            destination,
            classification="HIT",
            is_spreadsheet_data=False,
            extension=ext,
        )

    assert not evaluate(
        destination,
        classification="NO_HIT",
        is_spreadsheet_data=False,
        extension="json",
    )

    assert not evaluate(
        native,
        destination="review",
        extension="json",
        is_workbook_sheet=False,
        row={"doc_id": "INSYT000000018"},
    )

    assert not evaluate(
        native,
        destination="cyber2",
        extension="json",
        is_workbook_sheet=True,
        row={"doc_id": "INSYT000000018"},
    )

    assert not evaluate(
        native,
        destination="cyber2",
        extension="json",
        is_workbook_sheet=False,
        row={"doc_id": "INSYT000000018.1"},
    )


def test_spreadsheet_routing_preserved():
    destination, _ = routing_conditions()
    assert evaluate(
        destination,
        classification="HIT",
        is_spreadsheet_data=True,
        extension="csv",
    )
