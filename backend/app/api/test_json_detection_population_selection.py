"""Exercise the actual Detection selection statements without Azure."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).with_name("processing_center_azure.py")
TREE = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

routes = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "start_data_element_detection"
]
assert len(routes) == 1, "Detection endpoint changed"


def statement_lists(node):
    for _, value in ast.iter_fields(node):
        if isinstance(value, list):
            if value and all(isinstance(x, ast.stmt) for x in value):
                yield value
            for child in value:
                if isinstance(child, ast.AST):
                    yield from statement_lists(child)
        elif isinstance(value, ast.AST):
            yield from statement_lists(value)


def assigned(statement, name):
    return (
        isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        )
    )


selection = None
for statements in statement_lists(routes[0]):
    starts = [
        i for i, statement in enumerate(statements)
        if assigned(statement, "ready_docs")
    ]
    ends = [
        i for i, statement in enumerate(statements)
        if assigned(statement, "detection_job_id")
    ]
    if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]:
        selection = statements[starts[0]:ends[0]]
        break

assert selection is not None, "Detection selection block changed"

module = ast.Module(body=selection, type_ignores=[])
ast.fix_missing_locations(module)
CODE = compile(module, str(SOURCE), "exec")


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def doc(number, extension, *, text=True, **options):
    value = {
        "doc_id": f"INSYT{number:09d}",
        "extension": extension,
        "text_staged_blob_path": (
            f"synthetic/text/INSYT{number:09d}.txt" if text else None
        ),
    }
    value.update(options)
    return value


def execute(documents, *, all_ready, requested=(), invalid=()):
    blocked = []
    invalid = set(invalid)

    def verify(row):
        extension = str(row.get("extension") or "").lstrip(".").lower()
        if extension not in {"json", "jsonl", "ndjson"}:
            return True
        if (
            not row.get("text_staged_blob_path")
            or row["doc_id"] in invalid
        ):
            blocked.append(row["doc_id"])
            return False
        return True

    scope = {
        "staged": {"docs": documents},
        "request": SimpleNamespace(
            detect_all_ready=all_ready,
            doc_ids=list(requested),
        ),
        "blocked_native_json": blocked,
        "native_json_detection_text_ready": verify,
        "HTTPException": FakeHTTPException,
    }

    exec(CODE, scope)
    return scope["selected_docs"]


class DetectionPopulationSelectionTests(unittest.TestCase):

    def test_detect_all_blocks_missing_ndjson_text(self):
        good = doc(901, "json")
        missing = doc(902, "ndjson", text=False)
        with self.assertRaises(FakeHTTPException) as caught:
            execute([good, missing], all_ready=True)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn(missing["doc_id"], caught.exception.detail)

    def test_detect_selected_blocks_missing_jsonl_text(self):
        missing = doc(903, "jsonl", text=False)
        with self.assertRaises(FakeHTTPException) as caught:
            execute(
                [missing],
                all_ready=False,
                requested=[missing["doc_id"]],
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn(missing["doc_id"], caught.exception.detail)

    def test_all_three_json_extensions_are_eligible(self):
        documents = [
            doc(904, "json"),
            doc(905, "jsonl"),
            doc(906, "ndjson"),
        ]
        selected = execute(documents, all_ready=True)
        self.assertEqual(
            [row["doc_id"] for row in selected],
            [row["doc_id"] for row in documents],
        )

    def test_verified_json_does_not_block_other_documents(self):
        documents = [
            doc(907, "json"),
            doc(908, "pdf"),
        ]
        selected = execute(documents, all_ready=True)
        self.assertEqual(len(selected), 2)

    def test_existing_exclusions_are_preserved(self):
        good = doc(909, "json")
        documents = [
            good,
            doc(910, "json", is_duplicate=True),
            doc(911, "json", is_denisted=True),
            doc(912, "json", promotion_status="Promoted"),
            doc(913, "pdf", text=False),
        ]
        selected = execute(documents, all_ready=True)
        self.assertEqual(
            [row["doc_id"] for row in selected],
            [good["doc_id"]],
        )

    def test_unverified_json_with_path_is_blocked(self):
        bad = doc(914, "jsonl")
        with self.assertRaises(FakeHTTPException) as caught:
            execute(
                [bad],
                all_ready=True,
                invalid=[bad["doc_id"]],
            )
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
