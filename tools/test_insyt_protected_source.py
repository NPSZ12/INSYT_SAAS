"""Permanent protected-source security regressions."""

import copy
import unittest

from unittest.mock import patch

import insyt_protected_source as protected

from insyt_release_transition import TransitionDenied


class ProtectedSourceTests(unittest.TestCase):

    def setUp(self):

        self.baseline = "a" * 40
        self.candidate = "b" * 40
        self.reference = "c" * 40
        self.blob = "d" * 40

        self.registry = {
            "schema_version": 1,
            "policy": {
                "automatic_hardening": False,
                "automatic_baseline_replacement": False,
                "automatic_test_removal": False,
                "protected_deletion_requires_explicit_approval": True,
                "registry_changes_require_independent_review": True,
                "production_verification_required_for_promotion": True,
            },
            "protected_source": [],
        }

        self.history = {
            "schema_version": 1,
            "features": {},
        }

        for index, path in enumerate(
            sorted(protected.REQUIRED_PATHS), 1
        ):

            identity = f"protected-{index}"

            self.registry["protected_source"].append({
                "id": identity,
                "path": path,
                "git_blob_sha": self.blob,
                "reference_commit": self.reference,
                "protection": "source_integrity",
                "verification":
                    "source_only_not_full_runtime_attestation",
            })

            self.history["features"][identity] = {
                "versions": [{
                    "version": 1,
                    "source": {path: self.blob},
                }],
            }

        revision_patch = patch.object(
            protected,
            "revision",
            side_effect=lambda value: value,
        )

        revision_patch.start()
        self.addCleanup(revision_patch.stop)

        blob_patch = patch.object(
            protected,
            "source_blob",
            side_effect=self.lookup_blob,
        )

        self.lookup = blob_patch.start()
        self.addCleanup(blob_patch.stop)

    def lookup_blob(self, commit, path):
        return self.blob

    def validate(self):
        return protected.validate_registry(
            self.registry,
            self.history,
            self.baseline,
            self.candidate,
        )

    def test_valid_protected_registry(self):
        self.assertEqual(self.validate(), 9)

    def test_missing_protected_record_rejected(self):

        removed = self.registry["protected_source"].pop()

        self.history["features"].pop(removed["id"])

        with self.assertRaisesRegex(
            TransitionDenied,
            "Mandatory protected source missing",
        ):
            self.validate()

    def test_duplicate_protected_path_rejected(self):

        self.registry["protected_source"].append(
            copy.deepcopy(
                self.registry["protected_source"][0]
            )
        )

        with self.assertRaisesRegex(
            TransitionDenied,
            "Duplicate protected source record",
        ):
            self.validate()

    def test_automatic_hardening_rejected(self):

        self.registry["policy"]["automatic_hardening"] = True

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_automatic_baseline_replacement_rejected(self):

        self.registry["policy"][
            "automatic_baseline_replacement"
        ] = True

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_automatic_test_removal_rejected(self):

        self.registry["policy"]["automatic_test_removal"] = True

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_independent_review_disabled_rejected(self):

        self.registry["policy"][
            "registry_changes_require_independent_review"
        ] = False

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_production_verification_disabled_rejected(self):

        self.registry["policy"][
            "production_verification_required_for_promotion"
        ] = False

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_protection_disabled_rejected(self):

        self.registry["protected_source"][0][
            "protection"
        ] = "none"

        with self.assertRaises(TransitionDenied):
            self.validate()

    def test_registry_history_mismatch_rejected(self):

        self.registry["protected_source"][0][
            "git_blob_sha"
        ] = "e" * 40

        with self.assertRaisesRegex(
            TransitionDenied,
            "Registry differs from latest protected history",
        ):
            self.validate()

    def test_historical_reference_mismatch_rejected(self):

        self.lookup.side_effect = (
            lambda commit, path:
                "e" * 40
                if commit == self.reference
                else self.blob
        )

        with self.assertRaisesRegex(
            TransitionDenied,
            "Historical source identity mismatch",
        ):
            self.validate()

    def test_production_baseline_mismatch_rejected(self):

        self.lookup.side_effect = (
            lambda commit, path:
                "e" * 40
                if commit == self.baseline
                else self.blob
        )

        with self.assertRaisesRegex(
            TransitionDenied,
            "Production baseline identity mismatch",
        ):
            self.validate()

    def test_candidate_source_mismatch_rejected(self):

        self.lookup.side_effect = (
            lambda commit, path:
                "e" * 40
                if commit == self.candidate
                else self.blob
        )

        with self.assertRaisesRegex(
            TransitionDenied,
            "Candidate protected source mismatch",
        ):
            self.validate()

    def test_invalid_version_sequence_rejected(self):

        feature = next(iter(self.history["features"]))

        self.history["features"][feature][
            "versions"
        ][0]["version"] = 2

        with self.assertRaisesRegex(
            TransitionDenied,
            "Invalid protected version sequence",
        ):
            self.validate()

    def test_changed_history_population_rejected(self):

        feature = next(iter(self.history["features"]))

        self.history["features"][feature][
            "versions"
        ].append({
            "version": 2,
            "source": {
                "backend/app/unrelated.py": self.blob,
            },
        })

        with self.assertRaisesRegex(
            TransitionDenied,
            "Protected version source inventory changed",
        ):
            self.validate()

    def test_valid_version_two_accepted(self):

        record = self.registry["protected_source"][0]

        path = record["path"]
        new_blob = "e" * 40

        self.history["features"][record["id"]][
            "versions"
        ].append({
            "version": 2,
            "source": {path: new_blob},
        })

        record["git_blob_sha"] = new_blob

        self.lookup.side_effect = (
            lambda commit, requested_path:
                new_blob
                if requested_path == path
                else self.blob
        )

        self.assertEqual(self.validate(), 9)

    def test_policy_commit_used_for_both_documents(self):

        policy = "f" * 40

        with patch.object(
            protected,
            "read_policy_json",
            side_effect=[self.registry, self.history],
        ) as reader:

            count = protected.verify_protected_source(
                policy,
                self.baseline,
                self.candidate,
            )

        self.assertEqual(count, 9)

        self.assertEqual(
            [call.args for call in reader.call_args_list],
            [
                (policy, protected.REGISTRY),
                (policy, protected.HISTORY),
            ],
        )


if __name__ == "__main__":
    unittest.main()
