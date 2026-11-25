"""INSYT proposed feature-change boundary checker.

This validates source scope only. It never grants release approval.

Usage:
 python tools/insyt_feature_scope_check.py --manifest PATH

The authoritative approval source must be independently protected;
a candidate-branch manifest is not authorization.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROTECTED = (
    "backend/app/api/auth.py",
    "backend/app/services/security.py",
    "backend/app/main.py",
    "backend/app/database/connection.py",
    "backend/app/database/init_db.py",
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")


def stop(message):
    raise ValueError("STOP: " + message)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stop(
            "Git operation failed: "
            + result.stderr.strip()[:300]
        )

    return result.stdout.strip()


def validate(manifest):
    if manifest.get("schema_version") != 1:
        stop("Unsupported scope schema")

    if manifest.get("feature") != "cyber2-native-json":
        stop("Unexpected feature")

    if manifest.get("status") != "PENDING_REVIEW_NOT_APPROVED":
        stop("Candidate manifest claims unauthorized approval")

    if manifest.get("production_deployment_authorized") is not False:
        stop("Candidate manifest must not authorize deployment")

    candidate = manifest.get("candidate_commit", "")

    if not SHA40.fullmatch(candidate):
        stop("Invalid candidate commit SHA")

    # Bind the proposed JSON scope to the immutable release
    # checkpoint, not to the changing validation-tool commit.
    git("cat-file", "-e", candidate + "^{commit}")

    # The release must be an ancestor of the checkout.
    git("merge-base", "--is-ancestor", candidate, "HEAD")

    # The immutable JSON release has one verified follow-up
    # repair: two qualified Python imports in the JSON router.
    # No other post-release application changes are permitted.
    repair_path = "backend/app/api/cyber2/json_mapped_preview.py"

    subsequent = git(
        "diff",
        "--name-only",
        "--no-renames",
        candidate,
        "HEAD",
        "--",
        "backend/",
        "frontend/",
    )

    if subsequent.splitlines() != [repair_path]:
        stop(
            "Application changes exceed exact JSON repair: "
            + repr(subsequent)
        )

    def committed_bytes(revision, file_path):
        result = subprocess.run(
            ["git", "show", revision + ":" + file_path],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        if result.returncode:
            stop("Cannot verify committed source: " + file_path)

        return result.stdout

    original = committed_bytes(candidate, repair_path)
    actual = committed_bytes("HEAD", repair_path)

    expected = original

    repairs = (
        (
            b"from json_header_evidence import",
            b"from app.api.cyber2.json_header_evidence import",
        ),
        (
            b"from json_duplicate_headers import",
            b"from app.api.cyber2.json_duplicate_headers import",
        ),
    )

    for before, after in repairs:
        if expected.count(before) != 1:
            stop("Expected JSON import missing or duplicated")

        expected = expected.replace(before, after, 1)

    if actual != expected:
        stop("JSON source differs beyond the two import repairs")

    print("PASS: Only two exact JSON import repairs permitted")

    components = manifest.get("components")

    if not isinstance(components, dict):
        stop("Missing component scopes")

    if set(components) != {"api", "frontend"}:
        stop("Unexpected or missing component scope")

    roots = {
        "api": "backend/",
        "frontend": "frontend/",
    }

    all_paths = set()

    for component in ("api", "frontend"):
        scope = components[component]
        baseline = scope.get("baseline", "")
        root = scope.get("root")
        changes = scope.get("changes")

        if not SHA40.fullmatch(baseline):
            stop("Invalid baseline for " + component)

        if root != roots[component]:
            stop("Component root mismatch: " + component)

        if not isinstance(changes, dict):
            stop("Missing exact file changes: " + component)

        for path, status in changes.items():
            if not isinstance(path, str):
                stop("Invalid source path")

            if not path.startswith(root):
                stop("Out-of-component source path: " + path)

            if ".." in Path(path).parts or "\\" in path:
                stop("Unsafe source path: " + path)

            if path in all_paths:
                stop("Duplicate source path: " + path)

            if status not in ("A", "M"):
                stop("Unapproved change type for " + path)

            all_paths.add(path)

        # Compare the COMPLETE component tree, not just the
        # declared paths. This detects any additional change.
        output = git(
            "diff",
            "--name-status",
            "--no-renames",
            baseline,
            candidate,
            "--",
            root,
        )

        actual = {}

        for line in output.splitlines():
            parts = line.split("\t")

            if len(parts) != 2:
                stop("Unexpected Git change format: " + line)

            status, path = parts

            if path in actual:
                stop("Duplicate Git change: " + path)

            actual[path] = status

        missing = sorted(set(changes) - set(actual))
        unexpected = sorted(set(actual) - set(changes))

        if missing:
            stop(
                component + " required changes missing: "
                + ", ".join(missing)
            )

        if unexpected:
            stop(
                component + " out-of-scope changes: "
                + ", ".join(unexpected)
            )

        for path in changes:
            if actual[path] != changes[path]:
                stop(
                    "Source change type mismatch: " + path
                    + " expected " + changes[path]
                    + " actual " + actual[path]
                )

        # Explicitly verify security and shared startup files
        # against the component's own production baseline.
        if component == "api":
            for path in PROTECTED:
                old = git(
                    "rev-parse",
                    baseline + ":" + path,
                )

                new = git(
                    "rev-parse",
                    candidate + ":" + path,
                )

                if old != new:
                    stop(
                        "Protected authentication/startup source "
                        "changed: " + path
                    )

            print(
                "PASS: Authentication and shared API startup "
                "source unchanged"
            )

        print(
            f"PASS: {component} exact change boundary "
            f"({len(actual)} files)"
        )

    print("PASS: No unrelated application source changes")
    print("SCOPE MATCH ONLY — NOT RELEASE APPROVAL")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    path = Path(args.manifest)

    if not path.is_file():
        stop("Scope manifest not found")

    manifest = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    validate(manifest)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
