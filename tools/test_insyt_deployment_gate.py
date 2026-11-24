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

    def test_api_original_steps_preserved(self):
        original = git_original(API)
        current = working(API)

        authorization = (
            "  authorize:\n"
            "    runs-on: ubuntu-latest\n"
            "    permissions:\n"
            "      contents: read\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "        with:\n"
            "          persist-credentials: false\n"
            "      - name: INSYT production release authorization\n"
            "        run: python3 tools/insyt_deployment_gate.py "
            "--component api --sha ${{ github.sha }}\n"
            "\n"
        )

        self.assertEqual(current.count(authorization), 1)
        self.assertEqual(
            current.count("    needs: [build, authorize]\n"),
            1,
        )

        restored = current.replace(authorization, "", 1)
        restored = restored.replace(
            "    needs: [build, authorize]\n",
            "    needs: build\n",
            1,
        )

        self.assertEqual(restored, original)

    def test_frontend_original_steps_preserved(self):
        original = git_original(FRONT)
        current = working(FRONT)

        addition = (
            "      - name: INSYT production release authorization\n"
            "        run: python3 tools/insyt_deployment_gate.py "
            "--component frontend --sha ${{ github.sha }}\n"
        )

        self.assertEqual(current.count(addition), 1)

        self.assertLess(
            current.index(addition),
            current.index("      - name: Set up Node"),
        )

        self.assertEqual(
            current.replace(addition, "", 1),
            original,
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


if __name__ == "__main__":
    unittest.main()
