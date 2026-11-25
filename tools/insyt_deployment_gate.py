#!/usr/bin/env python3
"""INSYT production deployment gate.

Requires trusted policy, source approval, exact CI attestation,
signed finished artifact, and exact GitHub release identity.

No bypass mode, candidate-supplied public key, or automatic approval.
"""

import argparse
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
    return git("show", policy_sha + ":" + path)


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
            or run.get("event") != "pull_request"
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

    if not args.artifact_directory:
        stop("Approved deployment artifact directory is required")

    if git("rev-parse", "HEAD") != sha:
        stop("Checked-out release revision mismatch")

    if git("remote", "get-url", "origin") not in REMOTE_URLS:
        stop("Unexpected Git origin")

    # The policy revision is obtained from the protected remote
    # reference, never supplied by the candidate's CLI or manifest.
    remote = git("ls-remote", "--heads", "origin", POLICY_REF)
    parts = remote.split()

    if (
        len(parts) != 2
        or parts[1] != POLICY_REF
        or not SHA40.fullmatch(parts[0])
    ):
        stop("Trusted policy reference unavailable")

    policy_sha = parts[0]

    git("fetch", "--no-tags", "origin", POLICY_REF)

    if git("rev-parse", "FETCH_HEAD") != policy_sha:
        stop("Trusted policy changed during retrieval")

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

    # This must use a separately protected policy revision,
    # not a candidate-controlled or environment-supplied value.
    result = verify_release_evidence(
        candidate=candidate,
        source_blobs=blobs,
        policy=policy,
        trusted_policy_commit=policy_sha,
        actual_policy_commit=policy_sha,
        trusted_public_key=public_raw,
        signed_envelope=envelope,
        artifact_directory=args.artifact_directory,
        release_commit=sha,
        component=args.component,
    )

    verify_ci(sha)

    if result.get("evidence_verified") is not True:
        stop("Release evidence incomplete")

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
