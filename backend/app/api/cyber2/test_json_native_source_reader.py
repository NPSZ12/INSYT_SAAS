import ast
import hashlib
import re
import unittest
from pathlib import Path
from unittest.mock import Mock


SOURCE = Path(__file__).with_name("schema_mapping.py")


class MockHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def load_reader(namespace):
    """Isolate the actual production function without Azure imports."""
    source = ast.parse(
        SOURCE.read_text(encoding="utf-8-sig")
    )

    matches = [
        node for node in source.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_read_verified_native_json_for_mapping"
    ]

    if len(matches) != 1:
        raise AssertionError("Native JSON reader not found exactly once.")

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            matches[0],
        ],
        type_ignores=[],
    )

    exec(
        compile(
            ast.fix_missing_locations(module),
            str(SOURCE),
            "exec",
        ),
        namespace,
    )

    return namespace["_read_verified_native_json_for_mapping"]


class NativeSourceReaderTests(unittest.TestCase):

    def setUp(self):
        self.data = b'{"name":"Avery"}'
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.base = "synthetic/capture/project"
        self.path = (
            self.base
            + "/source/native/INSYT000000077.json"
        )

        self.approved = {
            "doc_id": "INSYT000000077",
            "source_kind": "native_json",
            "source_native_path": self.path,
            "source_sha256": self.sha,
            "source_format": "json",
            "source_bytes": len(self.data),
        }

        self.registration = {
            "doc_id": self.approved["doc_id"],
            "source_kind": "native_json",
            "source_native_path": self.path,
            "source_sha256": self.sha,
            "source_bytes": len(self.data),
        }

        self.blob = Mock()
        self.blob.download_blob.return_value.readall.return_value = (
            self.data
        )

        self.service = Mock()
        self.service.get_blob_client.return_value = self.blob

        self.read_registration = Mock(
            return_value=self.registration
        )

        self.namespace = {
            "hashlib": hashlib,
            "re": re,
            "HTTPException": MockHTTPException,
            "_project_base_path": (
                lambda **kwargs: self.base
            ),
            "_read_processing_json_blob": (
                self.read_registration
            ),
            "_get_live_source_blob_service_client": (
                lambda: self.service
            ),
            "_live_source_container": (
                lambda workspace: "synthetic-live-source"
            ),
        }

        self.reader = load_reader(self.namespace)

    def read(self):
        return self.reader(
            workspace="capture",
            client="SyntheticClient",
            project="SyntheticProject",
            approved_document=self.approved,
        )

    def test_valid_registered_source_is_returned_unchanged(self):
        self.assertEqual(self.read(), self.data)

        self.read_registration.assert_called_once_with(
            self.base
            + "/cyber2/intake/documents/INSYT000000077.json"
        )

        self.service.get_blob_client.assert_called_once_with(
            container="synthetic-live-source",
            blob=self.path,
        )

        self.blob.download_blob.assert_called_once_with(
            offset=0,
            length=4 * 1024 * 1024 + 1,
        )

        self.blob.upload_blob.assert_not_called()

    def test_rejects_wrong_project_source_path(self):
        self.approved["source_native_path"] = (
            "another-project/source/native/INSYT000000077.json"
        )

        with self.assertRaises(MockHTTPException) as caught:
            self.read()

        self.assertEqual(caught.exception.status_code, 409)
        self.service.get_blob_client.assert_not_called()

    def test_rejects_intake_registration_mismatch(self):
        self.registration["source_sha256"] = "0" * 64

        with self.assertRaises(MockHTTPException) as caught:
            self.read()

        self.assertEqual(caught.exception.status_code, 409)
        self.service.get_blob_client.assert_not_called()

    def test_rejects_original_byte_hash_mismatch(self):
        self.blob.download_blob.return_value.readall.return_value = (
            b'{"name":"Other"}'
        )

        with self.assertRaises(MockHTTPException) as caught:
            self.read()

        self.assertEqual(caught.exception.status_code, 409)

    def test_rejects_oversized_registered_source(self):
        count = 4 * 1024 * 1024 + 1
        self.approved["source_bytes"] = count
        self.registration["source_bytes"] = count

        with self.assertRaises(MockHTTPException) as caught:
            self.read()

        self.assertEqual(caught.exception.status_code, 409)
        self.service.get_blob_client.assert_not_called()

    def test_rejects_missing_byte_count_evidence(self):
        self.registration.pop("source_bytes")

        with self.assertRaises(MockHTTPException) as caught:
            self.read()

        self.assertEqual(caught.exception.status_code, 409)
        self.service.get_blob_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
