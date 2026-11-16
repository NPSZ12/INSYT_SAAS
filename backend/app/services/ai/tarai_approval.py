"""Trusted, project-scoped TARai privilege-criteria approval records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.audit_log import AuditLog
from app.services.audit_service import write_audit_log
from app.services.ai.tarai_criteria import (
    TARaiCriteriaApprovalError,
    validate_criteria_approval,
)


APPROVAL_ACTION = "TARAI_PRIVILEGE_CRITERIA_APPROVED"
REVOCATION_ACTION = "TARAI_PRIVILEGE_CRITERIA_REVOKED"


def approve_criteria(
    *,
    db,
    actor,
    client: str,
    project: str,
    criteria_bytes: bytes,
    request=None,
) -> str:
    """Record approval using the authenticated actor, never caller metadata."""

    if not isinstance(criteria_bytes, bytes):
        raise TARaiCriteriaApprovalError(
            "Criteria must be supplied as bytes."
        )

    if not criteria_bytes or len(criteria_bytes) > 10000:
        raise TARaiCriteriaApprovalError(
            "Invalid privilege criteria size."
        )

    approver = str(getattr(actor, "username", "") or "").strip()

    if not approver:
        raise TARaiCriteriaApprovalError(
            "An authenticated approver is required."
        )

    digest = hashlib.sha256(criteria_bytes).hexdigest()

    approved_at = datetime.now(timezone.utc).isoformat()

    approval = {
        "status": "approved",
        "client": client,
        "project": project,
        "approved_by": approver,
        "approved_at": approved_at,
        "sha256": digest,
    }

    validate_criteria_approval(
        criteria_bytes=criteria_bytes,
        approval=approval,
        client=client,
        project=project,
    )

    write_audit_log(
        db=db,
        action=APPROVAL_ACTION,
        actor=actor,
        request=request,
        target_type="tarai_privilege_criteria",
        target_id=digest,
        workspace="discovery",
        client=client,
        project=project,
        details=approval,
    )

    return digest


def verify_approved_criteria(
    *,
    db,
    client: str,
    project: str,
    criteria_bytes: bytes,
) -> str:
    """Validate exact criteria against the latest trusted audit event."""

    record = (
        db.query(AuditLog)
        .filter(
            AuditLog.workspace == "discovery",
            AuditLog.client == client,
            AuditLog.project == project,
            AuditLog.action.in_(
                [APPROVAL_ACTION, REVOCATION_ACTION]
            ),
        )
        .order_by(AuditLog.id.desc())
        .first()
    )

    if record is None or record.action != APPROVAL_ACTION:
        raise TARaiCriteriaApprovalError(
            "No current trusted TARai approval exists."
        )

    try:
        approval = json.loads(record.details or "{}")
    except (TypeError, ValueError) as exc:
        raise TARaiCriteriaApprovalError(
            "Stored approval record is invalid."
        ) from exc

    if not isinstance(approval, dict):
        raise TARaiCriteriaApprovalError(
            "Stored approval record is invalid."
        )

    if approval.get("approved_by") != record.actor_username:
        raise TARaiCriteriaApprovalError(
            "Approval actor does not match the audit record."
        )

    if approval.get("sha256") != record.target_id:
        raise TARaiCriteriaApprovalError(
            "Approval identity does not match the audit record."
        )

    return validate_criteria_approval(
        criteria_bytes=criteria_bytes,
        approval=approval,
        client=client,
        project=project,
    )