import base64
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives import serialization

from insyt_artifact_integrity import fingerprint_directory
from insyt_release_evidence import (
    verify_release_evidence,
    scope_digest,
    ReleaseEvidenceDenied,
)
from insyt_signed_release_approval import canonical


class IntegratedEvidenceTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        (self.root / "app.py").write_bytes(b"synthetic-release")

        self.release = "a" * 40
        self.policy_sha = "b" * 40
        self.checkpoint = "c" * 40

        self.candidate = {
            "schema_version": 1,
            "feature": "cyber2-native-json",
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
            "candidate_commit": self.checkpoint,
            "components": {
                "api": {
                    "changes": {
                        "backend/app/api/cyber2/example.py": "M"
                    }
                }
            },
        }

        self.blobs = {
            "backend/app/api/cyber2/example.py": "d" * 40
        }

        self.approval = {
            "approval_status": "APPROVED",
            "approval_id": "synthetic-test-only",
            "feature": "cyber2-native-json",
            "candidate_commit": self.checkpoint,
            "release_commit": self.release,
            "components": self.candidate["components"],
            "source_blobs": dict(self.blobs),
        }

        self.policy = {
            "schema_version": 1,
            "approved_scopes": [self.approval],
        }

        self.private_key = Ed25519PrivateKey.generate()

        self.public_key = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        self.payload = {
            "schema_version": 1,
            "repository": "NPSZ12/INSYT_SAAS",
            "component": "api",
            "release_commit": self.release,
            "policy_commit": self.policy_sha,
            "scope_sha256": scope_digest(self.approval),
            "artifact_sha256": fingerprint_directory(
                self.root
            )["sha256"],
        }

        self.resign()

    def resign(self):
        signature = self.private_key.sign(canonical(self.payload))

        self.envelope = {
            "payload": dict(self.payload),
            "signature": base64.b64encode(
                signature
            ).decode("ascii"),
        }

    def check(self, **overrides):
        arguments = {
            "candidate": self.candidate,
            "source_blobs": self.blobs,
            "policy": self.policy,
            "trusted_policy_commit": self.policy_sha,
            "actual_policy_commit": self.policy_sha,
            "trusted_public_key": self.public_key,
            "signed_envelope": self.envelope,
            "artifact_directory": self.root,
            "release_commit": self.release,
            "component": "api",
        }

        arguments.update(overrides)

        return verify_release_evidence(**arguments)

    def test_valid_signed_evidence_passes(self):
        result = self.check()

        self.assertTrue(result["evidence_verified"])
        self.assertFalse(result["deployment_authorized"])

    def test_tampered_artifact_denied(self):
        (self.root / "app.py").write_bytes(b"tampered")

        with self.assertRaises(ReleaseEvidenceDenied):
            self.check()

    def test_extra_artifact_file_denied(self):
        (self.root / "unexpected.py").write_bytes(b"extra")

        with self.assertRaises(ReleaseEvidenceDenied):
            self.check()

    def test_wrong_release_commit_denied(self):
        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(release_commit="e" * 40)

    def test_wrong_policy_commit_denied(self):
        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(actual_policy_commit="e" * 40)

    def test_unapproved_scope_denied(self):
        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(policy={
                "schema_version": 1,
                "approved_scopes": [],
            })

    def test_missing_approved_release_commit_denied(self):
        self.approval.pop("release_commit")
        self.payload["scope_sha256"] = scope_digest(self.approval)
        self.resign()

        with self.assertRaises(ReleaseEvidenceDenied):
            self.check()

    def test_different_approved_release_commit_denied(self):
        self.approval["release_commit"] = "f" * 40
        self.payload["scope_sha256"] = scope_digest(self.approval)
        self.resign()

        with self.assertRaises(ReleaseEvidenceDenied):
            self.check()

    def test_changed_source_blob_denied(self):
        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(source_blobs={
                "backend/app/api/cyber2/example.py": "e" * 40
            })

    def test_wrong_verification_key_denied(self):
        other_key = Ed25519PrivateKey.generate()

        raw = other_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(trusted_public_key=raw)

    def test_changed_component_denied(self):
        with self.assertRaises(ReleaseEvidenceDenied):
            self.check(component="frontend")


if __name__ == "__main__":
    unittest.main()
