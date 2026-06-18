import json
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.batch_service import get_container_client
from app.database.connection import get_db
from app.models.user import User


router = APIRouter(prefix="/api/timesheet", tags=["Timesheet"])


class TimeRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    display_name: str | None = None
    role: str | None = None


class ManualEntryRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    username: str
    display_name: str | None = None
    role: str | None = None
    date: str
    login: str = ""
    logout: str = ""
    break_minutes: int = 0
    hours: float = 0
    notes: str = ""
    edited_by: str | None = None
    
class ReviewHoursClockRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    username: str
    display_name: str | None = None
    role: str | None = None
    date: str
    logout_reason: str = "manual"
    auto_logout_at: str | None = None


def get_entries_blob_name(
    workspace: str,
    client_id: str,
    project_id: str,
):
    clean_workspace = workspace.strip("/")
    clean_client = client_id.strip("/")
    clean_project = project_id.strip("/")

    return (
        f"{clean_client}/"
        f"{clean_workspace}/"
        f"{clean_project}/"
        f"ReviewHours/time_entries.json"
    )


def load_entries(workspace: str, client_id: str, project_id: str):
    container = get_container_client(workspace)

    blob_name = get_entries_blob_name(
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return []

    data = blob_client.download_blob().readall()

    try:
        entries = json.loads(data.decode("utf-8"))
    except Exception:
        return []

    return entries if isinstance(entries, list) else []


def save_entries(
    workspace: str,
    client_id: str,
    project_id: str,
    entries: list[dict],
):
    container = get_container_client(workspace)

    blob_name = get_entries_blob_name(
        workspace=workspace,
        client_id=client_id,
        project_id=project_id,
    )

    container.upload_blob(
        name=blob_name,
        data=json.dumps(entries, indent=2),
        overwrite=True,
    )


def parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def monday_for(value: date):
    return value - timedelta(days=value.weekday())


def sunday_for(monday: date):
    return monday + timedelta(days=6)


def now_utc():
    return datetime.now(timezone.utc)


def current_date_string():
    return now_utc().date().isoformat()


def current_time_string():
    return now_utc().strftime("%H:%M")

INACTIVITY_TIMEOUT_MINUTES = 10


def parse_iso_datetime(value: str | None):
    if not value:
        return now_utc()

    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def get_effective_review_hours_logout_time(
    logout_reason: str,
    auto_logout_at: str | None,
):
    actual_logout_at = parse_iso_datetime(auto_logout_at)

    if logout_reason == "inactivity_timeout":
        effective_logout_at = actual_logout_at - timedelta(
            minutes=INACTIVITY_TIMEOUT_MINUTES
        )
        inactive_minutes_deducted = INACTIVITY_TIMEOUT_MINUTES
    else:
        effective_logout_at = actual_logout_at
        inactive_minutes_deducted = 0

    return effective_logout_at, actual_logout_at, inactive_minutes_deducted


def calculate_hours(login_iso: str, logout_iso: str, break_minutes: int):
    if not login_iso or not logout_iso:
        return 0.0

    start = datetime.fromisoformat(login_iso)
    end = datetime.fromisoformat(logout_iso)

    total_hours = (end - start).total_seconds() / 3600
    total_hours -= (break_minutes or 0) / 60

    return max(round(total_hours, 2), 0)

def safe_json_list(value: str):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def normalize_access_value(value: str):
    return str(value or "").strip().lower()


def user_has_project_access(
    user: User,
    workspace: str,
    client_id: str,
    project_id: str,
):
    workspace_access = safe_json_list(user.workspace_access)
    client_access = safe_json_list(user.client_access)
    project_access = safe_json_list(user.project_access)

    clean_workspace = normalize_access_value(workspace)
    clean_client = normalize_access_value(client_id)
    clean_project = normalize_access_value(project_id)
    clean_project_path = normalize_access_value(
        f"{client_id}/{project_id}"
    )

    has_workspace = (
        "ALL" in workspace_access
        or workspace in workspace_access
        or clean_workspace in [
            normalize_access_value(item)
            for item in workspace_access
        ]
    )

    has_client = (
        "ALL" in client_access
        or client_id in client_access
        or clean_client in [
            normalize_access_value(item)
            for item in client_access
        ]
    )

    has_project = (
        "ALL" in project_access
        or project_id in project_access
        or f"{client_id}/{project_id}" in project_access
        or clean_project in [
            normalize_access_value(item)
            for item in project_access
        ]
        or clean_project_path in [
            normalize_access_value(item)
            for item in project_access
        ]
    )

    return has_workspace and has_client and has_project


def make_empty_review_hours_row(user: User):
    return {
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role or "",
        "mon_hours": 0,
        "tue_hours": 0,
        "wed_hours": 0,
        "thu_hours": 0,
        "fri_hours": 0,
        "sat_hours": 0,
        "sun_hours": 0,
        "week_total": 0,
        "details": [],
    }


def load_project_1l_reviewers(
    db: Session,
    workspace: str,
    client_id: str,
    project_id: str,
):
    users = (
        db.query(User)
        .filter(User.status == "Active")
        .all()
    )

    reviewers = []

    for user in users:
        role = str(user.role or "").strip()

        if role not in ["1L", "1L Reviewer"]:
            continue

        if user_has_project_access(
            user=user,
            workspace=workspace,
            client_id=client_id,
            project_id=project_id,
        ):
            reviewers.append(user)

    reviewers.sort(
        key=lambda item: (
            item.display_name or item.username or ""
        ).lower()
    )

    return reviewers

def get_role_bucket(role: str):
    clean = str(role or "").strip()

    if clean in ["1L", "1L Reviewer"]:
        return "one_l"

    if clean == "QC":
        return "qc"

    if clean == "TL":
        return "tl"

    if clean == "RM":
        return "rm"

    return "other"


def make_empty_project_hours_row(
    workspace: str,
    client_id: str,
    project_id: str,
):
    return {
        "workspace": workspace,
        "client_id": client_id,
        "project_id": project_id,

        "project_total": 0,
        "one_l_project_total": 0,
        "qc_project_total": 0,
        "tl_project_total": 0,
        "rm_project_total": 0,

        "weekly_totals": {},
    }


def make_empty_weekly_hours_row(week_ending: str):
    return {
        "week_ending": week_ending,
        "project_weekly_total": 0,
        "one_l_weekly_total": 0,
        "qc_weekly_total": 0,
        "tl_weekly_total": 0,
        "rm_weekly_total": 0,
    }


def add_hours_to_project_row(
    row: dict,
    role: str,
    hours: float,
):
    row["project_total"] += hours

    bucket = get_role_bucket(role)

    if bucket == "one_l":
        row["one_l_project_total"] += hours
    elif bucket == "qc":
        row["qc_project_total"] += hours
    elif bucket == "tl":
        row["tl_project_total"] += hours
    elif bucket == "rm":
        row["rm_project_total"] += hours


def add_hours_to_weekly_row(
    row: dict,
    role: str,
    hours: float,
):
    row["project_weekly_total"] += hours

    bucket = get_role_bucket(role)

    if bucket == "one_l":
        row["one_l_weekly_total"] += hours
    elif bucket == "qc":
        row["qc_weekly_total"] += hours
    elif bucket == "tl":
        row["tl_weekly_total"] += hours
    elif bucket == "rm":
        row["rm_weekly_total"] += hours


def get_week_ending_for_entry_date(entry_date: date):
    week_monday = monday_for(entry_date)
    week_sunday = sunday_for(week_monday)

    return week_sunday.isoformat()


def parse_review_hours_blob_path(
    blob_name: str,
    workspace: str,
):
    parts = blob_name.split("/")

    if len(parts) < 4:
        return None

    if parts[-2] != "ReviewHours":
        return None

    if parts[-1] != "time_entries.json":
        return None

    clean_workspace = str(workspace or "").strip("/")

    # Canonical path:
    # {client}/{workspace}/{project}/ReviewHours/time_entries.json
    if len(parts) >= 5 and parts[-4] == clean_workspace:
        return {
            "client_id": parts[-5],
            "project_id": parts[-3],
            "path_style": "canonical",
        }

    # If this looks like a canonical INSYT path for a different workspace,
    # do not treat it as legacy.
    if len(parts) >= 5 and parts[-4] in [
        "capture",
        "summaries",
        "discovery",
    ]:
        return None

    # Legacy path:
    # {client}/{project}/ReviewHours/time_entries.json
    if len(parts) >= 4:
        return {
            "client_id": parts[-4],
            "project_id": parts[-3],
            "path_style": "legacy",
        }

    return None


def round_project_hours_row(row: dict):
    row["project_total"] = round(float(row["project_total"] or 0), 2)
    row["one_l_project_total"] = round(float(row["one_l_project_total"] or 0), 2)
    row["qc_project_total"] = round(float(row["qc_project_total"] or 0), 2)
    row["tl_project_total"] = round(float(row["tl_project_total"] or 0), 2)
    row["rm_project_total"] = round(float(row["rm_project_total"] or 0), 2)

    weekly_rows = []

    for week_row in row["weekly_totals"].values():
        week_row["project_weekly_total"] = round(
            float(week_row["project_weekly_total"] or 0),
            2,
        )
        week_row["one_l_weekly_total"] = round(
            float(week_row["one_l_weekly_total"] or 0),
            2,
        )
        week_row["qc_weekly_total"] = round(
            float(week_row["qc_weekly_total"] or 0),
            2,
        )
        week_row["tl_weekly_total"] = round(
            float(week_row["tl_weekly_total"] or 0),
            2,
        )
        week_row["rm_weekly_total"] = round(
            float(week_row["rm_weekly_total"] or 0),
            2,
        )

        weekly_rows.append(week_row)

    weekly_rows.sort(
        key=lambda item: item.get("week_ending") or "",
        reverse=True,
    )

    row["weekly_totals"] = weekly_rows

    return row

@router.get("/")
def list_time(
    workspace: str = Query(...),
    client: str = Query(...),
    project: str = Query(...),
    username: str = Query(default=""),
    x_username: str = Header(default=""),
):
    current_user = username or x_username

    entries = load_entries(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    return [
        entry for entry in entries
        if entry.get("username") == current_user
    ]

@router.get("/project-hours-summary")
def project_hours_summary(
    workspace: str = Query(default=""),
    client: str = Query(default=""),
    project: str = Query(default=""),
):
    requested_workspace = str(workspace or "").strip().lower()
    clean_client = str(client or "").strip()
    clean_project = str(project or "").strip()

    if requested_workspace in ["", "all"]:
        workspaces_to_scan = ["capture", "summaries", "discovery"]
    elif requested_workspace in ["capture", "summaries", "discovery"]:
        workspaces_to_scan = [requested_workspace]
    else:
        raise HTTPException(
            status_code=400,
            detail="Workspace must be capture, summaries, discovery, or all.",
        )

    rows_by_project: dict[str, dict] = {}
    all_week_endings = set()

    for active_workspace in workspaces_to_scan:
        container = get_container_client(active_workspace)

        for blob in container.list_blobs():
            blob_name = blob.name

            if not blob_name.endswith("/ReviewHours/time_entries.json"):
                continue

            parsed_path = parse_review_hours_blob_path(
                blob_name=blob_name,
                workspace=active_workspace,
            )

            if not parsed_path:
                continue

            client_id = parsed_path["client_id"]
            project_id = parsed_path["project_id"]

            if clean_client and client_id != clean_client:
                continue

            if clean_project and project_id != clean_project:
                continue

            blob_client = container.get_blob_client(blob_name)

            try:
                data = blob_client.download_blob().readall()
                entries = json.loads(data.decode("utf-8"))
            except Exception:
                entries = []

            if not isinstance(entries, list):
                entries = []

            row_key = f"{active_workspace}/{client_id}/{project_id}"

            if row_key not in rows_by_project:
                rows_by_project[row_key] = make_empty_project_hours_row(
                    workspace=active_workspace,
                    client_id=client_id,
                    project_id=project_id,
                )

            row = rows_by_project[row_key]

            for entry in entries:
                hours = float(entry.get("hours") or 0)

                if hours <= 0:
                    continue

                role = entry.get("role") or ""
                entry_date_raw = entry.get("date") or ""

                try:
                    entry_date = parse_date(entry_date_raw)
                except Exception:
                    continue

                week_ending = get_week_ending_for_entry_date(entry_date)
                all_week_endings.add(week_ending)

                add_hours_to_project_row(
                    row=row,
                    role=role,
                    hours=hours,
                )

                if week_ending not in row["weekly_totals"]:
                    row["weekly_totals"][week_ending] = (
                        make_empty_weekly_hours_row(week_ending)
                    )

                add_hours_to_weekly_row(
                    row=row["weekly_totals"][week_ending],
                    role=role,
                    hours=hours,
                )

    rows = [
        round_project_hours_row(row)
        for row in rows_by_project.values()
    ]

    rows.sort(
        key=lambda item: (
            item.get("workspace") or "",
            item.get("client_id") or "",
            item.get("project_id") or "",
        )
    )

    week_endings = sorted(
        list(all_week_endings),
        reverse=True,
    )

    return {
        "workspace": requested_workspace or "all",
        "client": clean_client,
        "project": clean_project,
        "week_endings": week_endings,
        "rows": rows,
    }


@router.post("/clock-in")
def clock_in(
    payload: TimeRequest,
    x_username: str = Header(default=""),
):
    username = x_username or "Unknown User"

    if username == "Unknown User":
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    entries = load_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    open_entry = next(
        (
            entry for entry in reversed(entries)
            if entry.get("username") == username
            and not entry.get("logout_at")
        ),
        None,
    )

    if open_entry:
        return {
            "status": "already_clocked_in",
            "entry": open_entry,
        }

    now = now_utc()

    entry = {
        "entry_id": str(uuid.uuid4()),
        "workspace": payload.workspace,
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "username": username,
        "display_name": payload.display_name or username,
        "role": payload.role or "",
        "date": now.date().isoformat(),
        "login": now.strftime("%H:%M"),
        "logout": "",
        "login_at": now.isoformat(),
        "logout_at": "",
        "break_minutes": 0,
        "hours": 0,
        "notes": "",
        "source": "clock",
        "created_at": now.isoformat(),
        "edited_by": "",
        "edited_at": "",
    }

    entries.append(entry)

    save_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        entries=entries,
    )

    return {
        "status": "clocked_in",
        "entry": entry,
    }


@router.post("/clock-out")
def clock_out(
    payload: TimeRequest,
    x_username: str = Header(default=""),
):
    username = x_username or "Unknown User"

    if username == "Unknown User":
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    entries = load_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    now = now_utc()

    for entry in reversed(entries):
        if (
            entry.get("username") == username
            and not entry.get("logout_at")
        ):
            entry["logout"] = now.strftime("%H:%M")
            entry["logout_at"] = now.isoformat()
            entry["hours"] = calculate_hours(
                entry.get("login_at", ""),
                entry.get("logout_at", ""),
                int(entry.get("break_minutes") or 0),
            )

            save_entries(
                workspace=payload.workspace,
                client_id=payload.client_id,
                project_id=payload.project_id,
                entries=entries,
            )

            return {
                "status": "clocked_out",
                "entry": entry,
            }

    return {
        "status": "no_active_session",
    }


@router.get("/review-hours")
def review_hours(
    workspace: str = Query(...),
    client: str = Query(...),
    project: str = Query(...),
    week_start: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    entries = load_entries(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    selected_monday = (
        parse_date(week_start)
        if week_start
        else monday_for(now_utc().date())
    )

    selected_sunday = sunday_for(selected_monday)

    days = [
        ("mon_hours", selected_monday),
        ("tue_hours", selected_monday + timedelta(days=1)),
        ("wed_hours", selected_monday + timedelta(days=2)),
        ("thu_hours", selected_monday + timedelta(days=3)),
        ("fri_hours", selected_monday + timedelta(days=4)),
        ("sat_hours", selected_monday + timedelta(days=5)),
        ("sun_hours", selected_monday + timedelta(days=6)),
    ]

    grouped: dict[str, dict] = {}

    assigned_reviewers = load_project_1l_reviewers(
        db=db,
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    for reviewer in assigned_reviewers:
        grouped[reviewer.username] = make_empty_review_hours_row(
            reviewer
        )

    for entry in entries:
        entry_date_raw = entry.get("date")

        if not entry_date_raw:
            continue

        try:
            entry_date = parse_date(entry_date_raw)
        except Exception:
            continue

        if entry_date < selected_monday or entry_date > selected_sunday:
            continue

        username = entry.get("username") or "Unknown User"

        if username not in grouped:
            grouped[username] = {
                "username": username,
                "display_name": entry.get("display_name") or username,
                "role": entry.get("role") or "",
                "mon_hours": 0,
                "tue_hours": 0,
                "wed_hours": 0,
                "thu_hours": 0,
                "fri_hours": 0,
                "sat_hours": 0,
                "sun_hours": 0,
                "week_total": 0,
                "details": [],
            }

        hours = float(entry.get("hours") or 0)

        for key, day_date in days:
            if entry_date == day_date:
                grouped[username][key] += hours

        grouped[username]["week_total"] += hours
        grouped[username]["details"].append(entry)

    rows = list(grouped.values())

    for row in rows:
        for key, _day_date in days:
            row[key] = round(float(row[key] or 0), 2)

        row["week_total"] = round(float(row["week_total"] or 0), 2)

    rows.sort(key=lambda item: item.get("display_name") or item.get("username"))

    return {
        "workspace": workspace,
        "client_id": client,
        "project_id": project,
        "week_start": selected_monday.isoformat(),
        "week_end": selected_sunday.isoformat(),
        "rows": rows,
    }
    
@router.post("/review-hours/login")
def review_hours_login(payload: ReviewHoursClockRequest):
    if not payload.username:
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    try:
        parse_date(payload.date)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Date must be in YYYY-MM-DD format.",
        )

    entries = load_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    open_entry = next(
        (
            entry for entry in reversed(entries)
            if entry.get("username") == payload.username
            and entry.get("date") == payload.date
            and not entry.get("logout_at")
        ),
        None,
    )

    if open_entry:
        return {
            "status": "already_logged_in",
            "message": "User is already logged in for this date.",
            "entry": open_entry,
        }

    now = now_utc()

    entry = {
        "entry_id": str(uuid.uuid4()),
        "workspace": payload.workspace,
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "username": payload.username,
        "display_name": payload.display_name or payload.username,
        "role": payload.role or "",
        "date": payload.date,
        "login": now.strftime("%H:%M"),
        "logout": "",
        "login_at": now.isoformat(),
        "logout_at": "",
        "break_minutes": 0,
        "hours": 0,
        "notes": "",
        "source": "review_hours_login",
        "created_at": now.isoformat(),
        "edited_by": "",
        "edited_at": "",
    }

    entries.append(entry)

    save_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        entries=entries,
    )

    return {
        "status": "logged_in",
        "message": "Review hours login recorded.",
        "entry": entry,
    }

@router.post("/review-hours/logout")
def review_hours_logout(payload: ReviewHoursClockRequest):
    if not payload.username:
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    try:
        parse_date(payload.date)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Date must be in YYYY-MM-DD format.",
        )

    entries = load_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    (
        effective_logout_at,
        actual_logout_at,
        inactive_minutes_deducted,
    ) = get_effective_review_hours_logout_time(
        logout_reason=payload.logout_reason,
        auto_logout_at=payload.auto_logout_at,
    )

    target_entry = None

    # First try to close the active entry for the requested date.
    for entry in reversed(entries):
        if (
            entry.get("username") == payload.username
            and entry.get("date") == payload.date
            and not entry.get("logout_at")
        ):
            target_entry = entry
            break

    # Auto logout fallback:
    # If the browser has a stale/missing date in localStorage, still close the
    # latest open Review Hours entry for this reviewer in this project.
    if target_entry is None and payload.logout_reason == "inactivity_timeout":
        for entry in reversed(entries):
            if (
                entry.get("username") == payload.username
                and not entry.get("logout_at")
            ):
                target_entry = entry
                break

    if target_entry is None:
        raise HTTPException(
            status_code=400,
            detail="No active review-hours login found for this user and date.",
        )

    # Do not allow effective logout to be before login.
    login_at_raw = target_entry.get("login_at") or ""
    try:
        login_at = datetime.fromisoformat(login_at_raw)
        if login_at.tzinfo is None:
            login_at = login_at.replace(tzinfo=timezone.utc)

        if effective_logout_at < login_at:
            effective_logout_at = login_at
    except Exception:
        pass

    target_entry["logout"] = effective_logout_at.strftime("%H:%M")
    target_entry["logout_at"] = effective_logout_at.isoformat()
    target_entry["actual_logout_event_at"] = actual_logout_at.isoformat()
    target_entry["logout_reason"] = payload.logout_reason
    target_entry["inactive_minutes_deducted"] = inactive_minutes_deducted
    target_entry["current"] = False
    target_entry["is_active"] = False
    target_entry["status"] = "Logged Out"

    target_entry["hours"] = calculate_hours(
        target_entry.get("login_at", ""),
        target_entry.get("logout_at", ""),
        int(target_entry.get("break_minutes") or 0),
    )

    target_entry["display_name"] = (
        target_entry.get("display_name")
        or payload.display_name
        or payload.username
    )
    target_entry["role"] = target_entry.get("role") or payload.role or ""

    if payload.logout_reason == "inactivity_timeout":
        target_entry["source"] = "inactivity_timeout"
        target_entry["notes"] = (
            target_entry.get("notes")
            or f"Auto logout due to inactivity; "
            f"{inactive_minutes_deducted} inactive minutes deducted."
        )
    else:
        target_entry["source"] = (
            target_entry.get("source")
            or "review_hours_login"
        )

    save_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        entries=entries,
    )

    return {
        "status": "logged_out",
        "message": "Review hours logout recorded.",
        "entry": target_entry,
    }
    

@router.post("/review-hours/edit")
def edit_review_hours(payload: ManualEntryRequest):
    entries = load_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    edited_at = now_utc().isoformat()

    entry = {
        "entry_id": str(uuid.uuid4()),
        "workspace": payload.workspace,
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "username": payload.username,
        "display_name": payload.display_name or payload.username,
        "role": payload.role or "",
        "date": payload.date,
        "login": payload.login,
        "logout": payload.logout,
        "login_at": "",
        "logout_at": "",
        "break_minutes": payload.break_minutes,
        "hours": round(float(payload.hours or 0), 2),
        "notes": payload.notes,
        "source": "manual_edit",
        "created_at": edited_at,
        "edited_by": payload.edited_by or "",
        "edited_at": edited_at,
    }

    entries.append(entry)

    save_entries(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        entries=entries,
    )

    return {
        "status": "saved",
        "entry": entry,
    }