"""Trusted protected-source verification.

Validates source integrity only.
Never approves, signs or authorizes deployment.
"""

import json
import re

from insyt_release_transition import (
    git,
    revision,
    source_blob,
    require,
)

REGISTRY = ".github/insyt-release/hardened-registry.json"
HISTORY = ".github/insyt-release/hardened-history.json"

SHA40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PATHS = frozenset({
    "backend/app/api/auth.py",
    "backend/app/services/security.py",
    "backend/app/main.py",
    "backend/app/database/connection.py",
    "backend/app/database/init_db.py",
    ".github/workflows/main_insyt-api-prod-v2.yml",
    ".github/workflows/main_insyt-app-prod.yml",
    ".github/workflows/main_insyt-apc-worker-prod-v2.yml",
    ".github/workflows/insyt-detection-worker-v2-release.yml",
})


def read_policy_json(policy_commit, path):

    revision(policy_commit)

    return json.loads(
        git(
            "show",
            policy_commit + ":" + path,
        ).decode("utf-8-sig")
    )


def validate_registry(registry, history, baseline, candidate):

    revision(baseline)
    revision(candidate)

    require(
        registry.get("schema_version") == 1
        and history.get("schema_version") == 1,
        "Invalid protected registry schema",
    )

    safeguards = registry.get("policy", {})

    for name in (
        "automatic_hardening",
        "automatic_baseline_replacement",
        "automatic_test_removal",
    ):
        require(
            safeguards.get(name) is False,
            "Protected registry safeguard disabled: " + name,
        )

    for name in (
        "protected_deletion_requires_explicit_approval",
        "registry_changes_require_independent_review",
        "production_verification_required_for_promotion",
    ):
        require(
            safeguards.get(name) is True,
            "Required registry safeguard missing: " + name,
        )

    records = registry.get("protected_source")

    require(
        isinstance(records, list) and records,
        "Protected source inventory unavailable",
    )

    features = history.get("features")

    require(
        isinstance(features, dict) and features,
        "Protected source history unavailable",
    )

    historical = {}
    latest = {}

    for feature, record in features.items():

        versions = record.get("versions")

        require(
            isinstance(versions, list) and versions,
            "Missing protected history: " + feature,
        )

        original_paths = None

        for index, version in enumerate(versions, 1):

            require(
                type(version.get("version")) is int
                and version["version"] == index,
                "Invalid protected version sequence",
            )

            sources = version.get("source")

            require(
                isinstance(sources, dict) and sources,
                "Missing protected version source",
            )

            if original_paths is None:
                original_paths = set(sources)

            require(
                set(sources) == original_paths,
                "Protected version source inventory changed",
            )

            for path, blob in sources.items():

                require(
                    isinstance(path, str)
                    and isinstance(blob, str)
                    and SHA40.fullmatch(blob),
                    "Invalid historical source identity",
                )

                if index == 1:

                    require(
                        path not in historical,
                        "Duplicate historical source path",
                    )

                    historical[path] = blob

                if index == len(versions):
                    latest[path] = blob

    seen = set()
    seen_ids = set()

    for record in records:

        path = record.get("path")
        identity = record.get("id")
        expected = record.get("git_blob_sha")
        reference = record.get("reference_commit")

        require(
            isinstance(path, str)
            and path
            and isinstance(identity, str)
            and identity
            and isinstance(expected, str)
            and SHA40.fullmatch(expected),
            "Invalid protected source record",
        )

        require(
            path not in seen and identity not in seen_ids,
            "Duplicate protected source record",
        )

        seen.add(path)
        seen_ids.add(identity)

        require(
            record.get("protection") == "source_integrity",
            "Source protection disabled: " + path,
        )

        require(
            record.get("verification")
            == "source_only_not_full_runtime_attestation",
            "Invalid source verification claim: " + path,
        )

        require(
            latest.get(path) == expected,
            "Registry differs from latest protected history: " + path,
        )

        revision(reference)

        require(
            source_blob(reference, path) == expected,
            "Historical source identity mismatch: " + path,
        )

        require(
            source_blob(baseline, path) == expected,
            "Production baseline identity mismatch: " + path,
        )

        require(
            source_blob(candidate, path) == expected,
            "Candidate protected source mismatch: " + path,
        )

    require(
        REQUIRED_PATHS.issubset(seen),
        "Mandatory protected source missing",
    )

    require(
        seen == set(historical) == set(latest),
        "Protected registry and history inventories differ",
    )

    return len(seen)


def verify_protected_source(policy_commit, baseline, candidate):

    registry = read_policy_json(policy_commit, REGISTRY)
    history = read_policy_json(policy_commit, HISTORY)

    return validate_registry(
        registry,
        history,
        baseline,
        candidate,
    )
