"""Complete deployment inventory verification against real Git history."""

import copy
import json
import unittest

from unittest.mock import patch

import insyt_deployment_gate as gate
import insyt_release_transition as transition
import test_insyt_release_transition as fixtures

from insyt_release_transition import TransitionDenied


class CompleteDeploymentScopeTests(unittest.TestCase):

    def setUp(self):

        self.fixture = fixtures.RealGitTransitionTests(
            "test_exact_real_git_inventory"
        )

        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

        f = self.fixture

        self.manifest = (
            ".github/insyt-release/"
            "json-feature-scope-candidate.json"
        )

        f.write(self.manifest, '{"previous": true}\n')

        self.baseline = f.commit("Existing release manifest")

        self.checkpoint = f.valid_candidate()

        self.evidence = transition.inspect_transition(
            self.baseline,
            self.checkpoint,
        )

        self.candidate = {
            "schema_version": 1,
            "feature": "synthetic-upgrade",
            "candidate_commit": self.checkpoint,
            "status": "PENDING_REVIEW_NOT_APPROVED",
            "production_deployment_authorized": False,
            "components": copy.deepcopy(
                self.evidence["components"]
            ),
        }

        self.blobs = copy.deepcopy(
            self.evidence["source_blobs"]
        )

        f.write(
            self.manifest,
            json.dumps(self.candidate),
        )

        self.release = f.commit("Final release manifest")

        replacement = patch.object(
            gate,
            "git",
            side_effect=lambda *args:
                transition.git(*args).decode().strip(),
        )

        replacement.start()
        self.addCleanup(replacement.stop)

    def verify(self):

        return gate.verify_complete_release_scope(
            self.candidate,
            self.release,
            self.blobs,
        )

    def denied(self):

        with self.assertRaises(
            (RuntimeError, TransitionDenied)
        ):
            self.verify()

    def test_exact_complete_release_accepted(self):

        self.assertTrue(self.verify())

    def test_unlisted_application_change_rejected(self):

        self.fixture.write(
            "backend/app/unapproved.py",
            "UNAPPROVED = True\n",
        )

        self.release = self.fixture.commit(
            "Unauthorized application change"
        )

        self.denied()

    def test_unlisted_workflow_change_rejected(self):

        self.fixture.write(
            ".github/workflows/unapproved.yml",
            "name: Synthetic\n",
        )

        self.release = self.fixture.commit(
            "Unauthorized workflow change"
        )

        self.denied()

    def test_unlisted_security_change_rejected(self):

        self.fixture.write(
            "tools/insyt_deployment_gate.py",
            "SYNTHETIC = True\n",
        )

        self.release = self.fixture.commit(
            "Unauthorized security change"
        )

        self.denied()

    def test_modified_approved_source_rejected(self):

        self.fixture.write(
            "backend/app/example.py",
            "VALUE = 999\n",
        )

        self.release = self.fixture.commit(
            "Modified approved source"
        )

        self.denied()

    def test_missing_approved_blob_rejected(self):

        self.blobs.pop("backend/app/example.py")

        self.denied()

    def test_incorrect_approved_blob_rejected(self):

        self.blobs["backend/app/example.py"] = "f" * 40

        self.denied()

    def test_invented_scope_path_rejected(self):

        self.candidate["components"]["api"]["changes"][
            "backend/app/invented.py"
        ] = "A"

        self.denied()

    def test_inconsistent_component_baselines_rejected(self):

        self.candidate["components"]["frontend"][
            "baseline"
        ] = self.checkpoint

        self.denied()

    def test_missing_final_manifest_transition_rejected(self):

        self.release = self.checkpoint

        self.denied()

    def test_unrelated_release_ancestry_rejected(self):

        self.release = self.baseline

        self.denied()


if __name__ == "__main__":
    unittest.main()
