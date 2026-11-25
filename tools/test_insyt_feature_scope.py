"""Permanent INSYT JSON feature-isolation regression tests."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MANIFEST = (
    ROOT
    / ".github/insyt-release/json-feature-scope-candidate.json"
)

VALIDATOR = ROOT / "tools/insyt_feature_scope_check.py"


class FeatureIsolationTests(unittest.TestCase):

    def setUp(self):
        self.manifest = json.loads(
            MANIFEST.read_text(encoding="utf-8-sig")
        )

    def run_validator(self, manifest):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            return subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(VALIDATOR),
                    "--manifest",
                    str(path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

    def test_exact_json_scope_passes(self):
        result = self.run_validator(self.manifest)

        self.assertEqual(
            result.returncode, 0,
            result.stderr,
        )

        self.assertIn(
            "SCOPE MATCH ONLY",
            result.stdout,
        )

    def test_auth_change_rejected_with_same_file_count(self):
        altered = copy.deepcopy(self.manifest)
        changes = altered["components"]["api"]["changes"]

        # Replace an approved file rather than adding a file.
        # The number of proposed files stays exactly the same.
        del changes[
            "backend/app/api/cyber2/json_duplicate_headers.py"
        ]

        changes["backend/app/api/auth.py"] = "M"

        self.assertEqual(len(changes), 13)

        result = self.run_validator(altered)

        self.assertEqual(result.returncode, 2)
        self.assertIn("STOP:", result.stderr)

    def test_unrelated_frontend_file_rejected(self):
        altered = copy.deepcopy(self.manifest)

        altered["components"]["frontend"]["changes"] = {
            "frontend/src/app/login/page.tsx": "M"
        }

        result = self.run_validator(altered)

        self.assertEqual(result.returncode, 2)
        self.assertIn("STOP:", result.stderr)

    def test_candidate_cannot_approve_own_deployment(self):
        altered = copy.deepcopy(self.manifest)
        altered["production_deployment_authorized"] = True

        result = self.run_validator(altered)

        self.assertEqual(result.returncode, 2)
        self.assertIn("STOP:", result.stderr)

    def test_candidate_cannot_claim_policy_approval(self):
        altered = copy.deepcopy(self.manifest)
        altered["status"] = "APPROVED"

        result = self.run_validator(altered)

        self.assertEqual(result.returncode, 2)
        self.assertIn("STOP:", result.stderr)

    def test_missing_approved_json_file_rejected(self):
        altered = copy.deepcopy(self.manifest)

        del altered["components"]["api"]["changes"][
            "backend/app/api/cyber2/json_duplicate_headers.py"
        ]

        result = self.run_validator(altered)

        self.assertEqual(result.returncode, 2)
        self.assertIn("STOP:", result.stderr)


if __name__ == "__main__":
    unittest.main()
