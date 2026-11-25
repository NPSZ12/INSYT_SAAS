"""Permanent regression tests for retained INSYT artifacts."""

import io
import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from insyt_retained_artifact import (
    RetainedArtifactDenied,
    archive_sha256,
    extract_verified_archive,
)


class RetainedArtifactTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.archive = self.root / "package.tar"
        self.destination = self.root / "extracted"

    def make_archive(self, entries):
        with tarfile.open(self.archive, "w") as archive:
            for name, data, kind, mode in entries:
                member = tarfile.TarInfo(name)
                member.mode = mode

                if kind == "file":
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))

                elif kind == "directory":
                    member.type = tarfile.DIRTYPE
                    archive.addfile(member)

                elif kind == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = data.decode()
                    archive.addfile(member)

                elif kind == "hardlink":
                    member.type = tarfile.LNKTYPE
                    member.linkname = data.decode()
                    archive.addfile(member)

                elif kind == "fifo":
                    member.type = tarfile.FIFOTYPE
                    archive.addfile(member)

    def file(self, name, data=b"INSYT", mode=0o644):
        return (name, data, "file", mode)

    def extract(self, expected=None):
        return extract_verified_archive(
            self.archive,
            self.destination,
            expected or archive_sha256(self.archive),
        )

    def assert_denied(self):
        with self.assertRaises(RetainedArtifactDenied):
            self.extract()

        self.assertFalse(self.destination.exists())

    def test_valid_archive_extracts(self):
        self.make_archive([
            self.file("./server.js", b"server"),
            self.file("./.next/BUILD_ID", b"release-123"),
            self.file("./public/image.png", b"image"),
        ])

        result = self.extract()

        self.assertEqual(result["file_count"], 3)

        self.assertEqual(
            (self.destination / ".next/BUILD_ID").read_bytes(),
            b"release-123",
        )

    def test_hidden_files_preserved(self):
        self.make_archive([
            self.file(".next/static/chunk.js"),
            self.file(".hidden"),
        ])

        self.extract()

        self.assertTrue(
            (self.destination / ".hidden").is_file()
        )

    @unittest.skipIf(
        os.name == "nt",
        "Linux executable permission validation required",
    )
    def test_executable_permissions_preserved(self):
        self.make_archive([
            self.file("start.sh", mode=0o755),
        ])

        self.extract()

        self.assertEqual(
            stat.S_IMODE(
                (self.destination / "start.sh").stat().st_mode
            ),
            0o755,
        )

    def test_wrong_digest_denied(self):
        self.make_archive([self.file("server.js")])

        with self.assertRaises(RetainedArtifactDenied):
            self.extract("a" * 64)

        self.assertFalse(self.destination.exists())

    def test_modified_archive_denied(self):
        self.make_archive([self.file("server.js")])
        approved = archive_sha256(self.archive)

        self.make_archive([
            self.file("server.js", b"changed"),
        ])

        with self.assertRaises(RetainedArtifactDenied):
            self.extract(approved)

        self.assertFalse(self.destination.exists())

    def test_path_traversal_denied(self):
        self.make_archive([
            self.file("../outside.txt"),
        ])

        self.assert_denied()

        self.assertFalse(
            (self.root / "outside.txt").exists()
        )

    def test_absolute_path_denied(self):
        self.make_archive([
            self.file("/outside.txt"),
        ])

        self.assert_denied()

    def test_windows_path_denied(self):
        self.make_archive([
            self.file("C:/outside.txt"),
        ])

        self.assert_denied()

    def test_backslash_path_denied(self):
        self.make_archive([
            self.file("folder\\file"),
        ])

        self.assert_denied()

    def test_symbolic_link_denied(self):
        self.make_archive([
            self.file("server.js"),
            ("link", b"../outside", "symlink", 0o777),
        ])

        self.assert_denied()

    def test_hard_link_denied(self):
        self.make_archive([
            self.file("server.js"),
            ("link", b"server.js", "hardlink", 0o644),
        ])

        self.assert_denied()

    def test_special_file_denied(self):
        self.make_archive([
            self.file("server.js"),
            ("pipe", b"", "fifo", 0o644),
        ])

        self.assert_denied()

    def test_duplicate_member_denied(self):
        self.make_archive([
            self.file("server.js"),
            self.file("./server.js"),
        ])

        self.assert_denied()

    def test_case_collision_denied(self):
        self.make_archive([
            self.file("Folder/a"),
            self.file("folder/b"),
        ])

        self.assert_denied()

    def test_file_directory_conflict_denied(self):
        self.make_archive([
            self.file("folder"),
            self.file("folder/file"),
        ])

        self.assert_denied()

    def test_special_permissions_denied(self):
        self.make_archive([
            self.file("script", mode=0o4755),
        ])

        self.assert_denied()

    def test_existing_destination_preserved(self):
        self.make_archive([
            self.file("server.js"),
        ])

        self.destination.mkdir()

        original = self.destination / "existing.txt"
        original.write_bytes(b"preserve")

        with self.assertRaises(RetainedArtifactDenied):
            self.extract()

        self.assertEqual(
            original.read_bytes(),
            b"preserve",
        )

        self.assertFalse(
            (self.destination / "server.js").exists()
        )

    def test_empty_archive_denied(self):
        self.make_archive([])
        self.assert_denied()

    def test_reserved_path_denied(self):
        self.make_archive([
            self.file("folder/CON.txt"),
        ])

        self.assert_denied()

    def test_member_limit_enforced(self):
        self.make_archive([
            self.file("one"),
            self.file("two"),
        ])

        with patch(
            "insyt_retained_artifact.MAX_MEMBERS", 1
        ):
            self.assert_denied()

    def test_expanded_size_limit_enforced(self):
        self.make_archive([
            self.file("large", b"12345"),
        ])

        with patch(
            "insyt_retained_artifact.MAX_EXPANDED_BYTES", 4
        ):
            self.assert_denied()

    def test_corrupt_archive_denied(self):
        self.archive.write_bytes(b"not a tar archive")
        self.assert_denied()


if __name__ == "__main__":
    unittest.main()
