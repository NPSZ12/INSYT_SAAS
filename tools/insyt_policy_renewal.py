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

        require(
            evidence["baseline"] == old_release,
            "New scope baseline differs from trusted approval",
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
