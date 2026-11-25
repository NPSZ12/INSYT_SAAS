"""INSYT deployment artifact integrity.

Computes an exact digest of packaged directory contents.
This is an integrity primitive, NOT deployment authorization.

The expected digest must ultimately come from a verified,
independently signed release approval.
"""

import argparse
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

DOMAIN = b"INSYT-DEPLOYMENT-ARTIFACT-V1\n"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactDenied(Exception):
    pass


def deny(message):
    raise ArtifactDenied("STOP: " + message)


def fingerprint_directory(location):
    root = Path(location)

    if root.is_symlink():
        deny("Package root is a symbolic link")

    if not root.is_dir():
        deny("Package directory does not exist")

    entries = []
    seen = set()

    for path in root.rglob("*"):
        if path.is_symlink():
            deny("Package contains symbolic link")

        if path.is_dir():
            continue

        if not path.is_file():
            deny("Package contains unsupported file type")

        relative = path.relative_to(root).as_posix()

        if (
            not relative
            or relative.startswith("/")
            or "\\" in relative
            or ".." in relative.split("/")
        ):
            deny("Unsafe packaged path")

        folded = relative.casefold()

        if folded in seen:
            deny("Case-colliding packaged path")

        seen.add(folded)

        checksum = hashlib.sha256()
        size = 0

        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)

                if not chunk:
                    break

                checksum.update(chunk)
                size += len(chunk)

        entries.append({
            "path": relative,
            "size": size,
            "sha256": checksum.hexdigest(),
        })

    if not entries:
        deny("Package is empty")

    entries.sort(key=lambda item: item["path"])

    canonical = json.dumps(
        entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")

    digest = hashlib.sha256(DOMAIN + canonical).hexdigest()

    return {
        "algorithm": "INSYT-DEPLOYMENT-ARTIFACT-V1",
        "sha256": digest,
        "file_count": len(entries),
    }


def verify_directory(location, expected_sha256):
    if (
        not isinstance(expected_sha256, str)
        or not SHA256.fullmatch(expected_sha256)
    ):
        deny("Invalid approved artifact digest")

    actual = fingerprint_directory(location)

    if not hmac.compare_digest(
        actual["sha256"],
        expected_sha256,
    ):
        deny("Packaged artifact differs from approved digest")

    return actual


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "operation",
        choices=("digest", "verify"),
    )
    parser.add_argument("--path", required=True)
    parser.add_argument("--expected-sha256")

    args = parser.parse_args()

    if args.operation == "digest":
        if args.expected_sha256 is not None:
            deny("Digest operation does not accept approval")

        result = fingerprint_directory(args.path)

        print(json.dumps(result, sort_keys=True))
        print("INTEGRITY ONLY — NO RELEASE AUTHORIZATION")

    else:
        if args.expected_sha256 is None:
            deny("Approved artifact digest is required")

        result = verify_directory(
            args.path,
            args.expected_sha256,
        )

        print("PASS: Packaged artifact matches supplied digest")
        print("FILES:", result["file_count"])
        print("SHA256:", result["sha256"])
        print("DIGEST MATCH ONLY — NO RELEASE AUTHORIZATION")


if __name__ == "__main__":
    try:
        main()
    except ArtifactDenied as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
