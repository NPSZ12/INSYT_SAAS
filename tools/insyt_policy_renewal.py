"""Repeatable INSYT policy renewal validation.

Policy validation only. Never grants deployment authorization.
"""

import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREFIX = ".github/insyt-release/"
LEDGER = PREFIX + "approved-feature-scopes.json"
PUBLIC = PREFIX + "release-signing-public.pem"

POLICY_REF = "refs/remotes/origin/policy/insyt-hardened"
RELEASE_REF = "refs/remotes/origin/release/json-promotion-20261119"

TRUSTED_KEY = (
    "1a226fb6274f9ee7269c8929ffafbe3a39"
    "ff9ffdddcdee30f9292c3cbd677300"
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_ID = re.compile(r"^[A-Z0-9-]{1,100}$")


class RenewalDenied(Exception):
    pass


def require(condition, message):
    if not condition:
        raise RenewalDenied("STOP: " + message)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
    )

    require(result.returncode == 0, "Git verification failed")

    return result.stdout


def revision(ref):
    value = git("rev-parse", "--verify", ref).decode().strip()
    require(SHA40.fullmatch(value), "Invalid revision")
    return value


def read_json(commit, path):
    return json.loads(
        git("show", commit + ":" + path).decode("utf-8-sig")
    )


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def changed(base, target):
    raw = git(
        "diff", "--name-status", "-z", "--no-renames",
        base, target, "--",
    )

    fields = raw.decode("utf-8").split("\0")

    if fields[-1] == "":
        fields.pop()

    require(len(fields) % 2 == 0, "Invalid change inventory")

    result = {}

    for index in range(0, len(fields), 2):
        status, path = fields[index:index + 2]

        require(path not in result, "Duplicate changed path")

        result[path] = status

    return result


def ancestor(base, target):
    git("merge-base", "--is-ancestor", base, target)


def single_record(ledger):
    require(
        type(ledger.get("schema_version")) is int
        and ledger["schema_version"] == 1,
        "Invalid policy schema",
    )

    records = ledger.get("approved_scopes")

    require(
        isinstance(records, list) and len(records) == 1,
        "Exactly one effective approval required",
    )

    record = records[0]

    require(
        record.get("approval_status") == "APPROVED",
        "Effective approval unavailable",
    )

    require(
        APPROVAL_ID.fullmatch(record.get("approval_id", "")),
        "Invalid approval identifier",
    )

    require(
        SHA40.fullmatch(record.get("release_commit", "")),
        "Invalid release identity",
    )

    return record


def verify_signature(public, message, signature):
    require(len(signature) == 64, "Invalid signature length")

    import sys

    if sys.platform == "win32":
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        key = serialization.load_pem_public_key(public)

        require(
            isinstance(key, Ed25519PublicKey),
            "Unexpected signing key type",
        )

        try:
            key.verify(signature, message)
        except InvalidSignature:
            raise RenewalDenied("STOP: Cryptographic signature rejected")

        return

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)

        (root / "public.pem").write_bytes(public)
        (root / "message").write_bytes(message)
        (root / "signature").write_bytes(signature)

        result = subprocess.run(
            [
                "openssl", "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey", str(root / "public.pem"),
                "-rawin",
                "-in", str(root / "message"),
                "-sigfile", str(root / "signature"),
            ],
            capture_output=True,
        )

        require(
            result.returncode == 0,
            "Cryptographic signature rejected",
        )


