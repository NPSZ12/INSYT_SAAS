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


# Historical policy compatibility only.
# Subsequent policy revisions require signed installation evidence.

LEGACY_PREINSTALLATION_POLICY = (
    "6b2355f63923e4957724f480cfbb0b1f3a7346bc"
)


def resolve_release_baselines(policy_commit):
    """Resolve approved release and separately signed source installation.

    A security installation never establishes production deployment.
    """

    import json

    from insyt_release_transition import git

    from insyt_policy_renewal import (
        verify_security_installation_transition,
    )

    approved = approved_baseline(policy_commit)

    prefix = ".github/insyt-release/security-installation/"

    entries = git(
        "ls-tree", "-r", "--name-only",
        policy_commit,
        "--", prefix,
    ).decode("utf-8").splitlines()

    if not entries:

        require(
            policy_commit == LEGACY_PREINSTALLATION_POLICY,
            "Required security installation evidence missing",
        )

        return {
            "approved_release_baseline": approved,
            "source_baseline": approved,
            "security_installation_verified": False,
        }

    required = {
        prefix + "authorization.json",
        prefix + "transition.json",
        prefix + "registry.json",
        prefix + "history.json",
        prefix + "production-evidence.json",
    }

    require(
        set(entries) == required,
        "Incomplete or unexpected security installation evidence",
    )

    def read_bytes(name):

        return git(
            "show",
            policy_commit + ":" + prefix + name,
        )

    envelope = json.loads(
        read_bytes("authorization.json")
    )

    base = envelope["payload"]["previous_policy_commit"]

    revision(base)

    git(
        "merge-base",
        "--is-ancestor",
        base,
        policy_commit,
    )

    result = verify_security_installation_transition(
        base,
        envelope,
        read_bytes("transition.json"),
        read_bytes("registry.json"),
        read_bytes("history.json"),
        read_bytes("production-evidence.json"),
    )

    require(
        result.get("security_transition_verified") is True
        and result.get(
            "production_deployment_authorized"
        ) is False,
        "Security installation authorization incomplete",
    )

    installation = result["security_installation_commit"]
    previous = result["previous_production_commit"]

    require(
        read_policy_json(
            policy_commit,
            ".github/insyt-release/hardened-registry.json",
        ) == json.loads(read_bytes("registry.json")),
        "Published registry differs from signed registry",
    )

    require(
        read_policy_json(
            policy_commit,
            ".github/insyt-release/hardened-history.json",
        ) == json.loads(read_bytes("history.json")),
        "Published history differs from signed history",
    )

    if approved == previous:

        source_baseline = installation

    else:

        git(
            "merge-base",
            "--is-ancestor",
            installation,
            approved,
        )

        source_baseline = approved

    return {
        "approved_release_baseline": approved,
        "source_baseline": source_baseline,
        "security_installation_verified": True,
        "security_installation_commit": installation,
    }


def prepare_scope(policy_commit, candidate, feature):

    require(
        isinstance(feature, str)
        and FEATURE.fullmatch(feature),
        "Invalid application feature identity",
    )

    baselines = resolve_release_baselines(policy_commit)
    baseline = baselines["source_baseline"]

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

    baselines = resolve_release_baselines(policy_commit)
    baseline = baselines["source_baseline"]

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
        "approved_release_baseline": baselines[
            "approved_release_baseline"
        ],
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
