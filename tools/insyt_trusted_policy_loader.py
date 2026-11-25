"""Retrieve an exact, externally selected INSYT policy revision.

This module verifies source identity only. It does not decide
which policy commit is trusted, approve changes, or deploy.
"""

import argparse
import json
import re
import subprocess
import sys

SHA40 = re.compile(r"^[0-9a-f]{40}$")

REPOSITORY = "https://github.com/NPSZ12/INSYT_SAAS.git"
BRANCH = "refs/heads/policy/insyt-hardened"

POLICY_FILE = (
    ".github/insyt-release/approved-feature-scopes.json"
)


class PolicySourceDenied(Exception):
    pass


def deny(message):
    raise PolicySourceDenied("STOP: " + message)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )

    if result.returncode:
        deny("Git operation failed: " + result.stderr.strip()[:300])

    return result.stdout.strip()


def check_policy_identity(expected, actual):
    if not isinstance(expected, str) or not SHA40.fullmatch(expected):
        deny("Invalid trusted policy SHA")

    if not isinstance(actual, str) or actual != expected:
        deny("Live policy revision differs from trusted identity")

    return True


def read_live_policy(expected, run_git=git):
    """Fetch only the expected live policy revision.

    The caller must supply expected from a trusted source.
    Candidate-controlled values are not authorization.
    """

    if not isinstance(expected, str) or not SHA40.fullmatch(expected):
        deny("Trusted policy SHA missing or malformed")

    origin = run_git("remote", "get-url", "origin")

    if origin != REPOSITORY:
        deny("Unexpected Git remote origin")

    remote = run_git(
        "ls-remote",
        "--heads",
        "origin",
        BRANCH,
    )

    lines = remote.splitlines()

    if len(lines) != 1:
        deny("Policy branch missing or ambiguous")

    parts = lines[0].split()

    if len(parts) != 2 or parts[1] != BRANCH:
        deny("Unexpected policy reference")

    check_policy_identity(expected, parts[0])

    # This updates Git's fetch metadata/object store, never the
    # checked-out source tree or remote repository.
    run_git(
        "fetch",
        "--no-tags",
        "origin",
        BRANCH,
    )

    actual = run_git("rev-parse", "FETCH_HEAD")
    check_policy_identity(expected, actual)

    try:
        content = run_git(
            "show",
            expected + ":" + POLICY_FILE,
        )
    except PolicySourceDenied:
        deny("Trusted policy has no approved-scope record")

    try:
        policy = json.loads(content)
    except (ValueError, TypeError):
        deny("Trusted policy content is invalid JSON")

    if not isinstance(policy, dict):
        deny("Trusted policy must be an object")

    if policy.get("schema_version") != 1:
        deny("Unsupported trusted policy schema")

    if not isinstance(policy.get("approved_scopes"), list):
        deny("Trusted policy approval history missing")

    return policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trusted-policy-sha", required=True)
    args = parser.parse_args()

    read_live_policy(args.trusted_policy_sha)

    print("PASS: Live policy matches pinned trusted revision")
    print("POLICY SOURCE VERIFIED — NO RELEASE AUTHORIZATION")


if __name__ == "__main__":
    try:
        main()
    except PolicySourceDenied as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
