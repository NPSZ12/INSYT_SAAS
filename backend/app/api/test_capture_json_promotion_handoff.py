"""Capture native JSON dual-destination Promotion regressions.

Executes the real Promotion handler AST with injected dependencies.
Does not import Azure clients, connect to storage, or promote files.
"""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


API = Path(__file__).with_name("processing_center_azure.py")
DOC = "INSYT000000019"
JOB = "JOB-ABF3927B981B47CA"


class MockHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def load_handler(namespace):
    tree = ast.parse(API.read_text(encoding="utf-8-sig"))
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "promote_processing_center_review_population"
    ]
    if len(matches) != 1:
        raise AssertionError("Review Promotion handler missing")

    node = matches[0]
    node.decorator_list = []
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            node,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(API), "exec"), namespace)
    return namespace[node.name]


class CaptureJsonPromotionTests(unittest.TestCase):
    def run_scenario(
        self,
        extension="json",
        promotion="promoted",
        failure=False,
        overwrite=False,
    ):
        events = []
        row = {
            "doc_id": DOC,
            "extension": extension,
            "source_job_id": JOB,
            "detection_job_id": "DET-96D7C8D3ABC942C9",
            "classification": "HIT",
        }

        def population(**kwargs):
            events.append("population")
            return {
                "review_hits": [row],
                "counts": {"review_hits": 1},
            }

        def promote(*, workspace, request):
            events.append("files")
            item = {"doc_id": DOC, "status": promotion}
            return {
                "promoted": [item] if promotion == "promoted" else [],
                "skipped": [item] if promotion != "promoted" else [],
                "promoted_count": int(promotion == "promoted"),
                "skipped_count": int(promotion != "promoted"),
                "promotion_status": "Promoted",
            }

        def register(**kwargs):
            events.append("cyber2")
            if failure:
                raise ValueError("Hash verification failed")
            return {
                "doc_id": DOC,
                "status": "registered_verified",
                "csv_generated": False,
            }

        def ai(**kwargs):
            events.append("ai")
            return {"status": "completed"}

        namespace = {
            "Depends": lambda value: None,
            "require_admin": lambda: None,
            "HTTPException": MockHTTPException,
            "get_processing_center_promotion_population": population,
            "promote_processing_center_staged_results": promote,
            "_register_existing_capture_json_for_cyber2": register,
            "_resolve_processing_sets_for_doc_ids": lambda **kw: ["SET-1"],
            "build_ai_extraction_set": ai,
            "PromoteStagedResultsRequest": lambda **kw: SimpleNamespace(**kw),
            "BuildAiExtractionSetRequest": lambda **kw: SimpleNamespace(**kw),
            "_utc_now": lambda: "2026-11-18T00:00:00+00:00",
        }

        handler = load_handler(namespace)
        request = SimpleNamespace(
            client="INSYT_Demo",
            project="Project_Payroll_Dedupe_Test",
            doc_ids=[DOC],
            overwrite=overwrite,
        )
        admin = SimpleNamespace(username="test-admin")

        return handler, request, admin, events

    def test_new_json_dual_destination_and_ai(self):
        handler, request, admin, events = self.run_scenario()
        result = handler("capture", request, admin)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(events.count("files"), 1)
        self.assertEqual(events.count("cyber2"), 1)
        self.assertEqual(events.count("ai"), 1)
        self.assertLess(events.index("files"), events.index("cyber2"))

    def test_already_promoted_json_registration_only(self):
        handler, request, admin, events = self.run_scenario(
            promotion="already_promoted"
        )
        result = handler("capture", request, admin)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(events.count("cyber2"), 1)
        self.assertEqual(events.count("ai"), 0)
        self.assertEqual(result["promoted_count"], 0)

    def test_pdf_unchanged(self):
        handler, request, admin, events = self.run_scenario(
            extension="pdf"
        )
        result = handler("capture", request, admin)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(events.count("files"), 1)
        self.assertEqual(events.count("cyber2"), 0)
        self.assertEqual(events.count("ai"), 1)

    def test_registration_failure_reported(self):
        handler, request, admin, events = self.run_scenario(
            failure=True
        )
        result = handler("capture", request, admin)
        self.assertEqual(result["status"], "completed_with_errors")
        self.assertEqual(result["json_cyber2_error_count"], 1)
        self.assertEqual(events.count("ai"), 1)

    def test_json_overwrite_refused_before_files_write(self):
        handler, request, admin, events = self.run_scenario(
            overwrite=True
        )
        with self.assertRaises(MockHTTPException) as caught:
            handler("capture", request, admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(events.count("files"), 0)
        self.assertEqual(events.count("cyber2"), 0)


if __name__ == "__main__":
    unittest.main()
