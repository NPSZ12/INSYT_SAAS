"""Isolated native JSON Cyber2 endpoint regressions.

Runs the actual endpoint function body with mocked Azure storage.
No Azure connection, Detection V2 calls, or client documents.
"""

import ast
import hashlib
import os
import sys
import types
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


API = Path(__file__).with_name("processing_center_azure.py")
ROOT = API.resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

BASE = "SyntheticClient/capture/SyntheticProject"
DOC = "INSYT000009999"
JOB = "JOB-SYNTHETIC"
DETECTION = "DET-SYNTHETIC"
INDEX = f"{BASE}/cyber2/intake/documents/{DOC}.json"
NATIVE = f"{BASE}/source/native/{DOC}.json"


class MockHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class ResourceNotFoundError(Exception):
    pass


class ResourceExistsError(Exception):
    pass


def azure_module_mocks():
    azure = types.ModuleType("azure")
    azure.__path__ = []

    core = types.ModuleType("azure.core")
    core.__path__ = []

    exceptions = types.ModuleType("azure.core.exceptions")
    exceptions.ResourceNotFoundError = ResourceNotFoundError
    exceptions.ResourceExistsError = ResourceExistsError

    return {
        "azure": azure,
        "azure.core": core,
        "azure.core.exceptions": exceptions,
    }


def load_endpoint(namespace):
    tree = ast.parse(API.read_text(encoding="utf-8-sig"))

    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name ==
        "send_processing_center_json_native_to_cyber2"
    ]

    if len(matches) != 1:
        raise AssertionError("JSON endpoint missing or duplicated.")

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


