import ast
from pathlib import Path

REVIEW = Path(
    "backend/app/api/review.py"
).read_text(encoding="utf-8-sig")

TREE = ast.parse(REVIEW)


def _function(name):
    return next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )


def test_native_json_review_allowlist():
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "SUPPORTED_REVIEW_EXTENSIONS"
            for target in node.targets
        )
    )

    extensions = set(ast.literal_eval(assignment.value))

    for extension in (".json", ".jsonl", ".ndjson"):
        assert extension in extensions

    for extension in (
        ".pdf", ".csv", ".xlsx", ".docx", ".msg", ".eml"
    ):
        assert extension in extensions


def test_native_json_doc_id_lookup():
    fn = _function("load_review_document_by_doc_id")
    section = ast.get_source_segment(REVIEW, fn)

    for extension in (".json", ".jsonl", ".ndjson"):
        assert repr(extension).replace("'", '"') in section


def test_native_json_text_preview():
    fn = _function("get_workspace_review_preview")
    section = ast.get_source_segment(REVIEW, fn)

    for extension in (".json", ".jsonl", ".ndjson"):
        assert repr(extension).replace("'", '"') in section
