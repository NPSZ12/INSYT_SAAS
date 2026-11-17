import ast
from pathlib import Path

SOURCE = Path(
    "backend/app/api/processing_center_azure.py"
).read_text(encoding="utf-8-sig")


def population_section():
    start = SOURCE.index(
        "def get_processing_center_promotion_population("
    )
    end = SOURCE.find("\n@router.", start + 1)
    return SOURCE[start:end if end >= 0 else None]


def test_native_json_routing():
    tree = ast.parse(SOURCE)

    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name ==
        "get_processing_center_promotion_population"
    )

    matches = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "append"
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "native_json_hits"
            for statement in node.body
            for child in ast.walk(statement)
        )
    ]

    assert len(matches) == 1

    expression = compile(
        ast.Expression(matches[0].test),
        "<native-json-routing>",
        "eval",
    )

    def routed(ext, structured, doc_id, workbook=False,
               destination="cyber2"):
        return eval(expression, {
            "destination": destination,
            "extension": ext,
            "is_json_structured_data": structured,
            "is_workbook_sheet": workbook,
            "row": {"doc_id": doc_id},
        })

    for ext in ("json", "jsonl", "ndjson"):
        assert routed(ext, True, "INSYT000000010")

    assert not routed("csv", True, "INSYT000000010.1")
    assert not routed("json", True, "INSYT000000010.1")
    assert routed("json", False, "INSYT000000010")
    assert not routed(
        "json", True, "INSYT000000010", workbook=True
    )
    assert not routed(
        "json", True, "INSYT000000010",
        destination="review"
    )


def test_native_endpoints():
    for name in (
        "promote_processing_center_json_native",
        "send_processing_center_json_native_to_cyber2",
    ):
        start = SOURCE.index(f"def {name}(")
        end = SOURCE.find("\n@router.", start + 1)
        section = SOURCE[start:end if end >= 0 else None]

        assert 'population.get("native_json_hits")' in section
        assert 'population.get("spreadsheet_hits")' not in section


def test_population_counts():
    section = population_section()

    assert '"native_json_hits": []' in section
    assert '"native_json_hits": 0' in section
    assert '"native_json_hits": (' in section
    assert '"native_json_hits": len(' in section
    assert "len(native_json_hits) + " in section
