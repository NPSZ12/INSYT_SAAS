"""Reusable application scope validation.

The baseline comes from independently trusted policy.
Candidate declarations never establish approval authority.
"""

import re

from insyt_release_transition import (
    inspect_transition,
    require,
    revision,
)

from insyt_protected_source import (
    read_policy_json,
    verify_protected_source,
)

LEDGER = ".github/insyt-release/approved-feature-scopes.json"

SHA40 = re.compile(r"^[0-9a-f]{40}$")

FEATURE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def approved_baseline(policy_commit):

    revision(policy_commit)

    ledger = read_policy_json(
        policy_commit,
        LEDGER,
    )

    require(
        type(ledger.get("schema_version")) is int
        and ledger["schema_version"] == 1,
        "Invalid trusted approval ledger",
    )

    records = ledger.get("approved_scopes")

    require(
        isinstance(records, list)
        and len(records) == 1,
        "Exactly one effective trusted approval required",
    )

    record = records[0]

    require(
        record.get("approval_status") == "APPROVED",
        "Trusted baseline approval unavailable",
    )

    baseline = record.get("release_commit")

    require(
        isinstance(baseline, str)
        and SHA40.fullmatch(baseline),
        "Invalid approved baseline identity",
    )

    return revision(baseline)


def prepare_scope(policy_commit, candidate, feature):

    require(
        isinstance(feature, str)
        and FEATURE.fullmatch(feature),
        "Invalid application feature identity",
    )

    baseline = approved_baseline(policy_commit)

    transition = inspect_transition(
        baseline,
        candidate,
    )

    return {
        "schema_version": 1,
        "feature": feature,
        "status": "PENDING_REVIEW_NOT_APPROVED",
        "production_deployment_authorized": False,
        "candidate_commit": candidate,
        "components": transition["components"],
    }


def verify_new_scope(policy_commit, proposed):

    require(
        isinstance(proposed, dict),
        "Proposed application scope missing",
    )

    require(
        set(proposed) == {
            "schema_version",
            "feature",
            "status",
            "production_deployment_authorized",
            "candidate_commit",
            "components",
        },
        "Unexpected application scope fields",
    )

    require(
        type(proposed.get("schema_version")) is int
        and proposed["schema_version"] == 1,
        "Invalid application scope schema",
    )

    require(
        proposed.get("status")
        == "PENDING_REVIEW_NOT_APPROVED"
        and proposed.get(
            "production_deployment_authorized"
        ) is False,
        "Candidate claims unauthorized approval",
    )

    candidate = proposed.get("candidate_commit")
    feature = proposed.get("feature")

    expected = prepare_scope(
        policy_commit,
        candidate,
        feature,
    )

    require(
        proposed == expected,
        "Proposed scope differs from exact Git transition",
    )

    baseline = approved_baseline(policy_commit)

    count = verify_protected_source(
        policy_commit,
        baseline,
        candidate,
    )

    transition = inspect_transition(
        baseline,
        candidate,
    )

    return {
        "policy_commit": policy_commit,
        "baseline": baseline,
        "candidate_commit": candidate,
        "feature": feature,
        "components": transition["components"],
        "source_blobs": transition["source_blobs"],
        "protected_source_count": count,
        "scope_verified": True,
        "production_deployment_authorized": False,
    }


MANIFEST = (
    ".github/insyt-release/json-feature-scope-candidate.json"
)


def verify_release_candidate(policy_commit, release_commit):
    """Validate exact release source without authorizing deployment."""

    from insyt_release_transition import git, changed_paths, source_blob

    revision(policy_commit)
    revision(release_commit)

    proposed = read_policy_json(
        release_commit,
        MANIFEST,
    )

    evidence = verify_new_scope(
        policy_commit,
        proposed,
    )

    require(
        evidence.get("scope_verified") is True
        and evidence.get(
            "production_deployment_authorized"
        ) is False,
        "Invalid incoming scope authorization evidence",
    )

    require(
        evidence.get("candidate_commit")
        == proposed.get("candidate_commit")
        and evidence.get("feature")
        == proposed.get("feature")
        and evidence.get("components")
        == proposed.get("components"),
        "Incoming scope evidence identity differs",
    )

    checkpoint = evidence["candidate_commit"]
    baseline = evidence["baseline"]

    require(
        all(
            component.get("baseline") == baseline
            for component in proposed["components"].values()
        ),
        "Verified baseline differs from component baseline",
    )

    revision(checkpoint)
    revision(baseline)

    git(
        "merge-base",
        "--is-ancestor",
        checkpoint,
        release_commit,
    )

    require(
        changed_paths(checkpoint, release_commit) == {
            MANIFEST: "M",
        },
        "Unexpected post-candidate release changes",
    )

    expected = {}

    for component in evidence["components"].values():
        expected.update(component["changes"])

    expected[MANIFEST] = "M"

    require(
        changed_paths(baseline, release_commit) == expected,
        "Complete release transition differs from approved scope",
    )

    for path, expected_blob in evidence["source_blobs"].items():

        require(
            source_blob(release_commit, path) == expected_blob,
            "Release source differs from verified candidate: " + path,
        )

    verify_protected_source(
        policy_commit,
        baseline,
        release_commit,
    )

    return {
        **evidence,
        "release_commit": release_commit,
        "release_source_verified": True,
        "production_deployment_authorized": False,
    }
