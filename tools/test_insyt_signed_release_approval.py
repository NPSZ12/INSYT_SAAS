"""Temporary-key tests for INSYT signed release approval."""

import base64
import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives import serialization

from insyt_signed_release_approval import (
    ApprovalDenied,
    canonical,
    verify_signed_release,
)


class SignedReleaseApprovalTests(unittest.TestCase):

    def setUp(self):
        # Generated only in memory for each test.
        # These are NOT production signing credentials.
        self.private = Ed25519PrivateKey.generate()

        self.public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        self.payload = {
            "schema_version": 1,
            "repository": "NPSZ12/INSYT_SAAS",
            "component": "api",
            "release_commit": "a" * 40,
            "policy_commit": "b" * 40,
            "scope_sha256": "c" * 64,
            "artifact_sha256": "d" * 64,
        }

    def envelope(self):
        signature = self.private.sign(
            canonical(self.payload)
        )

        return {
            "payload": copy.deepcopy(self.payload),
            "signature": base64.b64encode(signature).decode("ascii"),
        }

    def verify(self, envelope, key=None, **overrides):
        expected = {
            "release_commit": "a" * 40,
            "policy_commit": "b" * 40,
            "scope_sha256": "c" * 64,
            "artifact_sha256": "d" * 64,
            "component": "api",
        }

        expected.update(overrides)

        return verify_signed_release(
            envelope,
            self.public if key is None else key,
            **expected,
        )

    def test_exact_signed_approval_passes(self):
        self.assertTrue(self.verify(self.envelope()))

    def test_modified_release_commit_rejected(self):
        envelope = self.envelope()
        envelope["payload"]["release_commit"] = "e" * 40

        with self.assertRaises(ApprovalDenied):
            self.verify(envelope)

    def test_other_policy_revision_rejected(self):
        with self.assertRaises(ApprovalDenied):
            self.verify(
                self.envelope(),
                policy_commit="e" * 40,
            )

    def test_other_feature_scope_rejected(self):
        with self.assertRaises(ApprovalDenied):
            self.verify(
                self.envelope(),
                scope_sha256="e" * 64,
            )

    def test_other_artifact_rejected(self):
        with self.assertRaises(ApprovalDenied):
            self.verify(
                self.envelope(),
                artifact_sha256="e" * 64,
            )

    def test_other_component_rejected(self):
        with self.assertRaises(ApprovalDenied):
            self.verify(
                self.envelope(),
                component="frontend",
            )

    def test_other_signing_key_rejected(self):
        other = Ed25519PrivateKey.generate()

        wrong_key = other.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        with self.assertRaises(ApprovalDenied):
            self.verify(self.envelope(), key=wrong_key)

    def test_changed_repository_rejected(self):
        envelope = self.envelope()
        envelope["payload"]["repository"] = "attacker/repository"

        with self.assertRaises(ApprovalDenied):
            self.verify(envelope)

    def test_unsigned_extra_permissions_rejected(self):
        envelope = self.envelope()
        envelope["payload"]["allow_auth_changes"] = True

        with self.assertRaises(ApprovalDenied):
            self.verify(envelope)

    def test_missing_signature_rejected(self):
        envelope = self.envelope()
        del envelope["signature"]

        with self.assertRaises(ApprovalDenied):
            self.verify(envelope)


if __name__ == "__main__":
    unittest.main()
