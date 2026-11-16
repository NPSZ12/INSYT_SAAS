"""Validate project-specific TARai criteria approval records."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


class TARaiCriteriaApprovalError(ValueError):
    pass


def validate_criteria_approval(
    *,
    criteria_bytes: bytes,
    approval: dict[str, Any],
    client: str,
    project: str,
) -> str:
    """Validate approval metadata and exact content integrity.

    The calling layer must independently trust the source of the
    approval record. Self-asserted metadata is not proof of approval.
    """
    if not isinstance(criteria_bytes, bytes):
        raise TARaiCriteriaApprovalError("Invalid criteria content.")

    if not isinstance(approval, dict):
        raise TARaiCriteriaApprovalError("Approval record is required.")

    if approval.get("status") != "approved":
        raise TARaiCriteriaApprovalError("Criteria are not approved.")

    if approval.get("client") != client or approval.get("project") != project:
        raise TARaiCriteriaApprovalError("Approval scope does not match.")

    approver = approval.get("approved_by")
    if not isinstance(approver, str) or not approver.strip():
        raise TARaiCriteriaApprovalError("Approver is missing.")

    timestamp = approval.get("approved_at")
    try:
        if not isinstance(timestamp, str):
            raise ValueError("Invalid timestamp")
        approved_at = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
        if approved_at.tzinfo is None:
            raise ValueError("Timezone is required")
    except ValueError as exc:
        raise TARaiCriteriaApprovalError(
            "Approval timestamp is invalid."
        ) from exc

    expected_hash = approval.get("sha256")
    actual_hash = hashlib.sha256(criteria_bytes).hexdigest()

    if not isinstance(expected_hash, str) or expected_hash != actual_hash:
        raise TARaiCriteriaApprovalError(
            "Criteria do not match the approved version."
        )

    if not criteria_bytes or len(criteria_bytes) > 10000:
        raise TARaiCriteriaApprovalError("Invalid criteria size.")

    try:
        criteria = criteria_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise TARaiCriteriaApprovalError(
            "Criteria must be UTF-8."
        ) from exc

    if not criteria or len(criteria) > 5000:
        raise TARaiCriteriaApprovalError(
            "Criteria are empty or too long."
        )

    return criteria