"""Ensure all shared Review lookup paths support native JSON formats."""

import ast
from pathlib import Path


REVIEW = Path(__file__).resolve().parent / "review.py"


def test_all_shared_review_json_extension_lists():
    tree = ast.parse(REVIEW.read_text(encoding="utf-8-sig"))

    lists = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        names = {
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        }

        if names.intersection({
            "SUPPORTED_REVIEW_EXTENSIONS",
            "known_extensions",
        }):
            lists.append((names, ast.literal_eval(node.value)))

    assert len(lists) == 4

    for names, extensions in lists:
        assert len(extensions) == len(set(extensions))

        for ext in (".json", ".jsonl", ".ndjson"):
            assert ext in extensions

    supported = [
        extensions
        for names, extensions in lists
        if "SUPPORTED_REVIEW_EXTENSIONS" in names
    ]

    assert len(supported) == 1

    for ext in (
        ".pdf", ".docx", ".xlsx",
        ".csv", ".msg", ".eml",
    ):
        assert ext in supported[0]
