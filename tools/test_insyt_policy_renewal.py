"""Permanent negative security tests for policy renewal."""

import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

import insyt_policy_renewal as renewal


class PolicyRenewalRegression(unittest.TestCase):

    def setUp(self):

        self.base = "a" * 40
        self.target = "b" * 40
        self.release = "c" * 40
        self.previous_release = "d" * 40
        self.checkpoint = "e" * 40
        self.source_path = "backend/app/example.py"
        self.source_blob = "f" * 40

        self.private = Ed25519PrivateKey.generate()

        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self.previous = {
            "approval_id": "TEST-OLD-APPROVAL",
            "approval_status": "APPROVED",
            "release_commit": self.previous_release,
            "candidate_commit": "1" * 40,
            "feature": "synthetic-test",
            "components": {
                "api": {
                    "changes": {self.source_path: "M"},
                }
            },
            "source_blobs": {
                self.source_path: self.source_blob,
            },
        }

        self.current = copy.deepcopy(self.previous)
        self.current["approval_id"] = "TEST-NEW-APPROVAL"
        self.current["release_commit"] = self.release

        self.archive = (
            renewal.PREFIX
            + "approval-history/TEST-OLD-APPROVAL.json"
        )

        self.signature_root = (
            renewal.PREFIX
            + "signed-releases/"
            + self.release
        )

        self.candidate = {
            "schema_version": 1,
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
            "candidate_commit": self.current["candidate_commit"],
            "feature": self.current["feature"],
            "components": self.current["components"],
        }

        self.previous_ledger = {
            "schema_version": 1,
            "approved_scopes": [self.previous],
        }

        self.current_ledger = {
            "schema_version": 1,
            "approved_scopes": [self.current],
        }

        self.scope = hashlib.sha256(
            renewal.canonical(self.current)
        ).hexdigest()

        self.documents = {
            (self.base, renewal.LEDGER): self.previous_ledger,
            (self.target, renewal.LEDGER): self.current_ledger,
            (self.checkpoint, renewal.LEDGER): self.current_ledger,
            (self.target, self.archive): copy.deepcopy(self.previous),
            (
                self.release,
                renewal.PREFIX + "json-feature-scope-candidate.json",
            ): self.candidate,
        }

        for component in ("api", "frontend"):

            payload = {
                "schema_version": 1,
                "repository": "NPSZ12/INSYT_SAAS",
                "component": component,
                "release_commit": self.release,
                "policy_commit": self.checkpoint,
                "scope_sha256": self.scope,
                "artifact_sha256": "2" * 64,
            }

            signature = self.private.sign(
                b"INSYT-RELEASE-APPROVAL-V1\n"
                + renewal.canonical(payload)
            )

            self.documents[
                (
                    self.target,
                    self.signature_root + "/" + component + ".json",
                )
            ] = {
                "payload": payload,
                "signature": base64.b64encode(signature).decode(),
            }

        self.deltas = {
            (self.previous_release, self.release): {},
            (self.base, self.checkpoint): {
                renewal.LEDGER: "M",
            },
            (self.base, self.target): {
                renewal.LEDGER: "M",
                self.archive: "A",
                self.signature_root + "/api.json": "A",
                self.signature_root + "/frontend.json": "A",
            },
        }

        self.ancestry = {
            (self.base, self.target),
            (self.previous_release, self.release),
            (self.base, self.checkpoint),
            (self.checkpoint, self.target),
        }

        self.actual_blob = self.source_blob
        self.proposed_public = self.public

    def read_document(self, commit, path):
        return self.documents[(commit, path)]

    def check_ancestor(self, base, target):

        if (base, target) not in self.ancestry:
            raise renewal.RenewalDenied(
                "STOP: Untrusted policy ancestry"
            )

    def git(self, *args):

        if args == ("show", self.base + ":" + renewal.PUBLIC):
            return self.public

        if args == ("show", self.target + ":" + renewal.PUBLIC):
            return self.proposed_public

        raise AssertionError("Unexpected Git operation")

    def validate(self):

        with (
            patch.object(
                renewal, "read_json",
                side_effect=self.read_document,
            ),
            patch.object(
                renewal, "changed",
                side_effect=lambda a, b: self.deltas[(a, b)],
            ),
            patch.object(
                renewal, "ancestor",
                side_effect=self.check_ancestor,
            ),
            patch.object(
                renewal, "revision",
                return_value=self.actual_blob,
            ),
            patch.object(
                renewal, "git",
                side_effect=self.git,
            ),
            patch.object(
                renewal, "TRUSTED_KEY",
                hashlib.sha256(self.public).hexdigest(),
            ),
        ):
            renewal.validate_renewal(
                self.base,
                self.target,
                self.release,
            )

    def denied(self):
        with self.assertRaises(renewal.RenewalDenied):
            self.validate()

    def envelope(self, component="api"):
        return self.documents[
            (
                self.target,
                self.signature_root + "/" + component + ".json",
            )
        ]

    def test_valid_future_release(self):
        self.validate()

    def test_untrusted_policy_ancestry(self):
        self.ancestry.remove((self.base, self.target))
        self.denied()

    def test_untrusted_checkpoint_ancestry(self):
        self.ancestry.remove((self.base, self.checkpoint))
        self.denied()

    def test_unauthorized_application_change(self):
        self.deltas[
            (self.previous_release, self.release)
        ] = {"backend/app/unauthorized.py": "M"}
        self.denied()

    def test_approved_source_blob_changed(self):
        self.actual_blob = "3" * 40
        self.denied()

    def test_approval_scope_changed(self):
        self.current["feature"] = "unapproved-feature"
        self.denied()

    def test_duplicate_active_approvals(self):
        self.current_ledger["approved_scopes"].append(
            copy.deepcopy(self.current)
        )
        self.denied()

    def test_historical_approval_modified(self):
        self.documents[
            (self.target, self.archive)
        ]["approval_id"] = "ALTERED"
        self.denied()

    def test_historical_signature_modified(self):
        self.deltas[(self.base, self.target)][
            renewal.PREFIX
            + "signed-releases/"
            + self.previous_release
            + "/api.json"
        ] = "M"
        self.denied()

    def test_invalid_signature(self):
        self.envelope()["signature"] = base64.b64encode(
            b"\0" * 64
        ).decode()
        self.denied()

    def test_wrong_component(self):
        self.envelope()["payload"]["component"] = "frontend"
        self.denied()

    def test_wrong_release(self):
        self.envelope()["payload"]["release_commit"] = "4" * 40
        self.denied()

    def test_artifact_digest_tampering(self):
        self.envelope()["payload"]["artifact_sha256"] = "5" * 64
        self.denied()

    def test_signing_key_changed(self):
        self.proposed_public = b"untrusted-public-key"
        self.denied()

    def test_protected_baseline_modified(self):
        self.deltas[(self.base, self.target)][
            renewal.PREFIX + "production-baseline.json"
        ] = "M"
        self.denied()

    def test_validator_self_modification(self):
        self.deltas[(self.base, self.target)][
            "tools/insyt_policy_renewal.py"
        ] = "M"
        self.denied()

    def test_unexpected_policy_file(self):
        self.deltas[(self.base, self.target)][
            renewal.PREFIX + "unexpected.json"
        ] = "A"
        self.denied()

    def test_checkpoint_contains_extra_changes(self):
        self.deltas[(self.base, self.checkpoint)][
            renewal.PUBLIC
        ] = "M"
        self.denied()


if __name__ == "__main__":
    unittest.main()
