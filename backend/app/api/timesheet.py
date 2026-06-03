import json
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.services.batch_service import get_container_client


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


def get_entries_blob_name(client_id: str, project_id: str):
    clean_client = client_id.strip("/")
    clean_project = project_id.strip("/")

    return f"{clean_client}/{clean_project}/ReviewHours/time_entries.json"


def load_entries(workspace: str, client_id: str, project_id: str):
    container = get_container_client(workspace)

    blob_name = get_entries_blob_name(
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


def calculate_hours(login_iso: str, logout_iso: str, break_minutes: int):
    if not login_iso or not logout_iso:
        return 0.0

    start = datetime.fromisoformat(login_iso)
    end = datetime.fromisoformat(logout_iso)

    total_hours = (end - start).total_seconds() / 3600
    total_hours -= (break_minutes or 0) / 60

    return max(round(total_hours, 2), 0)


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