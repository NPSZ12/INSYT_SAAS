"""Permanent final release candidate validation regressions."""

import copy
import unittest

from unittest.mock import patch

import insyt_new_scope_validation as scope
import insyt_release_transition as transition

from insyt_release_transition import TransitionDenied


class ReleaseCandidateTests(unittest.TestCase):

    def setUp(self):

        self.policy = "a" * 40
        self.baseline = "b" * 40
        self.checkpoint = "c" * 40
        self.release = "d" * 40
        self.blob = "e" * 40

        self.path = "backend/app/example.py"

        self.evidence = {
            "policy_commit": self.policy,
            "baseline": self.baseline,
            "candidate_commit": self.checkpoint,
            "feature": "synthetic-release",
            "components": {
                "api": {
                    "baseline": self.baseline,
                    "root": "backend/",
                    "changes": {
                        self.path: "M",
                    },
                },
                "frontend": {
                    "baseline": self.baseline,
                    "root": "frontend/",
                    "changes": {},
                },
            },
            "source_blobs": {
                self.path: self.blob,
            },
            "protected_source_count": 9,
            "scope_verified": True,
            "production_deployment_authorized": False,
        }

        self.proposed = {
            "schema_version": 1,
            "feature": self.evidence["feature"],
            "candidate_commit": self.checkpoint,
            "components": copy.deepcopy(
                self.evidence["components"]
            ),
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
        }

        self.deltas = {
            (self.checkpoint, self.release): {
                scope.MANIFEST: "M",
            },
            (self.baseline, self.release): {
                self.path: "M",
                scope.MANIFEST: "M",
            },
        }

        patches = {
            "revision": patch.object(
                scope,
                "revision",
                side_effect=lambda value: value,
            ),
            "read": patch.object(
                scope,
                "read_policy_json",
                return_value=self.proposed,
            ),
            "scope": patch.object(
                scope,
                "verify_new_scope",
                return_value=self.evidence,
            ),
            "protected": patch.object(
                scope,
                "verify_protected_source",
                return_value=9,
            ),
            "git": patch.object(
                transition,
                "git",
                return_value=b"",
            ),
            "changed": patch.object(
                transition,
                "changed_paths",
                side_effect=lambda a, b: self.deltas[(a, b)],
            ),
            "blob": patch.object(
                transition,
                "source_blob",
                return_value=self.blob,
            ),
        }

        self.mocks = {}

        for name, replacement in patches.items():
            self.mocks[name] = replacement.start()
            self.addCleanup(replacement.stop)

    def validate(self):

        return scope.verify_release_candidate(
            self.policy,
            self.release,
        )

    def denied(self):

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_valid_release_candidate(self):

        result = self.validate()

        self.assertTrue(result["release_source_verified"])

        self.assertFalse(
            result["production_deployment_authorized"]
        )

        self.assertEqual(
            result["release_commit"],
            self.release,
        )

    def test_manifest_read_from_exact_release(self):

        self.validate()

        self.mocks["read"].assert_called_once_with(
            self.release,
            scope.MANIFEST,
        )

    def test_untrusted_checkpoint_ancestry_rejected(self):

        self.mocks["git"].side_effect = TransitionDenied(
            "STOP: Invalid checkpoint ancestry"
        )

        self.denied()

    def test_extra_post_candidate_change_rejected(self):

        self.deltas[
            (self.checkpoint, self.release)
        ]["tools/insyt_deployment_gate.py"] = "M"

        self.denied()

    def test_extra_baseline_change_rejected(self):

        self.deltas[
            (self.baseline, self.release)
        ]["backend/app/unapproved.py"] = "A"

        self.denied()

    def test_missing_application_change_rejected(self):

        self.deltas[
            (self.baseline, self.release)
        ].pop(self.path)

        self.denied()

    def test_changed_release_blob_rejected(self):

        self.mocks["blob"].return_value = "f" * 40

        self.denied()

    def test_protected_release_change_rejected(self):

        self.mocks["protected"].side_effect = TransitionDenied(
            "STOP: Protected release source mismatch"
        )

        self.denied()

    def test_final_protected_source_verified(self):

        self.validate()

        self.mocks["protected"].assert_called_once_with(
            self.policy,
            self.baseline,
            self.release,
        )

    def test_new_scope_rejection_propagates(self):

        self.mocks["scope"].side_effect = TransitionDenied(
            "STOP: Unapproved application scope"
        )

        self.denied()


if __name__ == "__main__":
    unittest.main()
