"""INSYT release evidence integration.

This combines source, signature and package integrity.
It is NOT an independent deployment authority.

The caller must independently establish trusted policy
identity, public-key identity and exact-commit CI evidence.
"""

import hashlib
import json
import re

from insyt_artifact_integrity import (
    fingerprint_directory,
    ArtifactDenied,
)
from insyt_authoritative_scope import (
    verify as verify_scope,
    PolicyDenied,
)
from insyt_signed_release_approval import (
    verify_signed_release,
    ApprovalDenied,
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ReleaseEvidenceDenied(Exception):
    pass


def reject(message):
    raise ReleaseEvidenceDenied("STOP: " + message)


def scope_digest(record):
    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")

    return hashlib.sha256(canonical).hexdigest()


def verify_release_evidence(
    *,
    candidate,
    source_blobs,
    policy,
    trusted_policy_commit,
    actual_policy_commit,
    trusted_public_key,
    signed_envelope,
    artifact_directory,
    release_commit,
    component,
):
    """Verify source, signature and finished artifact together.

    This function does not verify GitHub CI or establish
    the independent origin of its trusted inputs.
    It cannot authorize Azure deployment by itself.
    """

    if (
        not isinstance(release_commit, str)
        or not SHA40.fullmatch(release_commit)
    ):
        reject("Invalid release commit")

    if (
        not isinstance(trusted_policy_commit, str)
        or not SHA40.fullmatch(trusted_policy_commit)
        or actual_policy_commit != trusted_policy_commit
    ):
        reject("Untrusted policy revision")

    if component not in ("api", "frontend"):
        reject("Unexpected component")

    if not isinstance(candidate, dict):
        reject("Candidate scope missing")

    # The source manifest intentionally names the immutable
    # JSON checkpoint, which can precede the CI-only changes.
    # The caller must independently verify the deployable
    # commit's permitted delta from that checkpoint.
    candidate_commit = candidate.get("candidate_commit")

    if (
        not isinstance(candidate_commit, str)
        or not SHA40.fullmatch(candidate_commit)
    ):
        reject("Candidate checkpoint invalid")

    if (
        not isinstance(policy, dict)
        or type(policy.get("schema_version")) is not int
        or policy["schema_version"] != 1
    ):
        reject("Invalid trusted policy")

    approvals = policy.get("approved_scopes")

    if not isinstance(approvals, list):
        reject("Approved scope ledger missing")

    matches = [
        record for record in approvals
        if isinstance(record, dict)
        and record.get("feature") == candidate.get("feature")
        and record.get("candidate_commit") == candidate_commit
    ]

    if len(matches) != 1:
        reject("Exactly one independent scope approval required")

    approval = matches[0]

    try:
        verify_scope(candidate, approval, source_blobs)
    except (PolicyDenied, KeyError, ValueError, TypeError) as exc:
        reject("Source approval rejected: " + str(exc))

    try:
        package = fingerprint_directory(artifact_directory)
    except (ArtifactDenied, OSError, ValueError) as exc:
        reject("Artifact rejected: " + str(exc))

    try:
        verify_signed_release(
            signed_envelope,
            trusted_public_key,
            release_commit=release_commit,
            policy_commit=trusted_policy_commit,
            scope_sha256=scope_digest(approval),
            artifact_sha256=package["sha256"],
            component=component,
        )
    except (ApprovalDenied, ValueError, TypeError) as exc:
        reject("Signed release rejected: " + str(exc))

    return {
        "release_commit": release_commit,
        "policy_commit": trusted_policy_commit,
        "component": component,
        "scope_sha256": scope_digest(approval),
        "artifact_sha256": package["sha256"],
        "file_count": package["file_count"],
        "evidence_verified": True,
        "deployment_authorized": False,
    }