def verify_security_installation_signature(base, envelope):
    """Verify independently signed security installation evidence.

    Security installation approval never authorizes application
    deployment or establishes successful production deployment.
    """

    require(
        SHA40.fullmatch(base),
        "Invalid security policy baseline",
    )

    require(
        isinstance(envelope, dict)
        and set(envelope) == {"payload", "signature"},
        "Invalid security installation envelope",
    )

    payload = envelope["payload"]

    require(
        isinstance(payload, dict)
        and set(payload) == {
            "schema_version",
            "repository",
            "transition_type",
            "previous_policy_commit",
            "previous_production_commit",
            "security_installation_commit",
            "transition_sha256",
            "registry_sha256",
            "history_sha256",
            "production_evidence_sha256",
            "production_deployment_authorized",
        },
        "Unexpected security authorization fields",
    )

    require(
        type(payload["schema_version"]) is int
        and payload["schema_version"] == 1
        and payload["repository"] == "NPSZ12/INSYT_SAAS"
        and payload["transition_type"] == "SECURITY_INSTALLATION"
        and payload["previous_policy_commit"] == base
        and payload["production_deployment_authorized"] is False,
        "Invalid security authorization identity",
    )

    for field in (
        "previous_production_commit",
        "security_installation_commit",
    ):
        require(
            isinstance(payload[field], str)
            and SHA40.fullmatch(payload[field]),
            "Invalid security transition commit",
        )

    for field in (
        "transition_sha256",
        "registry_sha256",
        "history_sha256",
        "production_evidence_sha256",
    ):
        require(
            isinstance(payload[field], str)
            and SHA256.fullmatch(payload[field]),
            "Invalid security transition digest",
        )

    public = git("show", base + ":" + PUBLIC).strip() + b"\n"

    require(
        hashlib.sha256(public).hexdigest() == TRUSTED_KEY,
        "Trusted security signing identity changed",
    )

    signature = base64.b64decode(
        envelope["signature"],
        validate=True,
    )

    verify_signature(
        public,
        b"INSYT-SECURITY-INSTALLATION-V1\n" + canonical(payload),
        signature,
    )

    return payload


