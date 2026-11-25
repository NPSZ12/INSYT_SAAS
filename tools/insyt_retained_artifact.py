"""Safely extract an independently authorized INSYT release archive.

This utility verifies archive identity and extraction safety.
It does not grant production deployment authorization.
The production deployment gate must pass before extraction.
"""

import argparse
import hashlib
import hmac
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path


SHA256 = re.compile(r"^[0-9a-f]{64}$")

MAX_MEMBERS = 250_000
MAX_EXPANDED_BYTES = 20 * 1024**3


class RetainedArtifactDenied(Exception):
    pass


def deny(message):
    raise RetainedArtifactDenied("STOP: " + message)


def archive_sha256(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def safe_member_path(name):
    if not isinstance(name, str):
        deny("Invalid archive member name")

    if (
        name.startswith("/")
        or "\\" in name
        or ":" in name
        or "\x00" in name
    ):
        deny("Unsafe archive member path")

    parts = []

    for part in name.split("/"):
        if part in ("", "."):
            continue

        if part == "..":
            deny("Archive path traversal")

        if part.endswith((" ", ".")):
            deny("Ambiguous archive member path")

        if any(ord(char) < 32 for char in part):
            deny("Control character in archive path")

        if part.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *("COM" + str(i) for i in range(1, 10)),
            *("LPT" + str(i) for i in range(1, 10)),
        }:
            deny("Reserved archive path")

        parts.append(part)

    return "/".join(parts)


def validate_members(archive):
    members = []
    inventory = {}
    folded_paths = {}
    total_bytes = 0
    root_seen = False

    for member in archive:
        if len(members) >= MAX_MEMBERS:
            deny("Archive member limit exceeded")

        relative = safe_member_path(member.name)

        if not relative:
            if not member.isdir() or root_seen:
                deny("Invalid archive root entry")
            root_seen = True
            continue

        if not (member.isfile() or member.isdir()):
            deny("Unsupported archive member type")

        if member.issparse():
            deny("Sparse archive member rejected")

        if member.mode & 0o7000:
            deny("Unsafe special permission bits")

        if relative in inventory:
            deny("Duplicate archive member")

        # Check every path prefix for case collisions.
        parts = relative.split("/")

        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            folded = prefix.casefold()

            previous = folded_paths.get(folded)

            if previous is not None and previous != prefix:
                deny("Case-colliding archive path")

            folded_paths[folded] = prefix

        if member.size < 0:
            deny("Invalid archive member size")

        if member.isdir() and member.size != 0:
            deny("Invalid directory size")

        total_bytes += member.size

        if total_bytes > MAX_EXPANDED_BYTES:
            deny("Expanded archive size limit exceeded")

        inventory[relative] = (
            "directory" if member.isdir() else "file"
        )

        members.append((member, relative))

    for relative in inventory:
        parts = relative.split("/")

        for length in range(1, len(parts)):
            parent = "/".join(parts[:length])

            if inventory.get(parent) == "file":
                deny("Archive file-directory conflict")

    if not any(
        member.isfile() for member, _ in members
    ):
        deny("Archive contains no files")

    return members


def extract_verified_archive(
    archive_path,
    destination,
    expected_sha256,
):
    archive_path = Path(archive_path)
    destination = Path(destination)

    if (
        not isinstance(expected_sha256, str)
        or not SHA256.fullmatch(expected_sha256)
    ):
        deny("Invalid expected archive digest")

    if (
        archive_path.is_symlink()
        or not archive_path.is_file()
    ):
        deny("Retained archive missing or unsafe")

    if destination.exists() or destination.is_symlink():
        deny("Extraction destination already exists")

    parent = destination.parent.resolve()

    if not parent.is_dir():
        deny("Extraction parent directory missing")

    staging = Path(tempfile.mkdtemp(
        prefix=".insyt-extract-",
        dir=parent,
    ))

    try:
        # Use a private copy so the verified bytes are the
        # same bytes inspected and extracted.
        retained = staging / "verified.tar"
        shutil.copyfile(archive_path, retained)

        actual_sha256 = archive_sha256(retained)

        if not hmac.compare_digest(
            actual_sha256,
            expected_sha256,
        ):
            deny("Retained archive digest mismatch")

        output = staging / "package"
        output.mkdir(mode=0o700)

        with tarfile.open(retained, mode="r:") as archive:
            members = validate_members(archive)
            directories = []

            for member, relative in members:
                target = output.joinpath(
                    *relative.split("/")
                )

                if member.isdir():
                    target.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    directories.append((target, member))
                    continue

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                stream = archive.extractfile(member)

                if stream is None:
                    deny("Archive file contents unavailable")

                with stream, target.open("xb") as result:
                    shutil.copyfileobj(
                        stream, result, 1024 * 1024
                    )

                if target.stat().st_size != member.size:
                    deny("Extracted file size mismatch")

                target.chmod(member.mode & 0o777)

            # Restore directory modes after writing files.
            for target, member in sorted(
                directories,
                key=lambda item: len(item[0].parts),
                reverse=True,
            ):
                target.chmod(member.mode & 0o777)

        if destination.exists() or destination.is_symlink():
            deny("Extraction destination changed")

        output.rename(destination)

        return {
            "archive_sha256": actual_sha256,
            "file_count": sum(
                member.isfile()
                for member, _ in members
            ),
        }

    except (
        tarfile.TarError,
        OSError,
        EOFError,
        ValueError,
    ) as exc:
        deny("Archive extraction failed: " + type(exc).__name__)

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--expected-sha256", required=True)

    args = parser.parse_args()

    result = extract_verified_archive(
        args.archive,
        args.destination,
        args.expected_sha256,
    )

    print("PASS: Exact retained archive verified")
    print("PASS: Safe archive extraction completed")
    print("FILES:", result["file_count"])
    print("SHA256:", result["archive_sha256"])
    print("EXTRACTION ONLY - NOT DEPLOYMENT AUTHORIZATION")


if __name__ == "__main__":
    try:
        main()
    except RetainedArtifactDenied as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
