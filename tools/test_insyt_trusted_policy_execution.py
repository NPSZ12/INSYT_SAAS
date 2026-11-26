"""Trusted policy dependency execution regressions."""

import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import insyt_policy_publication_ci as publication


class TrustedPolicyExecutionTests(unittest.TestCase):

    def setUp(self):

        self.base = "a" * 40
        self.target = "b" * 40
        self.release = "c" * 40

        self.modules = {
            "insyt_release_transition.py": b"""
ROOT = None
TRUSTED = True
""",
            "insyt_protected_source.py": b"""
from insyt_release_transition import TRUSTED
""",
            "insyt_new_scope_validation.py": b"""
from insyt_protected_source import TRUSTED
""",
            "insyt_policy_renewal.py": b"""
from insyt_new_scope_validation import TRUSTED
from insyt_release_transition import ROOT as initial_root

ROOT = None

def validate_renewal(base, target, release):
    from pathlib import Path
    import insyt_release_transition as transition

    if TRUSTED is not True:
        raise RuntimeError("Untrusted dependency")

    if not isinstance(ROOT, Path):
        raise RuntimeError("Repository root missing")

    if transition.ROOT != ROOT:
        raise RuntimeError("Repository roots differ")

    if (base, target, release) != (
        "a" * 40, "b" * 40, "c" * 40
    ):
        raise RuntimeError("Commit identities differ")
""",
        }

        self.proposed = dict(self.modules)
        self.requests = []

    def git(self, *args):

        self.requests.append(args)

        if len(args) != 2 or args[0] != "show":
            raise AssertionError("Unexpected Git operation")

        commit, path = args[1].split(":", 1)

        if not path.startswith("tools/"):
            raise AssertionError("Unexpected module path")

        name = path.removeprefix("tools/")

        if commit == self.base:
            source = self.modules
        elif commit == self.target:
            source = self.proposed
        else:
            raise AssertionError("Unexpected policy commit")

        if name not in source:
            raise SystemExit("STOP: Trusted module missing")

        return source[name]

    def validate(self):

        with patch.object(
            publication,
            "git",
            side_effect=self.git,
        ):

            publication.validate_installed_renewal(
                self.base,
                self.target,
                self.release,
            )

    def test_real_isolated_execution(self):

        self.validate()

        self.assertEqual(len(self.requests), 8)

    def test_all_dependencies_read_from_protected_base(self):

        self.validate()

        for name in self.modules:

            self.assertIn(
                ("show", self.base + ":tools/" + name),
                self.requests,
            )

    def test_each_modified_dependency_rejected(self):

        for name in self.modules:

            with self.subTest(module=name):

                self.proposed = dict(self.modules)

                self.proposed[name] += b"\nTAMPERED = True\n"

                with self.assertRaisesRegex(
                    SystemExit,
                    "Trusted validator modification prohibited",
                ):
                    self.validate()

    def test_missing_trusted_dependency_rejected(self):

        self.modules.pop(
            "insyt_protected_source.py"
        )

        with self.assertRaises(SystemExit):
            self.validate()

    def test_missing_proposed_dependency_rejected(self):

        self.proposed.pop(
            "insyt_new_scope_validation.py"
        )

        with self.assertRaises(SystemExit):
            self.validate()

    def test_pythonpath_shadowing_rejected(self):

        with tempfile.TemporaryDirectory() as folder:

            shadow = Path(folder)

            for name in self.modules:

                (shadow / name).write_text(
                    'raise RuntimeError("Shadow module executed")',
                    encoding="utf-8",
                )

            with patch.dict(
                os.environ,
                {"PYTHONPATH": str(shadow)},
            ):
                self.validate()

    def test_trusted_validator_failure_blocks_publication(self):

        self.modules["insyt_policy_renewal.py"] = b"""
ROOT = None

def validate_renewal(base, target, release):
    raise RuntimeError("Intentional synthetic denial")
"""

        self.proposed = dict(self.modules)

        with self.assertRaisesRegex(
            SystemExit,
            "Trusted policy validation failed",
        ):
            self.validate()


if __name__ == "__main__":
    unittest.main()
