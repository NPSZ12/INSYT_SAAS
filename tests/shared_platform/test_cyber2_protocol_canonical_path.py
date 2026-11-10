"""Prevent Cyber2 from resolving a different Project Protocol path."""

import ast
import json
import unittest
from pathlib import Path

from app.services.storage_paths import build_project_path


ROOT = Path(__file__).resolve().parents[2]


def isolated_protocol_functions():
    path = ROOT / "backend/app/api/cyber_utility.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names = {
        "get_protocol_folder_prefix",
        "get_project_protocol_blob_paths",
        "load_project_protocol_json",
    }

    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]

    assert {node.name for node in selected} == names

    def clean_folder(value):
        return str(value or "").strip().replace(" ", "_")

    namespace = {
        "build_project_path": build_project_path,
        "clean_folder": clean_folder,
        "json": json,
    }

    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)

    return namespace


class FakeContainer:
    def __init__(self, expected_path):
        self.expected_path = expected_path
        self.requested = []

    def download_blob(self, path):
        self.requested.append(path)

        if path != self.expected_path:
            raise FileNotFoundError(path)

        return self

    def readall(self):
        return json.dumps({
            "fields": [
                {"label": "First Name"},
                {"label": "Last Name"},
                {"label": "Employee ID Number"},
            ]
        }).encode("utf-8")


class ProtocolCanonicalPathTests(unittest.TestCase):

    def test_payroll_protocol_uses_client_workspace_project(self):
        functions = isolated_protocol_functions()

        expected = (
            "INSYT_Demo/capture/Project_Payroll_Dedupe_Test/"
            "source/protocol/"
            "Project_Payroll_Dedupe_Test_Protocol.json"
        )

        paths = functions["get_project_protocol_blob_paths"](
            workspace="capture",
            client="INSYT_Demo",
            project="Project_Payroll_Dedupe_Test",
        )

        self.assertEqual(paths[0], expected)
        self.assertEqual(
            paths[0],
            build_project_path(
                "capture",
                "INSYT_Demo",
                "Project_Payroll_Dedupe_Test",
                "source/protocol",
                "Project_Payroll_Dedupe_Test_Protocol.json",
            ),
        )

    def test_protocol_json_loaded_from_approved_location(self):
        functions = isolated_protocol_functions()

        expected = (
            "INSYT_Demo/capture/Project_Payroll_Dedupe_Test/"
            "source/protocol/"
            "Project_Payroll_Dedupe_Test_Protocol.json"
        )

        container = FakeContainer(expected)

        data, path = functions["load_project_protocol_json"](
            container=container,
            workspace="capture",
            client="INSYT_Demo",
            project="Project_Payroll_Dedupe_Test",
        )

        self.assertEqual(path, expected)
        self.assertEqual(container.requested, [expected])
        self.assertEqual(len(data["fields"]), 3)
        self.assertEqual(
            data["fields"][2]["label"],
            "Employee ID Number",
        )

    def test_workspace_isolation(self):
        functions = isolated_protocol_functions()

        paths = [
            functions["get_project_protocol_blob_paths"](
                workspace=workspace,
                client="INSYT_Demo",
                project="Project_Payroll_Dedupe_Test",
            )[0]
            for workspace in ("capture", "discovery")
        ]

        self.assertNotEqual(paths[0], paths[1])
        self.assertIn("/capture/", paths[0])
        self.assertIn("/discovery/", paths[1])

    def test_both_cyber2_consumers_use_shared_library(self):
        for filename in (
            "header_identification.py",
            "schema_mapping.py",
        ):
            path = (
                ROOT / "backend/app/api/cyber2" / filename
            )

            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            loader = next(
                node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "_load_protocol_library"
            )

            calls = [
                node for node in ast.walk(loader)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_protocol_header_library"
            ]

            self.assertEqual(len(calls), 1, filename)

        source = (
            ROOT / "backend/app/api/cyber2/header_identification.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "container = get_live_source_container_client(workspace)",
            source,
        )


if __name__ == "__main__":
    unittest.main()