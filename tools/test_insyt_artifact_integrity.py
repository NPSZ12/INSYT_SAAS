"""INSYT deployment artifact integrity regression tests."""

import tempfile
import unittest
from pathlib import Path

from insyt_artifact_integrity import (
    ArtifactDenied,
    fingerprint_directory,
    verify_directory,
)


class ArtifactIntegrityTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        (self.root / "backend").mkdir()
        (self.root / "backend" / "app.py").write_bytes(
            b"synthetic-api-v1"
        )

        (self.root / "config.json").write_bytes(
            b'{"synthetic":true}'
        )

    def test_identical_artifact_passes(self):
        original = fingerprint_directory(self.root)

        verified = verify_directory(
            self.root,
            original["sha256"],
        )

        self.assertEqual(
            verified["sha256"],
            original["sha256"],
        )

    def test_modified_file_rejected(self):
        original = fingerprint_directory(self.root)

        (self.root / "backend" / "app.py").write_bytes(
            b"synthetic-api-tampered"
        )

        with self.assertRaises(ArtifactDenied):
            verify_directory(self.root, original["sha256"])

    def test_added_file_rejected(self):
        original = fingerprint_directory(self.root)

        (self.root / "unexpected.py").write_bytes(
            b"unauthorized"
        )

        with self.assertRaises(ArtifactDenied):
            verify_directory(self.root, original["sha256"])

    def test_removed_file_rejected(self):
        original = fingerprint_directory(self.root)

        (self.root / "config.json").unlink()

        with self.assertRaises(ArtifactDenied):
            verify_directory(self.root, original["sha256"])

    def test_invalid_approval_digest_rejected(self):
        with self.assertRaises(ArtifactDenied):
            verify_directory(self.root, "not-an-approved-sha")

    def test_empty_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ArtifactDenied):
                fingerprint_directory(directory)

    def test_file_order_does_not_change_digest(self):
        original = fingerprint_directory(self.root)

        with tempfile.TemporaryDirectory() as directory:
            copy_root = Path(directory)

            (copy_root / "config.json").write_bytes(
                b'{"synthetic":true}'
            )
            (copy_root / "backend").mkdir()
            (copy_root / "backend" / "app.py").write_bytes(
                b"synthetic-api-v1"
            )

            copied = fingerprint_directory(copy_root)

        self.assertEqual(
            original["sha256"],
            copied["sha256"],
        )

    def test_symlink_rejected_if_supported(self):
        target = self.root / "backend" / "app.py"
        link = self.root / "linked.py"

        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links unavailable")

        with self.assertRaises(ArtifactDenied):
            fingerprint_directory(self.root)


if __name__ == "__main__":
    unittest.main()
