from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.user import User
from app.services.security import get_current_user


router = APIRouter(
    prefix="/api/reviewer-hours",
    tags=["reviewer-hours"],
)


INACTIVITY_TIMEOUT_MINUTES = 10


class ReviewerLogoutPayload(BaseModel):
    logout_reason: str = "manual"
    auto_logout_at: str | None = None


def parse_iso_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


@router.post("/logout")
def logout_reviewer_hours(
    payload: ReviewerLogoutPayload,
    current_user: User = Depends(get_current_user),
):
    username = (
        current_user.username
        or current_user.email
        or current_user.display_name
    )

    if not username:
        raise HTTPException(status_code=401, detail="Unable to identify reviewer.")

    actual_logout_at = parse_iso_datetime(payload.auto_logout_at)

    logout_reason = payload.logout_reason or "manual"

    if logout_reason == "inactivity_timeout":
        effective_logout_at = actual_logout_at - timedelta(
            minutes=INACTIVITY_TIMEOUT_MINUTES
        )
        inactive_minutes_deducted = INACTIVITY_TIMEOUT_MINUTES
    else:
        effective_logout_at = actual_logout_at
        inactive_minutes_deducted = 0

    # TODO:
    # Replace this section with however Reviewer Hours sessions are currently stored.
    # We need to find the reviewer’s currently open session and update it.
    open_session = None

    if not open_session:
        return {
            "status": "already_logged_out",
            "logout_reason": logout_reason,
        }

    login_at = parse_iso_datetime(open_session.get("login_at"))

    total_minutes = max(
        0,
        int((effective_logout_at - login_at).total_seconds() / 60),
    )

    open_session["logout_at"] = effective_logout_at.isoformat()
    open_session["actual_logout_event_at"] = actual_logout_at.isoformat()
    open_session["logout_reason"] = logout_reason
    open_session["inactive_minutes_deducted"] = inactive_minutes_deducted
    open_session["total_minutes"] = total_minutes
    open_session["status"] = "closed"

    # TODO:
    # Save updated Reviewer Hours record back to storage/database.

    return {
        "status": "logged_out",
        "login_at": login_at.isoformat(),
        "logout_at": effective_logout_at.isoformat(),
        "actual_logout_event_at": actual_logout_at.isoformat(),
        "logout_reason": logout_reason,
        "inactive_minutes_deducted": inactive_minutes_deducted,
        "total_minutes": total_minutes,
    }