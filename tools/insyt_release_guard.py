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


def validate_policy_foundation():
    """Validate initial policy proposal; never authorize deployment."""

    foundation = "65ec1a3aaa632bb7c04a814a81c494b68cd963e7"
    reviewed = "1959711970f4cc5c1f9a819443fecc1019a030c7"

    git("merge-base", "--is-ancestor", foundation, "HEAD")
    git("merge-base", "--is-ancestor", reviewed, "HEAD")

    expected = {
        ".github/insyt-release/approved-feature-scopes.json": "A",
        ".github/insyt-release/hardened-history.json": "A",
        ".github/insyt-release/release-signing-public.pem": "A",
        "tools/insyt_release_guard.py": "M",
        ".github/workflows/insyt-release-validation.yml": "M",
    }

    observed = dict(
        (path, status)
        for status, path in changes_since(foundation, [])
    )

    if observed != expected:
        fail("Policy proposal exceeds reviewed foundation scope")

    if git(
        "ls-files", "--others", "--exclude-standard"
    ).strip():
        fail("Unexpected untracked policy files")

    for path, status in expected.items():
        if status != "A":
            continue

        actual = (REPO / path).read_bytes()
        original = git("show", reviewed + ":" + path)

        if actual.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
            fail("Previously reviewed policy content changed: " + path)

    key = (
        REPO / ".github/insyt-release/release-signing-public.pem"
    ).read_text(encoding="utf-8").strip() + "\n"

    if hashlib.sha256(key.encode("utf-8")).hexdigest() != (
        "1a226fb6274f9ee7269c8929ffafbe3a39ff9ffdddcdee30f9292c3cbd677300"
    ):
        fail("Policy signing identity changed")

    ledger = json.loads(
        (
            REPO / ".github/insyt-release/"
            "approved-feature-scopes.json"
        ).read_text(encoding="utf-8-sig")
    )

    records = ledger.get("approved_scopes", [])

    if ledger.get("schema_version") != 1 or len(records) != 1:
        fail("Unexpected policy approval inventory")

    approval = records[0]

    if approval.get("approval_id") != "INSYT-JSON-BB736295B00F":
        fail("Previously reviewed approval identity changed")

    if approval.get("approval_status") != "APPROVED":
        fail("Reviewed source approval unavailable")

    if approval.get("release_commit") != (
        "bb736295b00f3b8a783845442cb44cd2223b0a7c"
    ):
        fail("Previous release authorization unexpectedly changed")

    if len(approval.get("source_blobs", {})) != 14:
        fail("Reviewed source inventory changed")

    print("PASS: Exact policy foundation transition")
    print("PASS: Reviewed approval ledger unchanged")
    print("PASS: Original hardened history unchanged")
    print("PASS: Trusted signing identity unchanged")
    print("POLICY FOUNDATION VALIDATED - NO DEPLOYMENT AUTHORIZATION")



def validate_release_approval():
    """Validate this reviewed policy transition only."""

    base = "b0f5eda2e658a68a8fa8ad6ca76f22c222c20dc0"
    release = "039d5a740525e94e846023f74c34ed19e70dcd16"

    ledger_path = ".github/insyt-release/approved-feature-scopes.json"

    history_path = (
        ".github/insyt-release/approval-history/"
        "INSYT-JSON-BB736295B00F.json"
    )

    git("merge-base", "--is-ancestor", base, "HEAD")

    expected = {
        ledger_path: "M",
        history_path: "A",
        "tools/insyt_release_guard.py": "M",
    }

    observed = {
        path: status
        for status, path in changes_since(base, [])
    }

    if observed != expected:
        fail("Unexpected release approval transition")

    if git("ls-files", "--others", "--exclude-standard").strip():
        fail("Unexpected untracked files")

    old = json.loads(git("show", base + ":" + ledger_path))

    current = json.loads(
        (REPO / ledger_path).read_text(encoding="utf-8-sig")
    )

    archived = json.loads(
        (REPO / history_path).read_text(encoding="utf-8-sig")
    )

    if len(old["approved_scopes"]) != 1:
        fail("Unexpected previous approval inventory")

    previous = old["approved_scopes"][0]

    if archived != previous:
        fail("Historical approval changed")

    previous["approval_id"] = "INSYT-JSON-039D5A740525"
    previous["release_commit"] = release

    if current != old:
        fail("Unexpected approval ledger changes")

    canonical = json.dumps(
        current["approved_scopes"][0],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")

    if hashlib.sha256(canonical).hexdigest() != (
        "51fd0e3136dbfd61f5d572080b75876657a48ad8d037ec094355ffb3a92c285e"
    ):
        fail("Approved scope digest differs")

    for path, expected_blob in previous["source_blobs"].items():
        actual = git(
            "rev-parse", release + ":" + path
        ).decode().strip()

        if actual != expected_blob:
            fail("Approved source identity differs: " + path)

    print("PASS: Historical approval preserved")
    print("PASS: Exact reviewed release approval")
    print("PASS: All approved source hashes verified")
    print("POLICY VALIDATION ONLY - NOT DEPLOYMENT AUTHORIZATION")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate-policy-foundation",
        action="store_true",
    )
    args = parser.parse_args()

    data = load_baseline()
    print("PASS: Production baseline integrity verified.")

    for path in REQUIRED_WORKFLOWS:
        if not (REPO / path).is_file():
            fail(f"Existing hardened workflow missing: {path}")

    print("PASS: Required existing workflows still present.")

    if args.validate_policy_foundation:
        approved_foundation = "b0f5eda2e658a68a8fa8ad6ca76f22c222c20dc0"

        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor",
             approved_foundation, "HEAD"],
            cwd=REPO,
        )

        if result.returncode == 0:
            validate_release_approval()
        elif result.returncode == 1:
            validate_policy_foundation()
        else:
            fail("Unable to establish policy ancestry")

        return

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

    if observed:
        fail(
            "Release contains unapproved baseline differences. "
            "No automatic change approval is installed."
        )

    print("PASS: Proposed release matches protected baselines.")
    print("PASS: No protected source changes or deletions.")


if __name__ == "__main__":
    main()
