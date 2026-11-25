#!/usr/bin/env python3
"""INSYT production source protection.

Fail closed when a proposed release changes the verified
production baseline. No automatic approvals or bypass flags.

An authorization mechanism must be added separately,
reviewed, and protected by repository rules before releases
with changes can pass.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BASELINE = (
    REPO
    / ".github"
    / "insyt-release"
    / "production-baseline.json"
)

EXPECTED_BASELINE_CANONICAL_SHA256 = (
    "8ab81e0c26ce33f444d751451943c86dcb6112b45b9c9416660ecf386b30af49"
)

REQUIRED_WORKFLOWS = (
    ".github/workflows/main_insyt-api-prod-v2.yml",
    ".github/workflows/main_insyt-app-prod.yml",
    ".github/workflows/main_insyt-apc-worker-prod-v2.yml",
    ".github/workflows/insyt-detection-worker-v2-release.yml",
)

def fail(message):
    print("STOP:", message, file=sys.stderr)
    raise SystemExit(2)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        fail(
            "Git operation failed: "
            + " ".join(args)
            + " "
            + result.stderr.decode("utf-8", "replace")[:500]
        )
    return result.stdout


def load_baseline():
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        fail("Protected baseline unreadable: " + str(exc))

    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    actual = hashlib.sha256(canonical).hexdigest()

    if actual != EXPECTED_BASELINE_CANONICAL_SHA256:
        fail("Protected production baseline canonical SHA256 changed.")

    if data.get("schema_version") != 1:
        fail("Unexpected baseline schema.")

    expected = {
        "api": "32481b715ddd3d951b5de91592df00a3c8bd854e",
        "frontend": "5a7dd0339baf0579e303b032fdcd31f79f764102",
    }

    for component, commit in expected.items():
        entry = data.get(component, {})

        if entry.get("verified_deployment_commit") != commit:
            fail(f"{component} baseline commit mismatch.")

        if not entry.get("tracked_files"):
            fail(f"{component} baseline inventory empty.")

        # Validate the snapshot against the actual Git history.
        listing = git(
            "ls-tree", "-r", "-z", commit,
            "--",
            "backend" if component == "api" else "frontend",
            ".github/workflows",
            ".github/scripts",
        )

        actual_files = {}

        for record in listing.split(b"\0"):
            if not record:
                continue

            metadata, pathname = record.split(b"\t", 1)
            mode, kind, sha = metadata.decode().split()

            actual_files[pathname.decode()] = {
                "git_blob_sha": sha,
                "mode": mode,
                "type": kind,
            }

        if actual_files != entry["tracked_files"]:
            fail(f"{component} inventory does not match Git history.")

    return data


def changes_since(commit, paths):
    raw = git(
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        commit,
        "--",
        *paths,
    )

    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()

    if len(tokens) % 2:
        fail("Unexpected Git diff output.")

    changes = []

    for i in range(0, len(tokens), 2):
        status = tokens[i].decode("utf-8", "replace")
        path = tokens[i + 1].decode("utf-8", "replace")

        changes.append((status, path))

    return changes


def validate_candidate_transition(observed):
    """Validate proposed source boundaries, not authorization."""

    manifest = json.loads(
        (
            REPO / ".github/insyt-release/"
            "json-feature-scope-candidate.json"
        ).read_text(encoding="utf-8-sig")
    )

    validator = REPO / "tools/insyt_feature_scope_check.py"

    result = subprocess.run(
        [
            sys.executable,
            str(validator),
            "--manifest",
            str(
                REPO / ".github/insyt-release/"
                "json-feature-scope-candidate.json"
            ),
        ],
        cwd=REPO,
    )

    if result.returncode:
        fail("Candidate feature scope rejected")

    expected = {}

    for component in ("api", "frontend"):
        for path, status in (
            manifest["components"][component]["changes"].items()
        ):
            expected[(component, path)] = status

    workflows = {
        ".github/workflows/insyt-release-validation.yml": "A",
        ".github/workflows/insyt-release-packages.yml": "A",
        ".github/workflows/main_insyt-api-prod-v2.yml": "M",
        ".github/workflows/main_insyt-app-prod.yml": "M",
    }

    for component in ("api", "frontend"):
        for path, status in workflows.items():
            expected[(component, path)] = status

    # Local pre-commit validation must also account for
    # the explicitly proposed new package workflow.
    untracked = git(
        "ls-files", "--others", "--exclude-standard"
    ).decode("utf-8").splitlines()

    for path in untracked:
        if path.startswith((
            "backend/", "frontend/",
            ".github/workflows/", ".github/scripts/",
        )):
            if path != ".github/workflows/insyt-release-packages.yml":
                fail("Unexpected untracked candidate source: " + path)

            for component in ("api", "frontend"):
                observed[(component, path)] = "A"

    if observed != expected:
        print("Unexpected or missing baseline differences:")

        for key in sorted(set(observed) | set(expected)):
            if observed.get(key) != expected.get(key):
                print(
                    key,
                    "expected:", expected.get(key),
                    "observed:", observed.get(key),
                )

        fail("Candidate baseline transition differs from scope")

    # Application source must remain exactly as committed.
    if git("diff", "HEAD", "--", "backend", "frontend").strip():
        fail("Uncommitted application changes detected")

    for path in workflows:
        if not (REPO / path).is_file():
            fail("Expected candidate workflow missing: " + path)

    print("PASS: Exact candidate application scope")
    print("PASS: Exact candidate workflow transition scope")
    print("PASS: Original production baseline retained")
    print("CANDIDATE VALIDATION ONLY - NOT DEPLOYMENT AUTHORIZATION")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate-candidate",
        action="store_true",
    )
    args = parser.parse_args()

    data = load_baseline()
    print("PASS: Production baseline integrity verified.")

    for path in REQUIRED_WORKFLOWS:
        if not (REPO / path).is_file():
            fail(f"Existing hardened workflow missing: {path}")

    print("PASS: Required existing workflows still present.")

    observed = {}

    scopes = (
        (
            "api",
            ["backend", ".github/workflows", ".github/scripts"],
        ),
        (
            "frontend",
            ["frontend", ".github/workflows", ".github/scripts"],
        ),
    )

    for component, paths in scopes:
        commit = data[component]["verified_deployment_commit"]

        for status, path in changes_since(commit, paths):
            observed[(component, path)] = status

    print(
        "Changed baseline entries requiring review:",
        len(observed),
    )

    for (component, path), status in sorted(observed.items()):
        print(f"  {component:8} {status:3} {path}")

    deletions = [
        (component, path)
        for (component, path), status in observed.items()
        if status.startswith("D")
    ]

    if deletions:
        fail(
            "Protected files deleted. "
            "Restoration or independently authorized review required."
        )

    if args.validate_candidate:
        validate_candidate_transition(observed)
        return

    if observed:
        fail(
            "Release contains unapproved baseline differences. "
            "No automatic change approval is installed."
        )

    print("PASS: Proposed release matches protected baselines.")
    print("PASS: No protected source changes or deletions.")


if __name__ == "__main__":
    main()