class JsonCyber2EndpointTests(unittest.TestCase):

    def setUp(self):
        self.native = b'{"people":[{"name":"Synthetic"}]}'
        self.indexes = {}
        self.writes = 0
        self.promotions = 0
        self.fail_files = False
        self.fail_registration = False
        self.concurrent_registration = False
        self.corrupt_files = False
        self.events = []

        self.row = {
            "doc_id": DOC,
            "file_id": "FILE-SYNTHETIC",
            "classification": "HIT",
            "destination": "json_cyber2",
            "source_type": "json_structured",
            "source_format": "json",
            "extension": "json",
            "source_job_id": JOB,
            "detection_job_id": DETECTION,
            "original_filename": "synthetic.json",
            "original_json_filename": "synthetic.json",
        }

        self.request = SimpleNamespace(
            client="SyntheticClient",
            project="SyntheticProject",
            doc_ids=[DOC],
        )

        self.admin = SimpleNamespace(username="test-admin")

    def read_index(self, path):
        if path not in self.indexes:
            raise ResourceNotFoundError(path)
        return dict(self.indexes[path])

    def write_index(self, *, blob_path, payload, overwrite):
        self.assertFalse(overwrite)

        if self.fail_registration:
            raise RuntimeError("Simulated Cyber2 storage failure")

        if blob_path in self.indexes:
            raise ResourceExistsError(blob_path)

        self.indexes[blob_path] = dict(payload)
        self.writes += 1

        if self.concurrent_registration:
            raise ResourceExistsError(blob_path)

    def promote(self, *, workspace, request, admin):
        self.events.append("files")
        self.promotions += 1

        if self.fail_files:
            raise MockHTTPException(
                409, "Simulated Files promotion failure"
            )

        return {
            "promoted": [{
                "doc_id": DOC,
                "verified": True,
                "status": "already_promoted_verified"
                if self.promotions > 1 else "promoted",
                "source_native_path": NATIVE,
                "sha256": hashlib.sha256(self.native).hexdigest(),
                "bytes": len(self.native),
            }]
        }

    def live_service(self):
        data = (
            b'{"corrupted":true}'
            if self.corrupt_files
            else self.native
        )

        return SimpleNamespace(
            get_blob_client=lambda **kwargs: SimpleNamespace(
                download_blob=lambda: SimpleNamespace(
                    readall=lambda: data
                )
            )
        )

    def execute(self, enabled=True):
        namespace = {
            "os": os,
            "Depends": lambda dependency: None,
            "require_admin": lambda: None,
            "HTTPException": MockHTTPException,
            "require_scoped_project_access":
                lambda *args: None,
            "_project_base_path": lambda **kwargs: BASE,
            "_cyber2_intake_document_path":
                lambda **kwargs: INDEX,
            "_read_processing_json_blob": self.read_index,
            "_write_processing_json_blob": self.write_index,
            "promote_processing_center_json_native":
                self.promote,
            "_get_live_source_blob_service_client":
                self.live_service,
            "_live_source_container":
                lambda workspace: "synthetic-container",
            "get_processing_center_promotion_population":
                lambda **kwargs: {"json_hits": [self.row]},
            "_utc_now":
                lambda: "2026-11-19T00:00:00+00:00",
        }

        handler = load_endpoint(namespace)

        setting = {
            "INSYT_JSON_NATIVE_PROMOTION_ENABLED":
                "1" if enabled else "0"
        }

        with patch.dict(os.environ, setting):
            with patch.dict(sys.modules, azure_module_mocks()):
                return handler(
                    "capture",
                    self.request,
                    self.admin,
                )

    def test_all_six_profiles(self):
        examples = [
            (b'{"people":[]}', "plain"),
            (
                b'{"channels":[],"users":[],"messages":[]}',
                "slack",
            ),
            (b'{"teamId":"synthetic"}', "teams"),
            (
                b'{"records":[],"totalSize":0,"done":true}',
                "salesforce",
            ),
            (b'{"spaces":[]}', "google"),
            (b'{"custom_records":[]}', "custom_api"),
        ]

        for raw, profile in examples:
            with self.subTest(profile=profile):
                self.setUp()
                self.native = raw

                result = self.execute()

                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["source_profile"], profile)
                self.assertTrue(result["files_verified"])
                self.assertTrue(result["cyber2_verified"])
                self.assertTrue(result["verified"])
                self.assertFalse(result["csv_generated"])
                self.assertEqual(
                    self.indexes[INDEX]["source_profile"],
                    profile,
                )
                self.assertEqual(
                    self.indexes[INDEX]["source_kind"],
                    "native_json",
                )
                self.assertIsNone(
                    self.indexes[INDEX]["source_csv_path"]
                )
                self.assertEqual(self.writes, 1)

    def test_repeat_registration_is_idempotent(self):
        first = self.execute()
        second = self.execute()

        self.assertEqual(
            first["registration_status"],
            "registered_verified",
        )
        self.assertEqual(
            second["registration_status"],
            "already_registered_verified",
        )
        self.assertEqual(self.writes, 1)
        self.assertEqual(len(self.indexes), 1)

    def test_conflicting_index_rejected(self):
        self.execute()
        self.indexes[INDEX]["source_sha256"] = "0" * 64

        with self.assertRaises(MockHTTPException) as caught:
            self.execute()

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.writes, 1)

    def test_concurrent_registration_verified(self):
        self.concurrent_registration = True
        result = self.execute()

        self.assertEqual(
            result["registration_status"],
            "already_registered_verified",
        )
        self.assertTrue(result["cyber2_verified"])
        self.assertEqual(self.writes, 1)

    def test_files_failure_blocks_registration(self):
        self.fail_files = True

        with self.assertRaises(MockHTTPException) as caught:
            self.execute()

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.writes, 0)

    def test_registration_failure_is_explicit_and_retryable(self):
        self.fail_registration = True

        with self.assertRaises(MockHTTPException) as caught:
            self.execute()

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(self.writes, 0)

        self.fail_registration = False
        result = self.execute()

        self.assertTrue(result["cyber2_verified"])
        self.assertEqual(self.writes, 1)

    def test_native_hash_mismatch_rejected(self):
        self.corrupt_files = True

        with self.assertRaises(MockHTTPException) as caught:
            self.execute()

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.writes, 0)

    def test_disabled_feature_flag_blocks_promotion(self):
        with self.assertRaises(MockHTTPException) as caught:
            self.execute(enabled=False)

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.promotions, 0)
        self.assertEqual(self.writes, 0)


if __name__ == "__main__":
    unittest.main()