def verify_security_installation_transition(
    base,
    envelope,
    transition_bytes,
    registry_bytes,
    history_bytes,
    production_evidence_bytes,
):
    """Verify signed security evidence against actual Git content."""

    from insyt_release_transition import source_blob
    from insyt_protected_source import validate_registry

    payload = verify_security_installation_signature(
        base,
        envelope,
    )

    evidence_files = {
        "transition_sha256": transition_bytes,
        "registry_sha256": registry_bytes,
        "history_sha256": history_bytes,
        "production_evidence_sha256": production_evidence_bytes,
    }

    for field, content in evidence_files.items():
        require(
            isinstance(content, bytes)
            and hashlib.sha256(content).hexdigest() == payload[field],
            "Signed security evidence differs: " + field,
        )

    transition = json.loads(transition_bytes)
    registry = json.loads(registry_bytes)
    history = json.loads(history_bytes)
    production_evidence = json.loads(production_evidence_bytes)

    production = payload["previous_production_commit"]
    installation = payload["security_installation_commit"]

    ledger = read_json(base, LEDGER)
    previous = single_record(ledger)

    require(
        previous["release_commit"] == production,
        "Security installation differs from previous approved release",
    )

    require(
        transition.get("schema_version") == 1
        and transition.get("repository") == "NPSZ12/INSYT_SAAS"
        and transition.get("transition_type") == "SECURITY_INSTALLATION"
        and transition.get("previous_policy_commit") == base
        and transition.get("previous_production_commit") == production
        and transition.get("security_installation_commit") == installation
        and transition.get("application_source_changed") is False
        and transition.get("production_deployment_authorized") is False,
        "Security transition identity differs",
    )

    require(
        transition.get("production_evidence_sha256")
        == payload["production_evidence_sha256"],
        "Production evidence binding differs",
    )

    require(
        production_evidence.get("release_commit") == production
        and production_evidence.get("previous_policy_commit") == base
        and production_evidence.get(
            "production_deployment_authorized"
        ) is False,
        "Previous production evidence identity differs",
    )

    ancestor(production, installation)

    actual = changed(production, installation)
    observed = {}

    allowed_workflows = {
        ".github/workflows/insyt-release-validation.yml",
        ".github/workflows/main_insyt-api-prod-v2.yml",
        ".github/workflows/main_insyt-app-prod.yml",
    }

    for entry in transition["files"]:

        name = entry["path"]
        status = entry["change"]

        require(
            name not in observed
            and status in {"A", "M"}
            and (
                name in allowed_workflows
                or (
                    name.startswith((
                        "tools/insyt_",
                        "tools/test_insyt_",
                    ))
                    and name.count("/") == 1
                    and name.endswith(".py")
                )
            ),
            "Unauthorized security installation path",
        )

        require(
            source_blob(installation, name)
            == entry["proposed_blob"],
            "Proposed security source differs: " + name,
        )

        if status == "M":
            require(
                source_blob(production, name)
                == entry["previous_blob"],
                "Previous security source differs: " + name,
            )
        else:
            require(
                entry["previous_blob"] is None,
                "Unexpected previous source identity",
            )

        content = git("show", installation + ":" + name)

        require(
            hashlib.sha256(content).hexdigest()
            == entry["sha256"],
            "Security source digest differs: " + name,
        )

        observed[name] = status

    require(
        observed and observed == actual,
        "Complete security installation inventory differs",
    )

    # Compare against the independently established previous
    # protected policy, not candidate-provided history.

    old_registry = read_json(
        base,
        PREFIX + "hardened-registry.json",
    )

    old_history = read_json(
        base,
        PREFIX + "hardened-history.json",
    )

    require(
        set(registry) == set(old_registry),
        "Protected registry structure changed",
    )

    for field in old_registry:

        if field == "protected_source":
            continue

        require(
            registry[field] == old_registry[field],
            "Protected registry requirement changed: " + field,
        )

    require(
        set(history) == set(old_history)
        and history["schema_version"] == old_history["schema_version"],
        "Protected history structure changed",
    )

    old_records = {
        record["path"]: record
        for record in old_registry["protected_source"]
    }

    new_records = {
        record["path"]: record
        for record in registry["protected_source"]
    }

    require(
        len(old_records) == len(old_registry["protected_source"])
        and len(new_records) == len(registry["protected_source"])
        and set(old_records) == set(new_records),
        "Protected source population changed",
    )

    permitted_updates = {
        ".github/workflows/main_insyt-api-prod-v2.yml",
        ".github/workflows/main_insyt-app-prod.yml",
    }

    for name, old_record in old_records.items():

        new_record = new_records[name]

        if name not in permitted_updates:

            require(
                new_record == old_record,
                "Unapproved protected registry change: " + name,
            )

            continue

        require(
            set(new_record) == set(old_record),
            "Protected registry record structure changed",
        )

        for field in old_record:

            if field not in {"git_blob_sha", "reference_commit"}:

                require(
                    new_record[field] == old_record[field],
                    "Protected registry metadata changed",
                )

        require(
            new_record["git_blob_sha"]
            == source_blob(installation, name)
            and new_record["reference_commit"] == installation,
            "Protected installation identity differs",
        )

    old_features = old_history["features"]
    new_features = history["features"]

    require(
        set(old_features) == set(new_features),
        "Protected history population changed",
    )

    for feature, old_record in old_features.items():

        new_record = new_features[feature]

        require(
            set(old_record) == set(new_record),
            "Protected history record structure changed",
        )

        for field in old_record:

            if field != "versions":

                require(
                    new_record[field] == old_record[field],
                    "Protected history metadata changed",
                )

        old_versions = old_record["versions"]
        new_versions = new_record["versions"]

        require(
            new_versions[:len(old_versions)] == old_versions,
            "Historical protected versions modified or removed",
        )

        paths = set(old_versions[-1]["source"])

        if not paths.intersection(permitted_updates):

            require(
                new_versions == old_versions,
                "Unapproved protected history extension",
            )

            continue

        expected_versions = list(old_versions)
        previous_source = old_versions[-1]["source"]

        for checkpoint in (production, installation):

            current_source = {
                name: source_blob(checkpoint, name)
                for name in sorted(paths)
            }

            if current_source != previous_source:

                expected_versions.append({
                    "version": len(expected_versions) + 1,
                    "source": current_source,
                })

                previous_source = current_source

        require(
            new_versions == expected_versions,
            "Unexpected protected workflow history",
        )

    require(
        validate_registry(
            registry,
            history,
            installation,
            installation,
        ) >= 9,
        "Protected source inventory incomplete",
    )

    return {
        "previous_production_commit": production,
        "security_installation_commit": installation,
        "previous_policy_commit": base,
        "security_transition_verified": True,
        "production_deployment_authorized": False,
    }


