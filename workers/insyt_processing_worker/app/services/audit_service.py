import json
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    action: str,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
    target_type: str = "",
    target_id: str = "",
    workspace: str = "",
    client: str = "",
    project: str = "",
    details: Optional[dict[str, Any]] = None,
):
    log = AuditLog(
        actor_username=actor.username if actor else "",
        actor_email=actor.email if actor else "",
        actor_role=actor.role if actor else "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        workspace=workspace,
        client=client,
        project=project,
        ip_address=request.client.host if request and request.client else "",
        user_agent=request.headers.get("user-agent", "") if request else "",
        details=json.dumps(details or {}),
    )

    db.add(log)
    db.commit()

    return log