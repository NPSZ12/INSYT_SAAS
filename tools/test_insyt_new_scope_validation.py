"""Permanent new application scope security regressions."""

import copy
import unittest

from unittest.mock import patch

import insyt_new_scope_validation as scope

from insyt_release_transition import TransitionDenied


class NewScopeValidationTests(unittest.TestCase):

    def setUp(self):

        self.policy = "a" * 40
        self.baseline = "b" * 40
        self.candidate = "c" * 40
        self.feature = "synthetic-application-upgrade"

        self.ledger = {
            "schema_version": 1,
            "approved_scopes": [{
                "approval_status": "APPROVED",
                "release_commit": self.baseline,
            }],
        }

        self.components = {
            "api": {
                "baseline": self.baseline,
                "root": "backend/",
                "changes": {
                    "backend/app/example.py": "M",
                },
            },
            "frontend": {
                "baseline": self.baseline,
                "root": "frontend/",
                "changes": {
                    "frontend/src/components/Example.tsx": "A",
                },
            },
        }

        self.transition = {
            "baseline": self.baseline,
            "candidate_commit": self.candidate,
            "components": self.components,
            "source_blobs": {
                "backend/app/example.py": "d" * 40,
                "frontend/src/components/Example.tsx": "e" * 40,
            },
        }

        patches = {
            "revision": patch.object(
                scope,
                "revision",
                side_effect=lambda value: value,
            ),
            "read_policy_json": patch.object(
                scope,
                "read_policy_json",
                return_value=self.ledger,
            ),
            "inspect_transition": patch.object(
                scope,
                "inspect_transition",
                return_value=self.transition,
            ),
            "verify_protected_source": patch.object(
                scope,
                "verify_protected_source",
                return_value=9,
            ),
        }

        self.mocks = {}

        for name, replacement in patches.items():

            self.mocks[name] = replacement.start()
            self.addCleanup(replacement.stop)

    def proposed(self):

        return copy.deepcopy(
            scope.prepare_scope(
                self.policy,
                self.candidate,
                self.feature,
            )
        )

    def verify(self, proposed=None):

        if proposed is None:
            proposed = self.proposed()

        return scope.verify_new_scope(
            self.policy,
            proposed,
        )

    def test_valid_new_scope(self):

        result = self.verify()

        self.assertTrue(result["scope_verified"])
        self.assertEqual(result["protected_source_count"], 9)

        self.assertFalse(
            result["production_deployment_authorized"]
        )

        self.assertEqual(
            result["source_blobs"],
            self.transition["source_blobs"],
        )

    def test_baseline_from_trusted_policy(self):

        self.assertEqual(
            scope.approved_baseline(self.policy),
            self.baseline,
        )

        self.mocks["read_policy_json"].assert_called_with(
            self.policy,
            scope.LEDGER,
        )

    def test_empty_approval_ledger_rejected(self):

        self.ledger["approved_scopes"] = []

        with self.assertRaises(TransitionDenied):
            scope.approved_baseline(self.policy)

    def test_multiple_approvals_rejected(self):

        self.ledger["approved_scopes"].append(
            copy.deepcopy(
                self.ledger["approved_scopes"][0]
            )
        )

        with self.assertRaises(TransitionDenied):
            scope.approved_baseline(self.policy)

    def test_unapproved_baseline_rejected(self):

        self.ledger["approved_scopes"][0][
            "approval_status"
        ] = "PENDING"

        with self.assertRaises(TransitionDenied):
            scope.approved_baseline(self.policy)

    def test_invalid_baseline_identity_rejected(self):

        self.ledger["approved_scopes"][0][
            "release_commit"
        ] = "invalid"

        with self.assertRaises(TransitionDenied):
            scope.approved_baseline(self.policy)

    def test_candidate_baseline_substitution_rejected(self):

        proposed = self.proposed()

        proposed["components"]["api"][
            "baseline"
        ] = "f" * 40

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_missing_changed_path_rejected(self):

        proposed = self.proposed()

        proposed["components"]["api"][
            "changes"
        ] = {}

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_extra_changed_path_rejected(self):

        proposed = self.proposed()

        proposed["components"]["api"]["changes"][
            "backend/app/unapproved.py"
        ] = "A"

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_candidate_self_approval_rejected(self):

        proposed = self.proposed()

        proposed["status"] = "APPROVED"

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_candidate_deployment_authority_rejected(self):

        proposed = self.proposed()

        proposed[
            "production_deployment_authorized"
        ] = True

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_unexpected_manifest_fields_rejected(self):

        proposed = self.proposed()

        proposed["override"] = True

        with self.assertRaises(TransitionDenied):
            self.verify(proposed)

    def test_invalid_feature_identity_rejected(self):

        with self.assertRaises(TransitionDenied):

            scope.prepare_scope(
                self.policy,
                self.candidate,
                "../invalid-feature",
            )

    def test_protected_source_failure_blocks_scope(self):

        proposed = self.proposed()

        self.mocks[
            "verify_protected_source"
        ].side_effect = TransitionDenied(
            "STOP: Protected source mismatch"
        )

        with self.assertRaisesRegex(
            TransitionDenied,
            "Protected source mismatch",
        ):
            self.verify(proposed)

    def test_protected_check_uses_exact_identities(self):

        self.verify()

        self.mocks[
            "verify_protected_source"
        ].assert_called_once_with(
            self.policy,
            self.baseline,
            self.candidate,
        )

    def test_invalid_ledger_schema_rejected(self):

        self.ledger["schema_version"] = 2

        with self.assertRaises(TransitionDenied):
            scope.approved_baseline(self.policy)


if __name__ == "__main__":
    unittest.main()
