"""Signed new application scope integration regressions."""

import base64
import copy
import hashlib
import unittest

from unittest.mock import patch

import insyt_policy_renewal as renewal
import insyt_new_scope_validation as new_scope

from insyt_release_transition import TransitionDenied

import test_insyt_policy_renewal as fixtures


class SignedNewScopeTests(unittest.TestCase):

    def setUp(self):

        self.fixture = fixtures.PolicyRenewalRegression(
            "test_valid_future_release"
        )

        self.fixture.setUp()

        f = self.fixture

        self.application_checkpoint = "6" * 40

        self.manifest_path = (
            renewal.PREFIX
            + "json-feature-scope-candidate.json"
        )

        f.current["feature"] = "synthetic-new-application-scope"

        f.current["candidate_commit"] = (
            self.application_checkpoint
        )

        f.current["components"] = {
            "api": {
                "baseline": f.previous_release,
                "root": "backend/",
                "changes": {
                    f.source_path: "M",
                },
            },
            "frontend": {
                "baseline": f.previous_release,
                "root": "frontend/",
                "changes": {},
            },
        }

        f.current["source_blobs"] = {
            f.source_path: f.source_blob,
        }

        f.candidate.update({
            "feature": f.current["feature"],
            "candidate_commit": self.application_checkpoint,
            "components": copy.deepcopy(
                f.current["components"]
            ),
        })

        self.evidence = {
            "baseline": f.previous_release,
            "candidate_commit": self.application_checkpoint,
            "feature": f.current["feature"],
            "components": copy.deepcopy(
                f.current["components"]
            ),
            "source_blobs": copy.deepcopy(
                f.current["source_blobs"]
            ),
            "protected_source_count": 9,
            "scope_verified": True,
            "release_source_verified": True,
            "release_commit": f.release,
            "production_deployment_authorized": False,
        }

        f.ancestry.add((
            self.application_checkpoint,
            f.release,
        ))

        f.deltas[
            (self.application_checkpoint, f.release)
        ] = {
            self.manifest_path: "M",
        }

        f.deltas[
            (f.previous_release, f.release)
        ] = {
            f.source_path: "M",
            self.manifest_path: "M",
        }

        self.resign()

    def resign(self):

        f = self.fixture

        digest = hashlib.sha256(
            renewal.canonical(f.current)
        ).hexdigest()

        for component in ("api", "frontend"):

            envelope = f.envelope(component)

            envelope["payload"]["scope_sha256"] = digest

            signature = f.private.sign(
                b"INSYT-RELEASE-APPROVAL-V1\n"
                + renewal.canonical(
                    envelope["payload"]
                )
            )

            envelope["signature"] = (
                base64.b64encode(signature).decode()
            )

    def validate(self):

        f = self.fixture

        with (
            patch.object(
                new_scope,
                "revision",
                side_effect=lambda value: value,
            ),
            patch.object(
                new_scope,
                "read_policy_json",
                return_value=f.candidate,
            ),
            patch.object(
                new_scope,
                "verify_new_scope",
                return_value=self.evidence,
            ) as verifier,
            patch.object(
                new_scope,
                "verify_protected_source",
                return_value=9,
            ),
            patch(
                "insyt_release_transition.git",
                side_effect=lambda command, flag, a, b:
                    f.check_ancestor(a, b),
            ),
            patch(
                "insyt_release_transition.changed_paths",
                side_effect=lambda a, b: f.deltas[(a, b)],
            ),
            patch(
                "insyt_release_transition.source_blob",
                return_value=f.actual_blob,
            ),
        ):
            f.validate()

        verifier.assert_called_once_with(
            f.base,
            f.candidate,
        )

    def denied(self):

        with self.assertRaises(
            (renewal.RenewalDenied, TransitionDenied)
        ):
            self.validate()

    def test_valid_signed_new_scope(self):

        self.validate()

    def test_wrong_verified_baseline_rejected(self):

        self.evidence["baseline"] = "7" * 40

        self.denied()

    def test_incomplete_scope_verification_rejected(self):

        self.evidence["scope_verified"] = False

        self.denied()

    def test_scope_validator_claims_deployment_rejected(self):

        self.evidence[
            "production_deployment_authorized"
        ] = True

        self.denied()

    def test_untrusted_application_checkpoint_rejected(self):

        self.fixture.ancestry.remove((
            self.application_checkpoint,
            self.fixture.release,
        ))

        self.denied()

    def test_extra_post_candidate_source_rejected(self):

        self.fixture.deltas[
            (
                self.application_checkpoint,
                self.fixture.release,
            )
        ]["backend/app/unapproved.py"] = "M"

        self.denied()

    def test_extra_post_candidate_gate_change_rejected(self):

        self.fixture.deltas[
            (
                self.application_checkpoint,
                self.fixture.release,
            )
        ]["tools/insyt_deployment_gate.py"] = "M"

        self.denied()

    def test_signed_but_unverified_blob_rejected(self):

        self.fixture.current["source_blobs"][
            self.fixture.source_path
        ] = "8" * 40

        self.resign()

        self.denied()

    def test_signed_but_unverified_scope_rejected(self):

        f = self.fixture

        f.current["components"]["api"]["changes"][
            "backend/app/unapproved.py"
        ] = "A"

        f.candidate["components"] = copy.deepcopy(
            f.current["components"]
        )

        self.resign()

        self.denied()

    def test_invalid_new_scope_signature_rejected(self):

        self.fixture.envelope()["signature"] = (
            base64.b64encode(b"\0" * 64).decode()
        )

        self.denied()

    def test_new_scope_artifact_tampering_rejected(self):

        self.fixture.envelope()["payload"][
            "artifact_sha256"
        ] = "9" * 64

        self.denied()

    def test_previous_approval_rewrite_rejected(self):

        f = self.fixture

        f.documents[
            (f.target, f.archive)
        ]["feature"] = "rewritten-history"

        self.denied()

    def test_previous_signature_rewrite_rejected(self):

        f = self.fixture

        f.deltas[(f.base, f.target)][
            renewal.PREFIX
            + "signed-releases/"
            + f.previous_release
            + "/api.json"
        ] = "M"

        self.denied()

    def test_registry_change_in_ordinary_scope_rejected(self):

        f = self.fixture

        f.deltas[(f.base, f.target)][
            renewal.PREFIX + "hardened-registry.json"
        ] = "M"

        self.denied()

    def test_protected_source_failure_propagates(self):

        with patch.object(
            new_scope,
            "verify_release_candidate",
            side_effect=TransitionDenied(
                "STOP: Protected source mismatch"
            ),
        ):

            with self.assertRaisesRegex(
                TransitionDenied,
                "Protected source mismatch",
            ):
                self.fixture.validate()


if __name__ == "__main__":
    unittest.main()
