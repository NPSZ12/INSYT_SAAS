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
            "legacy_policy": patch.object(
                scope,
                "LEGACY_PREINSTALLATION_POLICY",
                self.policy,
            ),
            "installation_git": patch(
                "insyt_release_transition.git",
                return_value=b"",
            ),
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



class SecurityBaselineResolutionTests(unittest.TestCase):

    def setUp(self):

        import json

        self.policy = "a" * 40
        self.production = "b" * 40
        self.installation = "c" * 40
        self.previous_policy = "d" * 40

        self.prefix = (
            ".github/insyt-release/security-installation/"
        )

        self.registry = {"synthetic_registry": True}
        self.history = {"synthetic_history": True}

        self.documents = {
            "authorization.json": {
                "payload": {
                    "previous_policy_commit":
                        self.previous_policy,
                },
            },
            "transition.json": {},
            "registry.json": self.registry,
            "history.json": self.history,
            "production-evidence.json": {},
        }

        self.entries = [
            self.prefix + name
            for name in self.documents
        ]

        self.result = {
            "previous_production_commit": self.production,
            "security_installation_commit": self.installation,
            "previous_policy_commit": self.previous_policy,
            "security_transition_verified": True,
            "production_deployment_authorized": False,
        }

        self.ancestry = []

        def git(*args):

            if args[0] == "ls-tree":
                return "\n".join(self.entries).encode()

            if args[0] == "show":
                name = args[1].split(":", 1)[1]
                name = name.removeprefix(self.prefix)
                return json.dumps(
                    self.documents[name]
                ).encode()

            if args[:2] == (
                "merge-base", "--is-ancestor"
            ):
                self.ancestry.append(args[2:])
                return b""

            raise AssertionError(
                "Unexpected Git operation: " + repr(args)
            )

        def read_policy(commit, path):

            self.assertEqual(commit, self.policy)

            if path.endswith("hardened-registry.json"):
                return self.registry

            if path.endswith("hardened-history.json"):
                return self.history

            raise AssertionError("Unexpected policy lookup")

        patches = {
            "approved": patch.object(
                scope,
                "approved_baseline",
                return_value=self.production,
            ),
            "revision": patch.object(
                scope,
                "revision",
                side_effect=lambda value: value,
            ),
            "git": patch(
                "insyt_release_transition.git",
                side_effect=git,
            ),
            "signature": patch(
                "insyt_policy_renewal."
                "verify_security_installation_transition",
                return_value=self.result,
            ),
            "policy": patch.object(
                scope,
                "read_policy_json",
                side_effect=read_policy,
            ),
        }

        self.mocks = {}

        for name, replacement in patches.items():
            self.mocks[name] = replacement.start()
            self.addCleanup(replacement.stop)

    def resolve(self):
        return scope.resolve_release_baselines(self.policy)

    def test_legacy_policy_without_installation(self):

        self.entries.clear()

        with patch.object(
            scope,
            "LEGACY_PREINSTALLATION_POLICY",
            self.policy,
        ):
            result = self.resolve()

        self.assertEqual(
            result["source_baseline"],
            self.production,
        )

        self.assertFalse(
            result["security_installation_verified"]
        )

        self.mocks["signature"].assert_not_called()

    def test_verified_installation_is_source_baseline(self):

        result = self.resolve()

        self.assertEqual(
            result["approved_release_baseline"],
            self.production,
        )

        self.assertEqual(
            result["source_baseline"],
            self.installation,
        )

        self.assertTrue(
            result["security_installation_verified"]
        )

        self.mocks["signature"].assert_called_once()

    def test_complete_installation_removal_rejected(self):

        self.entries.clear()

        with self.assertRaisesRegex(
            TransitionDenied,
            "Required security installation evidence missing",
        ):
            self.resolve()

        self.mocks["signature"].assert_not_called()

    def test_partial_installation_evidence_rejected(self):

        self.entries.pop()

        with self.assertRaises(TransitionDenied):
            self.resolve()

        self.mocks["signature"].assert_not_called()

    def test_unexpected_installation_file_rejected(self):

        self.entries.append(
            self.prefix + "unexpected.json"
        )

        with self.assertRaises(TransitionDenied):
            self.resolve()

    def test_invalid_signature_propagates(self):

        from insyt_policy_renewal import RenewalDenied

        self.mocks["signature"].side_effect = (
            RenewalDenied("Invalid signature")
        )

        with self.assertRaises(RenewalDenied):
            self.resolve()

    def test_unverified_installation_rejected(self):

        self.result["security_transition_verified"] = False

        with self.assertRaises(TransitionDenied):
            self.resolve()

    def test_deployment_authority_claim_rejected(self):

        self.result[
            "production_deployment_authorized"
        ] = True

        with self.assertRaises(TransitionDenied):
            self.resolve()

    def test_modified_published_registry_rejected(self):

        self.documents["registry.json"] = {
            "modified": True
        }

        with self.assertRaises(TransitionDenied):
            self.resolve()

    def test_modified_published_history_rejected(self):

        self.documents["history.json"] = {
            "modified": True
        }

        with self.assertRaises(TransitionDenied):
            self.resolve()

    def test_later_approved_release_uses_its_own_baseline(self):

        later = "e" * 40

        self.mocks["approved"].return_value = later

        result = self.resolve()

        self.assertEqual(
            result["source_baseline"],
            later,
        )

        self.assertEqual(
            result["approved_release_baseline"],
            later,
        )

        self.assertIn(
            (self.installation, later),
            self.ancestry,
        )

    def test_git_lookup_failure_is_not_missing_evidence(self):

        self.mocks["git"].side_effect = (
            TransitionDenied("Git lookup failed")
        )

        with self.assertRaises(TransitionDenied):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
