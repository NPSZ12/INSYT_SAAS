"""Dynamic deployment source-scope security regressions."""

import copy
import unittest

from unittest.mock import patch

import insyt_deployment_gate as gate


class DynamicDeploymentScopeTests(unittest.TestCase):

    def setUp(self):

        self.release = "a" * 40
        self.baseline = "b" * 40
        self.checkpoint = "c" * 40
        self.blob = "d" * 40

        self.candidate = {
            "schema_version": 1,
            "feature": "synthetic-upgrade",
            "candidate_commit": self.checkpoint,
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
            "components": {
                "api": {
                    "root": "backend/",
                    "baseline": self.baseline,
                    "changes": {
                        "backend/app/example.py": "M",
                    },
                },
                "frontend": {
                    "root": "frontend/",
                    "baseline": self.baseline,
                    "changes": {
                        "frontend/src/components/Example.tsx": "A",
                    },
                },
            },
        }

        self.approval = {
            "approval_id": "SYNTHETIC-APPROVAL",
            "approval_status": "APPROVED",
            "release_commit": self.release,
            "candidate_commit": self.checkpoint,
            "feature": self.candidate["feature"],
            "components": copy.deepcopy(
                self.candidate["components"]
            ),
            "source_blobs": {
                path: self.blob
                for component in self.candidate["components"].values()
                for path in component["changes"]
            },
        }

        self.policy = {
            "schema_version": 1,
            "approved_scopes": [self.approval],
        }

        replacement = patch.object(
            gate,
            "git",
            return_value=self.blob,
        )

        self.git = replacement.start()
        self.addCleanup(replacement.stop)

    def verify(self):

        return gate.verify_approved_source_scope(
            self.candidate,
            self.policy,
            self.release,
        )

    def denied(self):

        with self.assertRaises(RuntimeError):
            self.verify()

    def synchronize_scope(self):

        self.approval["components"] = copy.deepcopy(
            self.candidate["components"]
        )

        self.approval["source_blobs"] = {
            path: self.blob
            for component in self.candidate["components"].values()
            for path in component["changes"]
        }

    def test_dynamic_two_file_scope_accepted(self):

        self.assertEqual(
            self.verify(),
            self.approval["source_blobs"],
        )

        self.assertEqual(self.git.call_count, 2)

    def test_api_only_upgrade_accepted(self):

        self.candidate["components"]["frontend"]["changes"] = {}

        self.synchronize_scope()

        self.assertEqual(len(self.verify()), 1)

    def test_frontend_only_upgrade_accepted(self):

        self.candidate["components"]["api"]["changes"] = {}

        self.synchronize_scope()

        self.assertEqual(len(self.verify()), 1)

    def test_large_dynamic_scope_accepted(self):

        for index in range(30):

            self.candidate["components"]["api"]["changes"][
                f"backend/app/example_{index}.py"
            ] = "A"

        self.synchronize_scope()

        self.assertEqual(len(self.verify()), 32)

    def test_missing_approval_rejected(self):

        self.policy["approved_scopes"] = []

        self.denied()

    def test_duplicate_approval_rejected(self):

        self.policy["approved_scopes"].append(
            copy.deepcopy(self.approval)
        )

        self.denied()

    def test_unapproved_status_rejected(self):

        self.approval["approval_status"] = "PENDING"

        self.denied()

    def test_wrong_release_rejected(self):

        self.approval["release_commit"] = "e" * 40

        self.denied()

    def test_wrong_candidate_rejected(self):

        self.approval["candidate_commit"] = "e" * 40

        self.denied()

    def test_wrong_feature_rejected(self):

        self.approval["feature"] = "unapproved-feature"

        self.denied()

    def test_candidate_scope_change_rejected(self):

        self.candidate["components"]["api"]["changes"][
            "backend/app/unapproved.py"
        ] = "A"

        self.denied()

    def test_wrong_component_root_rejected(self):

        self.candidate["components"]["api"]["root"] = "frontend/"

        self.synchronize_scope()
        self.denied()

    def test_invalid_baseline_rejected(self):

        self.candidate["components"]["api"]["baseline"] = "invalid"

        self.synchronize_scope()
        self.denied()

    def test_cross_component_source_rejected(self):

        self.candidate["components"]["api"]["changes"][
            "frontend/src/unapproved.tsx"
        ] = "A"

        self.synchronize_scope()
        self.denied()

    def test_source_deletion_rejected(self):

        self.candidate["components"]["api"]["changes"][
            "backend/app/example.py"
        ] = "D"

        self.synchronize_scope()
        self.denied()

    def test_unsafe_path_rejected(self):

        self.candidate["components"]["api"]["changes"][
            "backend/../unapproved.py"
        ] = "A"

        self.synchronize_scope()
        self.denied()

    def test_missing_source_blob_rejected(self):

        self.approval["source_blobs"].pop(
            "backend/app/example.py"
        )

        self.denied()

    def test_extra_source_blob_rejected(self):

        self.approval["source_blobs"][
            "backend/app/unapproved.py"
        ] = self.blob

        self.denied()

    def test_modified_source_blob_rejected(self):

        self.git.return_value = "e" * 40

        self.denied()

    def test_empty_application_scope_rejected(self):

        for component in self.candidate["components"].values():
            component["changes"] = {}

        self.synchronize_scope()
        self.denied()


if __name__ == "__main__":
    unittest.main()
