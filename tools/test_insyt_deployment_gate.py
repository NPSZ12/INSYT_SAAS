"""Protect INSYT production deployment gate structure.

Run with:
python -m unittest discover -s tools -p test_insyt_deployment_gate.py -v
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BASE = "728c2e17848d53f88ce7336f61ccac94ad68a1bd"

API = ".github/workflows/main_insyt-api-prod-v2.yml"
FRONT = ".github/workflows/main_insyt-app-prod.yml"

GATE = ROOT / "tools/insyt_deployment_gate.py"


def git_original(path):
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"],
        cwd=ROOT,
    ).decode("utf-8-sig").replace("\r\n", "\n")


def working(path):
    return (
        (ROOT / path)
        .read_text(encoding="utf-8-sig")
        .replace("\r\n", "\n")
    )


class DeploymentGateRegression(unittest.TestCase):

    def parse_workflow(self, source):
        import yaml
        return yaml.load(source, Loader=yaml.BaseLoader)

    def assert_retained_workflow(self, path, component, destination):
        current = self.parse_workflow(working(path))
        original = self.parse_workflow(git_original(path))

        self.assertEqual(set(current["on"]), {"workflow_dispatch"})
        self.assertEqual(set(current["jobs"]), {"deploy"})

        inputs = current["on"]["workflow_dispatch"]["inputs"]

        self.assertEqual(set(inputs), {"package_run_id"})
        self.assertEqual(inputs["package_run_id"]["required"], "true")
        self.assertEqual(inputs["package_run_id"]["type"], "string")

        deploy = current["jobs"]["deploy"]
        original_deploy = original["jobs"]["deploy"]

        self.assertEqual(
            deploy["runs-on"], original_deploy["runs-on"]
        )
        self.assertNotIn("needs", deploy)

        steps = deploy["steps"]
        prefix = [
            "Checkout exact release verification source",
            "Set up release-verification Python",
            "Install release-verification dependency",
            "Validate package preparation run",
            "Download exact retained artifact",
            "Verify signed archive and extract authorized package",
        ]

        self.assertEqual(
            [step["name"] for step in steps[:6]], prefix
        )

        self.assertEqual(
            steps[0],
            {
                "name": prefix[0],
                "uses": "actions/checkout@v4",
                "with": {
                    "ref": "${{ github.sha }}",
                    "persist-credentials": "false",
                    "fetch-depth": "0",
                },
            },
        )

        self.assertEqual(
            steps[1],
            {
                "name": prefix[1],
                "uses": "actions/setup-python@v5",
                "with": {"python-version": "3.12"},
            },
        )

        self.assertEqual(
            steps[2],
            {
                "name": prefix[2],
                "run": "python -m pip install cryptography==46.0.3",
            },
        )

        command = (
            "python tools/insyt_deployment_gate.py"
            " --component " + component
            + ' --sha "$GITHUB_SHA"'
            + ' --package-run-id "$INSYT_PACKAGE_RUN_ID"'
        )

        token_env = {
            "GITHUB_TOKEN": "${{ github.token }}",
            "INSYT_PACKAGE_RUN_ID": "${{ inputs.package_run_id }}",
        }

        self.assertEqual(
            steps[3],
            {
                "name": prefix[3],
                "env": token_env,
                "run": command + " --verify-package-run-only",
            },
        )

        self.assertEqual(
            steps[4],
            {
                "name": prefix[4],
                "uses": "actions/download-artifact@v4",
                "with": {
                    "name":
                        "insyt-" + component + "-${{ github.sha }}",
                    "path": "retained_artifact",
                    "github-token": "${{ github.token }}",
                    "repository": "${{ github.repository }}",
                    "run-id": "${{ inputs.package_run_id }}",
                },
            },
        )

        self.assertEqual(
            steps[5],
            {
                "name": prefix[5],
                "env": token_env,
                "run": (
                    command
                    + " --artifact-directory retained_artifact"
                    + " --extract-to " + destination
                ),
            },
        )

        # Restore only the authorized release-integration
        # differences, then compare to the protected baseline.
        import copy

        restored = copy.deepcopy(current)
        restored_deploy = restored["jobs"]["deploy"]

        restored["on"] = original["on"]

        if component == "api":
            self.assertEqual(len(steps), 8)

            publishers = copy.deepcopy(steps[6:])

            self.assertEqual(
                publishers[1]["with"]["package"],
                "./insyt_api_package",
            )

            publishers[1]["with"]["package"] = "."

            original_publishers = [
                step for step in original_deploy["steps"]
                if step.get("name") in (
                    "Login to Azure",
                    "Deploy to Azure Web App",
                )
            ]

            self.assertEqual(publishers, original_publishers)

            self.assertEqual(
                restored_deploy["permissions"].pop("actions"),
                "read",
            )

            restored_deploy["needs"] = original_deploy["needs"]
            restored["jobs"]["build"] = original["jobs"]["build"]

        else:
            self.assertEqual(len(steps), 7)

            original_publishers = [
                step for step in original_deploy["steps"]
                if step.get("name")
                == "Deploy cleanly to the existing INSYT Azure App Service"
            ]

            self.assertEqual(steps[6:], original_publishers)

            self.assertEqual(
                restored_deploy.pop("permissions"),
                {"contents": "read", "actions": "read"},
            )

        restored_deploy["steps"] = original_deploy["steps"]

        self.assertEqual(restored, original)

    def test_api_original_steps_preserved(self):
        self.assert_retained_workflow(
            API, "api", "insyt_api_package"
        )

    def test_frontend_original_steps_preserved(self):
        self.assert_retained_workflow(
            FRONT, "frontend", "frontend_release_package"
        )

    def run_gate(self, component, overrides=None):
        sha = "a" * 40

        env = dict(os.environ)
        env.update({
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "NPSZ12/INSYT_SAAS",
            "GITHUB_REF":
                "refs/heads/release/json-promotion-20261119",
            "GITHUB_SHA": sha,
        })

        if overrides:
            env.update(overrides)

        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(GATE),
                "--component",
                component,
                "--sha",
                sha,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_api_denied_without_approval(self):
        result = self.run_gate("api")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Production deployment denied", result.stderr)

    def test_frontend_denied_without_approval(self):
        result = self.run_gate("frontend")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Production deployment denied", result.stderr)

    def test_wrong_branch_rejected(self):
        result = self.run_gate(
            "api",
            {"GITHUB_REF": "refs/heads/main"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unauthorized deployment branch", result.stderr)

    def test_wrong_commit_rejected(self):
        result = self.run_gate(
            "api",
            {"GITHUB_SHA": "b" * 40},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match", result.stderr)

    def test_wrong_repository_rejected(self):
        result = self.run_gate(
            "frontend",
            {"GITHUB_REPOSITORY": "untrusted/repository"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unexpected GitHub repository", result.stderr)


class PolicyPublicationRegression(unittest.TestCase):

    APPROVED = "a" * 40
    PUBLISHED = "b" * 40

    def setUp(self):
        from unittest.mock import patch
        import insyt_deployment_gate as gate

        self.gate = gate
        self.envelope = {
            "payload": {
                "policy_commit": self.APPROVED,
            }
        }

        self.comparison = {
            "status": "ahead",
            "behind_by": 0,
            "ahead_by": 1,
            "base_commit": {"sha": self.APPROVED},
            "merge_base_commit": {"sha": self.APPROVED},
        }

        api = patch.object(
            gate,
            "github_json",
            return_value=self.comparison,
        )

        files = patch.object(
            gate,
            "read_policy_file",
            side_effect=lambda sha, path: "unchanged:" + path,
        )

        self.api = api.start()
        self.files = files.start()

        self.addCleanup(api.stop)
        self.addCleanup(files.stop)

    def verify(self):
        return self.gate.verify_approval_policy_revision(
            self.PUBLISHED,
            self.envelope,
        )

    def test_signed_policy_ancestor_accepted(self):
        self.assertEqual(self.verify(), self.APPROVED)

        self.api.assert_called_once_with(
            "compare/" + self.APPROVED
            + "..." + self.PUBLISHED
        )

    def test_same_policy_revision_accepted(self):
        result = self.gate.verify_approval_policy_revision(
            self.APPROVED,
            self.envelope,
        )

        self.assertEqual(result, self.APPROVED)
        self.api.assert_not_called()

    def test_divergent_policy_rejected(self):
        self.comparison["status"] = "diverged"

        with self.assertRaises(RuntimeError):
            self.verify()

    def test_nonancestor_policy_rejected(self):
        self.comparison["merge_base_commit"] = {
            "sha": "c" * 40
        }

        with self.assertRaises(RuntimeError):
            self.verify()

    def test_modified_approval_ledger_rejected(self):
        def changed(sha, path):
            if (
                sha == self.PUBLISHED
                and path.endswith("approved-feature-scopes.json")
            ):
                return "modified"

            return "unchanged"

        self.files.side_effect = changed

        with self.assertRaises(RuntimeError):
            self.verify()

    def test_modified_signing_key_rejected(self):
        def changed(sha, path):
            if (
                sha == self.PUBLISHED
                and path.endswith("release-signing-public.pem")
            ):
                return "modified"

            return "unchanged"

        self.files.side_effect = changed

        with self.assertRaises(RuntimeError):
            self.verify()

    def test_malformed_policy_revision_rejected(self):
        self.envelope["payload"]["policy_commit"] = "invalid"

        with self.assertRaises(RuntimeError):
            self.verify()

        self.api.assert_not_called()

    def test_missing_policy_revision_rejected(self):
        del self.envelope["payload"]["policy_commit"]

        with self.assertRaises(RuntimeError):
            self.verify()

    def test_policy_history_unavailable_rejected(self):
        self.api.side_effect = OSError("Unavailable")

        with self.assertRaises(OSError):
            self.verify()


class AuthorizedExtractionRegression(unittest.TestCase):

    def setUp(self):
        import tempfile
        import tarfile
        import io

        from insyt_artifact_integrity import fingerprint_directory

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.retained = self.root / "retained"
        self.retained.mkdir()

        self.archive = self.retained / "api.tar"
        self.destination = self.root / "deployed"

        with tarfile.open(self.archive, "w") as archive:
            data = b"approved INSYT content"
            member = tarfile.TarInfo("approved.txt")
            member.size = len(data)
            member.mode = 0o644

            archive.addfile(member, io.BytesIO(data))

        self.evidence = {
            "evidence_verified": True,
            "component": "api",
            "artifact_sha256": fingerprint_directory(
                self.retained
            )["sha256"],
        }

    def extract(self):
        from insyt_deployment_gate import extract_authorized_artifact

        return extract_authorized_artifact(
            self.retained,
            self.destination,
            "api",
            self.evidence,
        )

    def test_signed_archive_extracts(self):
        result = self.extract()

        self.assertEqual(result["file_count"], 1)

        self.assertEqual(
            (self.destination / "approved.txt").read_bytes(),
            b"approved INSYT content",
        )

    def test_unverified_evidence_denied(self):
        self.evidence["evidence_verified"] = False

        with self.assertRaises(RuntimeError):
            self.extract()

        self.assertFalse(self.destination.exists())

    def test_wrong_component_denied(self):
        self.evidence["component"] = "frontend"

        with self.assertRaises(RuntimeError):
            self.extract()

        self.assertFalse(self.destination.exists())

    def test_modified_archive_denied(self):
        from insyt_artifact_integrity import ArtifactDenied

        with self.archive.open("ab") as stream:
            stream.write(b"unauthorized modification")

        with self.assertRaises(ArtifactDenied):
            self.extract()

        self.assertFalse(self.destination.exists())

    def test_extra_retained_file_denied(self):
        (self.retained / "unexpected.txt").write_bytes(b"extra")

        with self.assertRaises(RuntimeError):
            self.extract()

        self.assertFalse(self.destination.exists())

    def test_wrong_signed_digest_denied(self):
        from insyt_artifact_integrity import ArtifactDenied

        self.evidence["artifact_sha256"] = "a" * 64

        with self.assertRaises(ArtifactDenied):
            self.extract()

        self.assertFalse(self.destination.exists())


class PackageProvenanceRegression(unittest.TestCase):

    def setUp(self):
        from unittest.mock import patch
        import insyt_deployment_gate as gate

        self.gate = gate
        self.sha = "a" * 40

        self.run = {
            "id": 123,
            "head_sha": self.sha,
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "path": ".github/workflows/insyt-release-packages.yml",
            "head_repository": {
                "full_name": "NPSZ12/INSYT_SAAS",
            },
        }

        mock = patch.object(
            gate, "github_json", return_value=self.run
        )

        self.api = mock.start()
        self.addCleanup(mock.stop)

    def verify(self):
        return self.gate.verify_package_run("123", self.sha)

    def test_exact_successful_run_accepted(self):
        self.assertTrue(self.verify())
        self.api.assert_called_once_with("actions/runs/123")

    def test_wrong_commit_rejected(self):
        self.run["head_sha"] = "b" * 40
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_wrong_workflow_rejected(self):
        self.run["path"] = ".github/workflows/other.yml"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_failed_run_rejected(self):
        self.run["conclusion"] = "failure"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_incomplete_run_rejected(self):
        self.run["status"] = "in_progress"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_wrong_repository_rejected(self):
        self.run["head_repository"]["full_name"] = "other/repo"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(RuntimeError):
            self.gate.verify_package_run("../123", self.sha)

        self.api.assert_not_called()

    def test_wrong_run_id_rejected(self):
        self.run["id"] = 456
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
