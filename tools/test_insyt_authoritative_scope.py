"""INSYT independent feature-scope authorization tests."""

import copy
import unittest

from insyt_authoritative_scope import PolicyDenied, verify


class AuthoritativeScopeTests(unittest.TestCase):

    def setUp(self):
        commit = "a" * 40

        self.candidate = {
            "schema_version": 1,
            "feature": "cyber2-native-json",
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
            "candidate_commit": commit,
            "components": {
                "api": {
                    "baseline": "b" * 40,
                    "root": "backend/",
                    "changes": {
                        "backend/app/api/cyber2/json_mapped_preview.py": "M"
                    },
                }
            },
        }

        self.blobs = {
            "backend/app/api/cyber2/json_mapped_preview.py": "c" * 40
        }

        self.approval = {
            "approval_id": "TEST-APPROVAL-001",
            "approval_status": "APPROVED",
            "feature": "cyber2-native-json",
            "candidate_commit": commit,
            "components": copy.deepcopy(self.candidate["components"]),
            "source_blobs": copy.deepcopy(self.blobs),
        }

    def test_matching_authoritative_scope_passes(self):
        self.assertTrue(
            verify(self.candidate, self.approval, self.blobs)
        )

    def test_unapproved_policy_rejected(self):
        approval = copy.deepcopy(self.approval)
        approval["approval_status"] = "PENDING"

        with self.assertRaises(PolicyDenied):
            verify(self.candidate, approval, self.blobs)

    def test_unapproved_auth_change_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["components"]["api"]["changes"] = {
            "backend/app/api/auth.py": "M"
        }

        with self.assertRaises(PolicyDenied):
            verify(candidate, self.approval, self.blobs)

    def test_changed_blob_rejected(self):
        blobs = copy.deepcopy(self.blobs)
        path = next(iter(blobs))
        blobs[path] = "d" * 40

        with self.assertRaises(PolicyDenied):
            verify(self.candidate, self.approval, blobs)

    def test_different_commit_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["candidate_commit"] = "e" * 40

        with self.assertRaises(PolicyDenied):
            verify(candidate, self.approval, self.blobs)

    def test_candidate_self_approval_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["production_deployment_authorized"] = True

        with self.assertRaises(PolicyDenied):
            verify(candidate, self.approval, self.blobs)

    def test_changed_approved_components_rejected(self):
        approval = copy.deepcopy(self.approval)
        approval["components"]["api"]["changes"] = {
            "backend/app/api/auth.py": "M"
        }

        with self.assertRaises(PolicyDenied):
            verify(self.candidate, approval, self.blobs)

    def test_missing_approval_id_rejected(self):
        approval = copy.deepcopy(self.approval)
        approval["approval_id"] = ""

        with self.assertRaises(PolicyDenied):
            verify(self.candidate, approval, self.blobs)


if __name__ == "__main__":
    unittest.main()
