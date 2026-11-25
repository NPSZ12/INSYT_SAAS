#!/usr/bin/env python3
"""INSYT production deployment gate.

Requires trusted policy, source approval, exact CI attestation,
signed finished artifact, and exact GitHub release identity.

No bypass mode, candidate-supplied public key, or automatic approval.
"""

import argparse
import shutil
import tempfile
import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from insyt_release_evidence import verify_release_evidence
from insyt_artifact_integrity import verify_directory
from insyt_retained_artifact import (
    archive_sha256,
    extract_verified_archive,
)

REPOSITORY = "NPSZ12/INSYT_SAAS"
POLICY_REF = "refs/heads/policy/insyt-hardened"
RELEASE_REF = "refs/heads/release/json-promotion-20261119"
REMOTE_URLS = {
    "https://github.com/NPSZ12/INSYT_SAAS.git",
    "git@github.com:NPSZ12/INSYT_SAAS.git",
}
PUBLIC_KEY_SHA256 = (
    "1a226fb6274f9ee7269c8929ffafbe3a39ff9ffdddcdee30f9292c3cbd677300"
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def stop(message):
    raise RuntimeError("STOP: " + message)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        stop("Git verification failed: " + " ".join(args))
    return result.stdout.strip()


def read_policy_file(policy_sha, path):
    if not SHA40.fullmatch(policy_sha):
        stop("Invalid trusted policy revision")

    result = github_json(
        "contents/" + path + "?ref=" + policy_sha
    )

    if (
        not isinstance(result, dict)
        or result.get("type") != "file"
        or result.get("path") != path
        or result.get("encoding") != "base64"
        or not isinstance(result.get("content"), str)
    ):
        stop("Trusted policy file unavailable")

    try:
        encoded = "".join(result["content"].split())
        raw = base64.b64decode(encoded, validate=True)
        return raw.decode("utf-8").strip()
    except (ValueError, binascii.Error, UnicodeError):
        stop("Trusted policy file encoding invalid")


def github_json(endpoint):
    token = os.environ.get("GITHUB_TOKEN")

    if not token:
        stop("GitHub API read token missing")

    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + "/" + endpoint,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify_approval_policy_revision(
    publication_sha,
    signed_envelope,
):
    """Resolve signed policy identity through protected history.

    The current protected branch publishes authorization.
    The signed ancestor establishes the independently approved
    policy contents. Candidate input cannot establish trust.
    """

    if (
        not isinstance(publication_sha, str)
        or not SHA40.fullmatch(publication_sha)
    ):
        stop("Invalid policy publication revision")

    if not isinstance(signed_envelope, dict):
        stop("Signed envelope missing")

    payload = signed_envelope.get("payload")

    if not isinstance(payload, dict):
        stop("Signed policy payload missing")

    approved_sha = payload.get("policy_commit")

    if (
        not isinstance(approved_sha, str)
        or not SHA40.fullmatch(approved_sha)
    ):
        stop("Invalid signed policy revision")

    if approved_sha != publication_sha:
        comparison = github_json(
            "compare/" + approved_sha + "..." + publication_sha
        )

        if not isinstance(comparison, dict):
            stop("Policy history verification failed")

        base = comparison.get("base_commit")
        merge_base = comparison.get("merge_base_commit")

        if (
            comparison.get("status") != "ahead"
            or comparison.get("behind_by") != 0
            or not isinstance(base, dict)
            or base.get("sha") != approved_sha
            or not isinstance(merge_base, dict)
            or merge_base.get("sha") != approved_sha
        ):
            stop("Signed policy is not a trusted ancestor")

    protected_files = (
        ".github/insyt-release/approved-feature-scopes.json",
        ".github/insyt-release/release-signing-public.pem",
    )

    for path in protected_files:
        approved_content = read_policy_file(
            approved_sha, path
        )

        published_content = read_policy_file(
            publication_sha, path
        )

        if approved_content != published_content:
            stop("Approved policy contents changed")

    return approved_sha


def extract_authorized_artifact(
    artifact_directory,
    destination,
    component,
    evidence,
):
    """Extract only an independently verified retained archive.

    The expected directory fingerprint comes from verified
    signed release evidence, never an independent CLI digest.
    """

    if not isinstance(evidence, dict):
        stop("Verified release evidence missing")

    if evidence.get("evidence_verified") is not True:
        stop("Verified release evidence required")

    if component not in ("api", "frontend"):
        stop("Unexpected retained artifact component")

    if evidence.get("component") != component:
        stop("Retained artifact component differs")

    root = Path(artifact_directory)

    if root.is_symlink() or not root.is_dir():
        stop("Retained artifact directory unsafe")

    archive_name = component + ".tar"
    entries = list(root.iterdir())

    if (
        len(entries) != 1
        or entries[0].name != archive_name
        or entries[0].is_symlink()
        or not entries[0].is_file()
    ):
        stop("Unexpected retained artifact inventory")

    # Snapshot the approved archive into a private directory.
    # Verify that snapshot against the signed package identity.
    with tempfile.TemporaryDirectory(
        prefix="insyt-authorized-"
    ) as temporary:

        snapshot = Path(temporary)
        retained = snapshot / archive_name

        shutil.copyfile(entries[0], retained)

        verify_directory(
            snapshot,
            evidence["artifact_sha256"],
        )

        # Raw archive checksum is derived only after the
        # signed directory fingerprint has matched.
        expected = archive_sha256(retained)

        return extract_verified_archive(
            retained,
            destination,
            expected,
        )


def verify_package_run(run_id, release_sha):
    if (
        not isinstance(run_id, str)
        or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
    ):
        stop("Invalid package preparation run ID")

    run = github_json("actions/runs/" + run_id)

    if not isinstance(run, dict):
        stop("Package preparation run unavailable")

    repository = run.get("head_repository")

    if (
        str(run.get("id")) != run_id
        or run.get("head_sha") != release_sha
        or run.get("event") != "workflow_dispatch"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("path")
            != ".github/workflows/insyt-release-packages.yml"
        or not isinstance(repository, dict)
        or repository.get("full_name") != REPOSITORY
    ):
        stop("Package preparation provenance rejected")

    return True


def verify_ci(release_sha):
    runs = github_json(
        "actions/workflows/insyt-release-validation.yml/runs"
        "?head_sha=" + release_sha + "&per_page=100"
    )

    if runs.get("total_count", 0) > 100:
        stop("CI run search is not exhaustive")

    required = {
        "Protected Source Integrity",
        "API Startup and JSON Regressions",
        "Frontend Build Validation",
    }

    for run in runs.get("workflow_runs", []):
        if (
            run.get("head_sha") != release_sha
            or run.get("event") != "push"
            or run.get("head_branch")
                != RELEASE_REF.removeprefix("refs/heads/")
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            continue

        jobs_data = github_json(
            "actions/runs/" + str(run["id"]) + "/jobs?per_page=100"
        )

        if jobs_data.get("total_count", 0) > 100:
            stop("CI job inventory is not exhaustive")

        jobs = jobs_data.get("jobs", [])
        matching = [
            job for job in jobs
            if job.get("name") in required
        ]

        if (
            len(matching) == len(required)
            and {job["name"] for job in matching} == required
            and all(
                job.get("status") == "completed"
                and job.get("conclusion") == "success"
                for job in matching
            )
        ):
            return True

    stop("Required exact-commit CI has not passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--component", required=True,
        choices=("api", "frontend"),
    )
    parser.add_argument("--sha", required=True)
    parser.add_argument("--artifact-directory")
    parser.add_argument("--extract-to")
    parser.add_argument("--package-run-id")
    parser.add_argument(
        "--verify-package-run-only",
        action="store_true",
    )
    args = parser.parse_args()

    sha = args.sha.lower()

    if not SHA40.fullmatch(sha):
        stop("Invalid release SHA")

    if os.getenv("GITHUB_ACTIONS") != "true":
        stop("GitHub Actions required")

    if os.getenv("GITHUB_REPOSITORY") != REPOSITORY:
        stop("Unexpected GitHub repository")

    if os.getenv("GITHUB_REF") != RELEASE_REF:
        stop("Unauthorized deployment branch")

    if os.getenv("GITHUB_SHA", "").lower() != sha:
        stop("Deployment commit does not match GitHub checkout")

    if args.verify_package_run_only:
        if args.artifact_directory or args.extract_to:
            stop("Unexpected artifact extraction arguments")

        verify_package_run(args.package_run_id, sha)
        print("PASS: Exact package preparation provenance")
        print("PROVENANCE ONLY - NOT DEPLOYMENT AUTHORIZATION")
        return

    if not args.artifact_directory:
        stop("Approved deployment artifact directory is required")

    if not args.extract_to:
        stop("Authorized retained archive extraction required")

    verify_package_run(args.package_run_id, sha)

    if git("rev-parse", "HEAD") != sha:
        stop("Checked-out release revision mismatch")

    if git("remote", "get-url", "origin") not in REMOTE_URLS:
        stop("Unexpected Git origin")

    # The policy revision is obtained from the protected remote
    # reference, never supplied by the candidate's CLI or manifest.
    policy_ref = github_json(
        "git/ref/" + POLICY_REF.removeprefix("refs/")
    )

    if not isinstance(policy_ref, dict):
        stop("Trusted policy reference unavailable")

    policy_object = policy_ref.get("object")

    if (
        policy_ref.get("ref") != POLICY_REF
        or not isinstance(policy_object, dict)
        or policy_object.get("type") != "commit"
        or not isinstance(policy_object.get("sha"), str)
        or not SHA40.fullmatch(policy_object["sha"])
    ):
        stop("Trusted policy reference unavailable")

    policy_sha = policy_object["sha"]

    policy = json.loads(read_policy_file(
        policy_sha,
        ".github/insyt-release/approved-feature-scopes.json",
    ))

    public_pem = read_policy_file(
        policy_sha,
        ".github/insyt-release/release-signing-public.pem",
    ).encode("utf-8") + b"\n"

    # Normalize only the PEM's terminal line ending.
    if hashlib.sha256(public_pem).hexdigest() != PUBLIC_KEY_SHA256:
        stop("Trusted signing identity differs")

    public_key = serialization.load_pem_public_key(public_pem)

    if not isinstance(public_key, Ed25519PublicKey):
        stop("Trusted signing key is not Ed25519")

    from cryptography.hazmat.primitives import serialization as enc

    public_raw = public_key.public_bytes(
        encoding=enc.Encoding.Raw,
        format=enc.PublicFormat.Raw,
    )

    candidate = json.loads(
        Path(
            ".github/insyt-release/json-feature-scope-candidate.json"
        ).read_text(encoding="utf-8-sig")
    )

    # Only the exact 14 previously reviewed source files are in scope.
    components = candidate.get("components", {})

    if (
        set(components) != {"api", "frontend"}
        or len(components["api"].get("changes", {})) != 13
        or len(components["frontend"].get("changes", {})) != 1
    ):
        stop("JSON source scope changed")

    paths = (
        list(components["api"]["changes"])
        + list(components["frontend"]["changes"])
    )

    if len(paths) != len(set(paths)):
        stop("Duplicate source paths")

    blobs = {}

    for path in paths:
        if (
            not isinstance(path, str)
            or path.startswith("/")
            or "\\" in path
            or ".." in path.split("/")
        ):
            stop("Unsafe approved source path")

        blobs[path] = git("rev-parse", sha + ":" + path)

    envelope_path = (
        ".github/insyt-release/signed-releases/"
        + sha + "/" + args.component + ".json"
    )

    envelope = json.loads(
        read_policy_file(policy_sha, envelope_path)
    )

    # Authorization is published at the current protected tip.
    # Its signed policy revision must be verified independently
    # against that tip before signature verification.
    approved_policy_sha = verify_approval_policy_revision(
        policy_sha,
        envelope,
    )

    result = verify_release_evidence(
        candidate=candidate,
        source_blobs=blobs,
        policy=policy,
        trusted_policy_commit=approved_policy_sha,
        actual_policy_commit=approved_policy_sha,
        trusted_public_key=public_raw,
        signed_envelope=envelope,
        artifact_directory=args.artifact_directory,
        release_commit=sha,
        component=args.component,
    )

    verify_ci(sha)

    # Refuse deployment if policy publication changed
    # while authorization was being evaluated.
    current_policy_ref = github_json(
        "git/ref/" + POLICY_REF.removeprefix("refs/")
    )

    if not isinstance(current_policy_ref, dict):
        stop("Policy publication unavailable")

    if (
        current_policy_ref.get("ref") != POLICY_REF
        or current_policy_ref.get("object") != policy_object
    ):
        stop("Policy publication changed during verification")

    if result.get("evidence_verified") is not True:
        stop("Release evidence incomplete")

    if args.extract_to:
        extracted = extract_authorized_artifact(
            args.artifact_directory,
            args.extract_to,
            args.component,
            result,
        )

        print(
            "PASS: Signed archive safely extracted; files:",
            extracted["file_count"],
        )

    print("PASS: Trusted source approval")
    print("PASS: Signed exact deployment artifact")
    print("PASS: Exact-commit GitHub CI")
    print("PASS: INSYT release gate")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not expose credentials, tokens or sensitive contents.
        allowed = (
            "Unexpected GitHub repository",
            "Unauthorized deployment branch",
            "Deployment commit does not match GitHub checkout",
        )
        message = str(exc)
        if isinstance(exc, RuntimeError) and any(
            message == "STOP: " + value for value in allowed
        ):
            print(message, file=sys.stderr)
        else:
            print(
                "STOP: Production deployment denied. "
                "Release authorization incomplete or invalid.",
                file=sys.stderr,
            )
        sys.exit(2)
