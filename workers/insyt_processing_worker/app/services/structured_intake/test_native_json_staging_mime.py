import ast
from pathlib import Path


def test_native_json_staging_mime_routing():
    source = Path(
        "workers/insyt_processing_worker/apc/"
        "azure_blob_adapter.py"
    ).read_text(encoding="utf-8-sig")

    tree = ast.parse(source)

    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "azure_upload_json_structured_outputs"
    )

    mime_expressions = [
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.keyword)
        and node.arg == "content_type"
    ]

    assert len(mime_expressions) == 2

    expression = next(
        expr for expr in mime_expressions
        if isinstance(expr, ast.IfExp)
    )

    def evaluate(extension):
        return eval(
            compile(
                ast.Expression(expression),
                "<mime-expression>",
                "eval",
            ),
            {"row": {"extension": extension}},
        )

    assert evaluate("json") == "application/json"
    assert evaluate("JSON") == "application/json"
    assert evaluate("jsonl") == "application/x-ndjson"
    assert evaluate("ndjson") == "application/x-ndjson"
    assert evaluate("csv") == "text/csv"

    function_source = ast.get_source_segment(source, fn)

    assert "with local_path.open(" in function_source
    assert '"rb"' in function_source
    assert "native_blob_client.upload_blob(" in function_source
