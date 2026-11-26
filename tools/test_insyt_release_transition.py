"""Permanent reusable release transition security regressions."""

import copy
import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import insyt_release_transition as transition

from insyt_release_transition import (
    TransitionDenied,
    inspect_transition,
    verify_transition,
    validate_path,
)


class ReleasePathTests(unittest.TestCase):

    def test_ordinary_api_change(self):
        self.assertEqual(
            validate_path("backend/app/services/example.py", "M"),
            "api",
        )

    def test_ordinary_frontend_addition(self):
        self.assertEqual(
            validate_path("frontend/src/components/Example.tsx", "A"),
            "frontend",
        )

    def test_protected_paths_rejected(self):
        paths = [
            "backend/app/api/auth.py",
            "backend/app/services/security.py",
            "backend/app/main.py",
            "backend/app/database/connection.py",
            "backend/app/database/init_db.py",
            "frontend/src/app/login/page.tsx",
            "frontend/src/app/mfa/setup/page.tsx",
            "frontend/src/app/auth/entra/callback/page.tsx",
        ]

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(TransitionDenied):
                    validate_path(path, "M")

    def test_dependency_changes_rejected(self):
        paths = [
            "backend/requirements.txt",
            "backend/requirements-dev.txt",
            "backend/pyproject.toml",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/next.config.ts",
            "frontend/.npmrc",
        ]

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(TransitionDenied):
                    validate_path(path, "M")

    def test_worker_changes_rejected(self):
        with self.assertRaises(TransitionDenied):
            validate_path(
                "workers/insyt_detection_worker_v2/worker.py",
                "M",
            )

    def test_workflow_changes_rejected(self):
        with self.assertRaises(TransitionDenied):
            validate_path(
                ".github/workflows/deploy.yml",
                "M",
            )

    def test_policy_changes_rejected(self):
        with self.assertRaises(TransitionDenied):
            validate_path(
                ".github/insyt-release/approved-feature-scopes.json",
                "M",
            )

    def test_release_gate_changes_rejected(self):
        with self.assertRaises(TransitionDenied):
            validate_path(
                "tools/insyt_deployment_gate.py",
                "M",
            )

    def test_unsafe_paths_rejected(self):
        paths = [
            "/backend/example.py",
            "backend/../example.py",
            "backend//example.py",
            "backend/./example.py",
            "backend\\example.py",
        ]

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(TransitionDenied):
                    validate_path(path, "A")

    def test_unsupported_change_types_rejected(self):
        for status in ("D", "T", "R100", "C100"):
            with self.subTest(status=status):
                with self.assertRaises(TransitionDenied):
                    validate_path(
                        "backend/app/example.py",
                        status,
                    )


class RealGitTransitionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.root_patch = patch.object(
            transition, "ROOT", self.root
        )

        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")

        self.write(
            "backend/app/example.py",
            "VALUE = 1\n",
        )

        self.baseline = self.commit("Synthetic baseline")

    def git(self, *args):
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            check=True,
        )

        return result.stdout.decode().strip()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def valid_candidate(self):
        self.write(
            "backend/app/example.py",
            "VALUE = 2\n",
        )

        self.write(
            "frontend/src/components/Example.tsx",
            "export const value = 2;\n",
        )

        return self.commit("Application upgrade")

    def test_exact_real_git_inventory(self):
        candidate = self.valid_candidate()

        result = inspect_transition(
            self.baseline, candidate
        )

        self.assertEqual(
            result["components"]["api"]["changes"],
            {"backend/app/example.py": "M"},
        )

        self.assertEqual(
            result["components"]["frontend"]["changes"],
            {"frontend/src/components/Example.tsx": "A"},
        )

        self.assertEqual(len(result["source_blobs"]), 2)

        self.assertEqual(
            verify_transition(
                self.baseline, candidate, result
            ),
            result,
        )

    def test_missing_approved_file_rejected(self):
        candidate = self.valid_candidate()

        proposed = inspect_transition(
            self.baseline, candidate
        )

        proposed["source_blobs"].pop(
            "backend/app/example.py"
        )

        with self.assertRaises(TransitionDenied):
            verify_transition(
                self.baseline, candidate, proposed
            )

    def test_changed_blob_rejected(self):
        candidate = self.valid_candidate()

        proposed = inspect_transition(
            self.baseline, candidate
        )

        proposed["source_blobs"][
            "backend/app/example.py"
        ] = "a" * 40

        with self.assertRaises(TransitionDenied):
            verify_transition(
                self.baseline, candidate, proposed
            )

    def test_protected_git_change_rejected(self):
        self.write(
            "backend/app/api/auth.py",
            "SYNTHETIC = True\n",
        )

        candidate = self.commit("Protected change")

        with self.assertRaises(TransitionDenied):
            inspect_transition(
                self.baseline, candidate
            )

    def test_deleted_file_rejected(self):
        (self.root / "backend/app/example.py").unlink()

        candidate = self.commit("Deleted source")

        with self.assertRaises(TransitionDenied):
            inspect_transition(
                self.baseline, candidate
            )

    def test_executable_source_rejected(self):
        self.git(
            "update-index",
            "--chmod=+x",
            "backend/app/example.py",
        )

        self.git("commit", "-qm", "Changed source mode")

        candidate = self.git("rev-parse", "HEAD")

        with self.assertRaises(TransitionDenied):
            inspect_transition(
                self.baseline, candidate
            )

    def test_identical_baseline_rejected(self):
        with self.assertRaises(TransitionDenied):
            inspect_transition(
                self.baseline, self.baseline
            )

    def test_nonancestor_baseline_rejected(self):
        first = self.valid_candidate()

        self.git("checkout", "-q", "--detach", self.baseline)

        self.write(
            "backend/app/example.py",
            "VALUE = 3\n",
        )

        second = self.commit("Divergent candidate")

        with self.assertRaises(TransitionDenied):
            inspect_transition(first, second)

    def test_invented_scope_rejected(self):
        candidate = self.valid_candidate()

        proposed = copy.deepcopy(
            inspect_transition(self.baseline, candidate)
        )

        proposed["components"]["api"]["changes"][
            "backend/app/invented.py"
        ] = "A"

        with self.assertRaises(TransitionDenied):
            verify_transition(
                self.baseline, candidate, proposed
            )


if __name__ == "__main__":
    unittest.main()
