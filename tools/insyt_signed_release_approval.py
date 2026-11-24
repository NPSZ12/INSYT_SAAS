"""INSYT signed release-approval verification.

Verification only. This module does not generate production keys,
select trusted public keys, attest CI, or authorize deployment alone.
"""

import base64
import binascii
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

DOMAIN = b"INSYT-RELEASE-APPROVAL-V1\n"

FIELDS = {
    "schema_version",
    "repository",
    "component",
    "release_commit",
    "policy_commit",
    "scope_sha256",
    "artifact_sha256",
}

REPOSITORY = "NPSZ12/INSYT_SAAS"


class ApprovalDenied(Exception):
    pass


def deny(message):
    raise ApprovalDenied("STOP: " + message)


def canonical(payload):
    if not isinstance(payload, dict):
        deny("Approval payload must be an object")

    return DOMAIN + json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def verify_signed_release(
    envelope,
    trusted_public_key,
    *,
    release_commit,
    policy_commit,
    scope_sha256,
    artifact_sha256,
    component,
):
    """Verify signature and exact identities supplied by trusted caller.

    The expected identities and public key MUST come from a trusted
    deployment authority, never candidate-branch input.
    """

    if not isinstance(envelope, dict):
        deny("Approval envelope missing")

    if set(envelope) != {"payload", "signature"}:
        deny("Unexpected approval envelope fields")

    payload = envelope["payload"]

    if not isinstance(payload, dict) or set(payload) != FIELDS:
        deny("Approval payload schema mismatch")

    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        deny("Unsupported signature schema")

    if payload["repository"] != REPOSITORY:
        deny("Unexpected repository")

    if component not in ("api", "frontend"):
        deny("Invalid deployment component")

    if payload["component"] != component:
        deny("Deployment component differs from approval")

    for field, expected, pattern in (
        ("release_commit", release_commit, SHA40),
        ("policy_commit", policy_commit, SHA40),
        ("scope_sha256", scope_sha256, SHA256),
        ("artifact_sha256", artifact_sha256, SHA256),
    ):
        if (
            not isinstance(expected, str)
            or not pattern.fullmatch(expected)
            or payload[field] != expected
        ):
            deny("Release identity mismatch: " + field)

    if not isinstance(trusted_public_key, bytes) or len(trusted_public_key) != 32:
        deny("Invalid trusted Ed25519 public key")

    signature_text = envelope["signature"]

    if not isinstance(signature_text, str):
        deny("Approval signature missing")

    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (ValueError, binascii.Error):
        deny("Malformed approval signature")

    if len(signature) != 64:
        deny("Invalid approval signature length")

    try:
        Ed25519PublicKey.from_public_bytes(
            trusted_public_key
        ).verify(signature, canonical(payload))
    except (InvalidSignature, ValueError):
        deny("Approval signature verification failed")

    return True
