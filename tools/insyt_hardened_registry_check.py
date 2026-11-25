#!/usr/bin/env python3
"""INSYT Hardened Registry integrity check.

This is a source-integrity check, not a substitute for
independent registry authorization or functional tests.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".github/insyt-release/hardened-registry.json"

def stop(message):
    print("STOP:", message, file=sys.stderr)
    raise SystemExit(2)

def git(*args):
    p = subprocess.run(
        ["git", *args], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if p.returncode:
        stop("Git verification failed.")
    return p.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=CANONICAL)
    parser.add_argument(
        "--validate-candidate",
        action="store_true",
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.registry.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        stop("Registry unreadable or invalid: " + str(exc))

    if data.get("schema_version") != 1:
        stop("Unknown registry schema.")

    if data.get("registry_state") != (
        "provisional_not_yet_enforced_in_production"
    ):
        stop("Unexpected registry state.")

    policy = data.get("policy", {})
    required_policies = (
        "automatic_hardening",
        "automatic_baseline_replacement",
        "automatic_test_removal",
    )

    if any(policy.get(name) is not False for name in required_policies):
        stop("Automatic hardening or baseline rewriting enabled.")

    required_true = (
        "protected_deletion_requires_explicit_approval",
        "registry_changes_require_independent_review",
        "production_verification_required_for_promotion",
    )

    if any(policy.get(name) is not True for name in required_true):
        stop("Required hardening safeguards disabled.")

    records = data.get("protected_source")
    if not isinstance(records, list) or len(records) != 9:
        stop("Protected source inventory missing or incomplete.")

    names = set()
    paths = set()

    for record in records:
        name = record.get("id")
        path = record.get("path")
        blob = record.get("git_blob_sha")
        reference = record.get("reference_commit")

        if not all(isinstance(x, str) and x for x in (
            name, path, blob, reference
        )):
            stop("Invalid source record.")

        if name in names or path in paths:
            stop("Duplicate protected source record.")

        names.add(name)
        paths.add(path)

        if record.get("protection") != "source_integrity":
            stop("Source protection disabled.")

        if record.get("verification") != (
            "source_only_not_full_runtime_attestation"
        ):
            stop("Incorrect source verification claim.")

        # A proposed release must retain each protected
        # source blob, not merely its filename.
        head_blob = git("rev-parse", f"HEAD:{path}").decode().strip()
        reference_blob = git(
            "rev-parse", f"{reference}:{path}"
        ).decode().strip()

        if blob != reference_blob:
            stop("Historical protected source changed: " + path)

        proposed_workflow_transition = (
            args.validate_candidate
            and path in {
                ".github/workflows/main_insyt-api-prod-v2.yml",
                ".github/workflows/main_insyt-app-prod.yml",
            }
        )

        if not proposed_workflow_transition:
            if blob != head_blob:
                stop("Protected source changed: " + path)

        # Verify working-tree content without confusing
        # Windows CRLF conversion with source changes.
        work_file = ROOT / path
        if not work_file.is_file():
            stop("Protected file missing: " + path)

        working = work_file.read_bytes().replace(b"\r\n", b"\n")
        committed = git("show", f"HEAD:{path}").replace(
            b"\r\n", b"\n"
        )

        if working != committed and not proposed_workflow_transition:
            stop("Protected working-tree file changed: " + path)

    features = data.get("features")
    if not isinstance(features, list) or not features:
        stop("Feature registry missing.")

    ids = set()
    for feature in features:
        fid = feature.get("id")
        if not isinstance(fid, str) or not fid or fid in ids:
            stop("Invalid or duplicate feature identifier.")

        ids.add(fid)

        status = feature.get("status")
        if status not in ("candidate", "hardened"):
            stop("Invalid feature state.")

        tests = feature.get("required_test_files")
        behaviors = feature.get("protected_behaviors")

        if not isinstance(tests, list) or not tests:
            stop("Feature missing required regression tests.")

        if not isinstance(behaviors, list) or not behaviors:
            stop("Feature missing protected behaviors.")

        for path in tests:
            if not isinstance(path, str) or not (ROOT / path).is_file():
                stop("Feature test missing: " + str(path))

        if status == "hardened":
            if feature.get("production_verified") is not True:
                stop("Unverified feature marked hardened.")

            if not feature.get("promoted_release"):
                stop("Hardened feature lacks release evidence.")

        elif feature.get("production_verified") is True:
            stop("Candidate improperly marked production-verified.")

    if "INSYT-CYBER2-JSON" not in ids:
        stop("JSON candidate record missing.")

    if args.validate_candidate:
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "unittest",
                "discover", "-s", "tools",
                "-p", "test_insyt_deployment_gate.py", "-v",
            ],
            cwd=ROOT,
        )

        if result.returncode:
            stop("Protected workflow transition regressions failed")

        print("PASS: Proposed workflow transitions validated")
        print("CANDIDATE VALIDATION ONLY - NOT AUTHORIZATION")

    print("PASS: Historical protected source hashes match Git.")
    print("PASS: Registry policy is fail-closed.")
    print("PASS: All declared test files exist.")
    print("PASS: JSON is a candidate, not falsely hardened.")
    print("NOTE: External trusted approval is not yet enforced.")

if __name__ == "__main__":
    main()