def validate_renewal(base, target, release):
    for value in (base, target, release):
        require(SHA40.fullmatch(value), "Invalid commit identity")

    ancestor(base, target)

    previous_ledger = read_json(base, LEDGER)
    current_ledger = read_json(target, LEDGER)

    previous = single_record(previous_ledger)
    current = single_record(current_ledger)

    require(
        previous["release_commit"] != release,
        "Release already approved",
    )

    require(
        current["release_commit"] == release,
        "Approval does not match trusted release",
    )

    require(
        current["approval_id"] != previous["approval_id"],
        "Approval identity reused",
    )

    old_release = previous["release_commit"]
    ancestor(old_release, release)

    candidate = read_json(
        release,
        PREFIX + "json-feature-scope-candidate.json",
    )

    require(
        candidate.get("schema_version") == 1
        and candidate.get("status") == "PENDING_REVIEW_NOT_APPROVED"
        and candidate.get("production_deployment_authorized") is False,
        "Invalid candidate authorization state",
    )

    for field in ("feature", "candidate_commit", "components"):
        require(
            candidate.get(field) == current.get(field),
            "Candidate scope differs: " + field,
        )

    expected = dict(previous)
    expected["approval_id"] = current["approval_id"]
    expected["release_commit"] = release

    if current == expected:

        # Preserve the existing same-scope renewal restrictions.
        source_delta = changed(old_release, release)

        permitted_release_changes = {
            "tools/insyt_deployment_gate.py",
        }

        require(
            set(source_delta).issubset(permitted_release_changes)
            and all(
                status == "M"
                for status in source_delta.values()
            ),
            "Release contains independently unapproved changes",
        )

    else:

        # Use the shared final release candidate validator.
        from insyt_new_scope_validation import verify_release_candidate

        evidence = verify_release_candidate(base, release)

        require(
            evidence.get("scope_verified") is True
            and evidence.get("release_source_verified") is True
            and evidence.get(
                "production_deployment_authorized"
            ) is False,
            "Final release scope verification incomplete",
        )

        from insyt_new_scope_validation import (
            resolve_release_baselines,
        )

        baselines = resolve_release_baselines(base)

        require(
            baselines["approved_release_baseline"] == old_release
            and evidence.get("approved_release_baseline")
            == old_release,
            "Previous approved release identity differs",
        )

        require(
            evidence["baseline"] == baselines["source_baseline"],
            "New scope baseline differs from trusted approval",
        )

        if baselines["source_baseline"] != old_release:

            require(
                baselines.get(
                    "security_installation_verified"
                ) is True
                and baselines.get(
                    "security_installation_commit"
                ) == baselines["source_baseline"],
                "Separate security baseline is not authorized",
            )

        checkpoint = candidate["candidate_commit"]

        require(
            evidence["candidate_commit"] == checkpoint
            and evidence["release_commit"] == release
            and evidence["feature"] == candidate["feature"]
            and evidence["components"] == candidate["components"],
            "Final release evidence identity differs",
        )

        expected_approval = {
            "approval_id": current["approval_id"],
            "approval_status": "APPROVED",
            "feature": candidate["feature"],
            "candidate_commit": checkpoint,
            "release_commit": release,
            "components": evidence["components"],
            "source_blobs": evidence["source_blobs"],
        }

        require(
            current == expected_approval,
            "New approval differs from exact verified scope",
        )

    paths = []

    for component in current["components"].values():
        paths.extend(component["changes"])

    blobs = current["source_blobs"]

    require(
        paths and len(paths) == len(set(paths))
        and set(paths) == set(blobs),
        "Incomplete or duplicate approved source inventory",
    )

    for path, blob in blobs.items():
        require(
            SHA40.fullmatch(blob)
            and not path.startswith("/")
            and ".." not in path.split("/"),
            "Invalid approved source identity",
        )

        require(
            revision(release + ":" + path) == blob,
            "Approved source changed: " + path,
        )

    archive = (
        PREFIX + "approval-history/"
        + previous["approval_id"] + ".json"
    )

    signature_root = PREFIX + "signed-releases/" + release

    permitted_policy_changes = {
        LEDGER: "M",
        archive: "A",
        signature_root + "/api.json": "A",
        signature_root + "/frontend.json": "A",
    }

    require(
        changed(base, target) == permitted_policy_changes,
        "Unexpected policy publication scope",
    )

    require(
        read_json(target, archive) == previous,
        "Historical approval differs",
    )

    public = git("show", base + ":" + PUBLIC).strip() + b"\n"

    require(
        hashlib.sha256(public).hexdigest() == TRUSTED_KEY,
        "Trusted signing identity changed",
    )

    require(
        git("show", target + ":" + PUBLIC).strip() + b"\n" == public,
        "Proposed signing identity changed",
    )

    scope = hashlib.sha256(canonical(current)).hexdigest()

    policy_checkpoint = None

    for component in ("api", "frontend"):
        envelope = read_json(
            target,
            signature_root + "/" + component + ".json",
        )

        require(
            set(envelope) == {"payload", "signature"},
            "Unexpected signature envelope",
        )

        payload = envelope["payload"]

        checkpoint = payload.get("policy_commit", "")
        digest = payload.get("artifact_sha256", "")

        require(
            SHA40.fullmatch(checkpoint)
            and SHA256.fullmatch(digest),
            "Invalid signed evidence identity",
        )

        expected_payload = {
            "schema_version": 1,
            "repository": "NPSZ12/INSYT_SAAS",
            "component": component,
            "release_commit": release,
            "policy_commit": checkpoint,
            "scope_sha256": scope,
            "artifact_sha256": digest,
        }

        require(
            payload == expected_payload,
            "Signed release identity differs",
        )

        if policy_checkpoint is None:
            policy_checkpoint = checkpoint

        require(
            checkpoint == policy_checkpoint,
            "Components reference different policy checkpoints",
        )

        ancestor(base, checkpoint)
        ancestor(checkpoint, target)

        require(
            changed(base, checkpoint) == {LEDGER: "M"},
            "Unexpected signed policy checkpoint scope",
        )

        require(
            read_json(checkpoint, LEDGER) == current_ledger,
            "Signed approval ledger differs",
        )

        signature = base64.b64decode(
            envelope["signature"], validate=True
        )

        verify_signature(
            public,
            b"INSYT-RELEASE-APPROVAL-V1\n" + canonical(payload),
            signature,
        )

        print("PASS: Cryptographic authorization:", component)

    print("PASS: Historical approval and signatures preserved")
    print("PASS: Exact reviewed application scope preserved")
    print("PASS: Repeatable signed policy renewal verified")
    print("POLICY VALIDATION ONLY - NOT DEPLOYMENT AUTHORIZATION")


if __name__ == "__main__":
    try:
        validate_renewal(
            revision(POLICY_REF),
            revision("HEAD"),
            revision(RELEASE_REF),
        )
    except (RenewalDenied, ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(str(exc))
