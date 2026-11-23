import copy
import importlib.util
import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("c2_origin_authorization.py")


def load_policy():
    spec = importlib.util.spec_from_file_location(
        "_insyt_json_origin_policy_test",
        SOURCE,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JsonOriginAuthorizationTests(unittest.TestCase):

    def setUp(self):
        self.policy = load_policy()

        self.scope = {
            "workspace": "capture",
            "client": "SyntheticClient",
            "project": "SyntheticProject",
            "header_set_id": "HDRSET-SYNTHETIC",
        }

        self.merge = {
            **self.scope,
            "status": "completed",
            "merge_set_id": "MSET-" + "A" * 32,
            "integrity_sha256": "b" * 64,
        }

        self.original_path = (
            "synthetic/project/source/native/"
            "INSYT000000077.json"
        )

        self.native_document = {
            "doc_id": "INSYT000000077",
            "source_kind": "native_json",
            "source_native_path": self.original_path,
            "source_sha256": "a" * 64,
            "source_csv_path": "",
        }

        self.mapping = {
            **self.scope,
            "status": "approved",
            "documents": [self.native_document],
        }

        self.receipt = {
            **self.scope,
            "merge_set_id": self.merge["merge_set_id"],
            "merge_integrity_sha256": (
                self.merge["integrity_sha256"]
            ),
            "decision": "approved_non_ai",
            "authorized_by": "SyntheticAdministrator",
            "authorized_at": "2026-11-23T00:00:00Z",
            "documents": [{
                "doc_id": "INSYT000000077",
                "source_kind": "native_json",
                "source_native_path": self.original_path,
                "source_json_path": self.original_path,
                "source_sha256": "a" * 64,
                "capture_method": "non_ai_structured_source",
            }],
        }

    def authorize(self):
        return self.policy.require_c2_origin_authorization(
            self.merge,
            self.mapping,
            self.receipt,
        )

    def test_native_json_original_identity_is_accepted(self):
        result = self.authorize()

        self.assertTrue(result["origin_authorized"])
        self.assertEqual(
            result["authorized_document_count"], 1
        )

    def test_json_alias_mismatch_is_rejected(self):
        self.receipt["documents"][0]["source_json_path"] = (
            "another/project/source/native/OTHER.json"
        )

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_json_hash_mismatch_is_rejected(self):
        self.receipt["documents"][0]["source_sha256"] = "c" * 64

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_json_missing_original_identity_is_rejected(self):
        self.mapping["documents"][0].pop("source_native_path")

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_json_non_ai_attestation_is_still_required(self):
        self.receipt["documents"][0]["capture_method"] = (
            "ai_generated"
        )

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_existing_csv_authorization_is_unchanged(self):
        self.mapping["documents"] = [{
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/project/source/CSV001.csv",
        }]

        self.receipt["documents"] = [{
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/project/source/CSV001.csv",
            "capture_method": "non_ai_structured_source",
        }]

        result = self.authorize()
        self.assertTrue(result["origin_authorized"])

        self.receipt["documents"][0]["source_csv_path"] = ""

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_native_json_cannot_impersonate_original_csv(self):
        self.receipt["documents"] = [{
            "doc_id": "INSYT000000077",
            "source_csv_path": "synthetic/generated/INSYT000000077.csv",
            "capture_method": "non_ai_structured_source",
        }]

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_approved_json_with_ai_origin_is_rejected(self):
        self.mapping["documents"][0]["source_origin"] = "ai_extracted"

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()

    def test_approved_csv_with_ai_origin_is_rejected(self):
        self.mapping["documents"] = [{
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/source/CSV001.csv",
            "source_origin": "ai_generated",
        }]
        self.receipt["documents"] = [{
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/source/CSV001.csv",
            "capture_method": "non_ai_structured_source",
        }]

        with self.assertRaises(
            self.policy.C2OriginAuthorizationError
        ):
            self.authorize()


if __name__ == "__main__":
    unittest.main()
