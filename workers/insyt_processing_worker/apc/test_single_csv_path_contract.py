import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_source(relative_path):
    path = ROOT / relative_path
    source = path.read_text(encoding="utf-8-sig")
    return source, ast.parse(source)


def function_calls(node, name):
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == name
    ]


class SingleCsvPathContractTests(unittest.TestCase):

    def test_azure_runner_has_one_uploader(self):
        source, tree = load_source(
            "apc/azure_job_runner.py"
        )

        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "run_azure_processing_job"
        ]

        self.assertEqual(len(functions), 1)
        fn = functions[0]

        self.assertEqual(
            len(function_calls(
                fn, "azure_upload_xl_files_outputs"
            )),
            1,
        )
        self.assertEqual(
            len(function_calls(
                fn, "azure_upload_json_structured_outputs"
            )),
            0,
        )

        self.assertIn(
            "Common CSV Azure staging incomplete",
            source,
        )

    def test_main_worker_has_one_uploader(self):
        source, tree = load_source(
            "app/workers/processing_worker.py"
        )

        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "structured_fast_lane"
        ]

        self.assertEqual(len(functions), 1)
        fn = functions[0]

        self.assertEqual(
            len(function_calls(
                fn, "azure_upload_xl_files_outputs"
            )),
            1,
        )
        self.assertEqual(
            len(function_calls(
                fn, "azure_upload_json_structured_outputs"
            )),
            0,
        )

        function_source = ast.get_source_segment(
            source, fn
        )

        self.assertIn(
            'row.get("is_csv_child") is True',
            function_source,
        )
        self.assertIn(
            'row.get("detection_ready") is True',
            function_source,
        )

    def test_manual_detection_gate_precedes_legacy(self):
        _, tree = load_source(
            "app/workers/processing_worker.py"
        )

        fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "structured_fast_lane"
        )

        legacy = [
            index
            for index, statement in enumerate(fn.body)
            if isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "detection_job_id"
                for target in statement.targets
            )
        ]

        self.assertEqual(len(legacy), 1)

        preceding = fn.body[:legacy[0]]

        self.assertTrue(
            any(
                isinstance(statement, ast.Return)
                for statement in preceding
            ),
            "Manual detection gate must return "
            "before legacy automatic detection.",
        )

    def test_common_staging_and_upload_flags(self):
        layout, _ = load_source(
            "apc/azure_layout.py"
        )
        uploader, _ = load_source(
            "apc/azure_blob_adapter.py"
        )

        self.assertIn(
            '"is_csv_child": is_csv_child',
            layout,
        )

        tree = ast.parse(uploader)
        fn = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "azure_upload_xl_files_outputs"
        )

        text = ast.get_source_segment(uploader, fn)

        self.assertIn('"is_csv_child"', text)
        self.assertNotIn('"is_workbook_child"', text)


if __name__ == "__main__":
    unittest.main()
