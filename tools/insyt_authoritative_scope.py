"""INSYT policy-bound feature-scope verification.

This module never grants production deployment permission.
The policy record must come from the protected policy branch,
not from a manifest supplied by the candidate branch.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

POLICY_BRANCH = "refs/remotes/origin/policy/insyt-hardened"
POLICY_FILE = ".github/insyt-release/approved-feature-scopes.json"

CANDIDATE_FILE = (
    ".github/insyt-release/json-feature-scope-candidate.json"
)

SHA = re.compile(r"^[0-9a-f]{40}$")


class PolicyDenied(Exception):
    pass


def deny(reason):
    raise PolicyDenied("STOP: " + reason)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode:
        deny("Git verification failed: " + result.stderr.strip()[:200])

    return result.stdout.strip()


def verify(candidate, approval, blobs):
    """Compare candidate to a trusted exact-source approval."""

    if candidate.get("schema_version") != 1:
        deny("Unsupported candidate schema")

    if candidate.get("status") != "PENDING_REVIEW_NOT_APPROVED":
        deny("Candidate claims authorization")

    if candidate.get("production_deployment_authorized") is not False:
        deny("Candidate claims production authority")

    if approval.get("approval_status") != "APPROVED":
        deny("Trusted policy has no effective approval")

    if not approval.get("approval_id"):
        deny("Approval identifier missing")

    feature = candidate.get("feature")
    commit = candidate.get("candidate_commit")
    components = candidate.get("components")

    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        deny("Invalid candidate commit")

    if approval.get("feature") != feature:
        deny("Feature differs from approved scope")

    if approval.get("candidate_commit") != commit:
        deny("Commit differs from approved scope")

    if approval.get("components") != components:
        deny("Changed-file scope differs from approved scope")

    approved_blobs = approval.get("source_blobs")

    if not isinstance(approved_blobs, dict):
        deny("Approved blob mapping missing")

    if not isinstance(components, dict):
        deny("Candidate components invalid")

    paths = []

    for component in components.values():
        if not isinstance(component, dict):
            deny("Invalid component")

        changes = component.get("changes")

        if not isinstance(changes, dict):
            deny("Component changes missing")

        paths.extend(changes)

    if not paths or len(paths) != len(set(paths)):
        deny("Empty or duplicate scope paths")

    if set(approved_blobs) != set(paths):
        deny("Approved source identities differ from change scope")

    if set(blobs) != set(paths):
        deny("Candidate source identities incomplete")

    for path in paths:
        approved_sha = approved_blobs[path]
        actual_sha = blobs[path]

        if not isinstance(approved_sha, str) or not SHA.fullmatch(approved_sha):
            deny("Invalid approved Git blob: " + path)

        if actual_sha != approved_sha:
            deny("Unauthorized source revision: " + path)

    return True


def main():
    candidate = json.loads(
        (ROOT / CANDIDATE_FILE).read_text(encoding="utf-8-sig")
    )

    # Read from the separately tracked policy branch.
    # Never load approval content from the candidate worktree.
    # A missing or unavailable policy record is a hard failure.
    policy_source = POLICY_BRANCH + ":" + POLICY_FILE

    try:
        policy_text = git("show", policy_source)
    except PolicyDenied:
        deny("No approved feature-scope policy is installed")

    policy = json.loads(policy_text)

    if policy.get("schema_version") != 1:
        deny("Unsupported policy schema")

    approvals = policy.get("approved_scopes")

    if not isinstance(approvals, list):
        deny("Approved scope history missing")

    matches = [
        record for record in approvals
        if record.get("feature") == candidate.get("feature")
        and record.get("candidate_commit")
        == candidate.get("candidate_commit")
    ]

    if len(matches) != 1:
        deny("Exactly one trusted scope approval is required")

    paths = []

    for component in candidate["components"].values():
        paths.extend(component["changes"])

    blobs = {}

    for path in paths:
        if not isinstance(path, str) or path.startswith("/") or ".." in path.split("/"):
            deny("Invalid source path")

        blobs[path] = git("rev-parse", "HEAD:" + path)

    verify(candidate, matches[0], blobs)

    print("PASS: Exact scope approved by policy branch")
    print("PASS: Every authorized source blob matches")
    print("SCOPE APPROVAL VERIFIED — DEPLOYMENT STILL REQUIRES SEPARATE AUTHORIZATION")


if __name__ == "__main__":
    try:
        main()
    except (PolicyDenied, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
