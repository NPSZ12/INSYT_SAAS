import copy
import subprocess
import unittest

from insyt_hardened_transition import (
    TransitionDenied,
    validate_history,
)


class HardenedTransitionTests(unittest.TestCase):

    def setUp(self):
        self.path = "backend/app/api/auth.py"
        self.sha1 = "a" * 40
        self.sha2 = "b" * 40

        self.baseline = {self.path: self.sha1}

        self.previous = {
            "schema_version": 1,
            "features": {
                "authentication": {
                    "versions": [
                        {
                            "version": 1,
                            "source": {self.path: self.sha1},
                        }
                    ]
                }
            },
        }

        self.proposed = copy.deepcopy(self.previous)

    def test_identical_history_allowed(self):
        self.assertTrue(
            validate_history(
                self.baseline, self.previous, self.proposed
            )
        )

    def test_new_version_can_be_appended(self):
        self.proposed["features"]["authentication"][
            "versions"
        ].append({
            "version": 2,
            "source": {self.path: self.sha2},
        })

        self.assertTrue(
            validate_history(
                self.baseline, self.previous, self.proposed
            )
        )

    def test_new_feature_can_be_added(self):
        self.proposed["features"]["json"] = {
            "versions": [
                {
                    "version": 1,
                    "source": {"backend/json.py": self.sha2},
                }
            ]
        }

        self.assertTrue(
            validate_history(
                self.baseline, self.previous, self.proposed
            )
        )

    def test_old_feature_cannot_be_removed(self):
        self.proposed["features"] = {}

        with self.assertRaises(TransitionDenied):
            validate_history(
                self.baseline, self.previous, self.proposed
            )

    def test_old_version_cannot_be_rewritten(self):
        self.proposed["features"]["authentication"][
            "versions"
        ][0]["source"][self.path] = self.sha2

        with self.assertRaises(TransitionDenied):
            validate_history(
                self.baseline, self.previous, self.proposed
            )

    def test_old_version_cannot_be_deleted(self):
        self.previous["features"]["authentication"][
            "versions"
        ].append({
            "version": 2,
            "source": {self.path: self.sha2},
        })

        with self.assertRaises(TransitionDenied):
            validate_history(
                self.baseline, self.previous, self.proposed
            )

    def test_original_baseline_cannot_disappear(self):
        self.proposed["features"]["authentication"][
            "versions"
        ][0]["source"] = {"backend/other.py": self.sha1}

        with self.assertRaises(TransitionDenied):
            validate_history(
                self.baseline, self.previous, self.proposed
            )

    def test_unauthorized_path_or_invalid_blob_rejected(self):
        for bad_path, bad_sha in (
            ("../auth.py", self.sha1),
            ("backend/auth.py", "not-a-git-hash"),
        ):
            changed = copy.deepcopy(self.proposed)
            changed["features"]["json"] = {
                "versions": [
                    {
                        "version": 1,
                        "source": {bad_path: bad_sha},
                    }
                ]
            }

            with self.assertRaises(TransitionDenied):
                validate_history(
                    self.baseline, self.previous, changed
                )


if __name__ == "__main__":
    unittest.main()
