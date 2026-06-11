import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.security import require_admin


router = APIRouter(
    prefix="/api/audit-logs",
    tags=["Audit Logs"],
)


def serialize_audit_log(log: AuditLog):
    try:
        details = json.loads(log.details or "{}")
    except Exception:
        details = {}

    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat()
        if log.timestamp
        else None,
        "actor_username": log.actor_username,
        "actor_email": log.actor_email,
        "actor_role": log.actor_role,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "workspace": log.workspace,
        "client": log.client,
        "project": log.project,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "details": details,
    }


@router.get("/")
def list_audit_logs(
    action: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    target_id: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)

    if actor:
        query = query.filter(
            AuditLog.actor_username.ilike(f"%{actor}%")
        )

    if target_id:
        query = query.filter(
            AuditLog.target_id.ilike(f"%{target_id}%")
        )

    logs = (
        query
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "success",
        "logs": [serialize_audit_log(log) for log in logs],
    }