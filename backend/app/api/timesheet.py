from datetime import datetime
from fastapi import APIRouter, Header
from pydantic import BaseModel
from app.services.project_store import TIME_ENTRIES

router = APIRouter(prefix="/api/timesheet", tags=["Timesheet"])


class TimeRequest(BaseModel):
    project_id: str


@router.get("/")
def list_time(project: str, x_username: str = Header(default="")):
    return [
        entry for entry in TIME_ENTRIES
        if entry["project_id"] == project and entry["username"] == x_username
    ]


@router.post("/clock-in")
def clock_in(payload: TimeRequest, x_username: str = Header(default="")):
    entry = {
        "project_id": payload.project_id,
        "username": x_username,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "clock_in": datetime.now().strftime("%I:%M %p"),
        "clock_out": "",
        "hours": "",
    }

    TIME_ENTRIES.append(entry)

    return {"status": "clocked_in", "entry": entry}


@router.post("/clock-out")
def clock_out(payload: TimeRequest, x_username: str = Header(default="")):
    for entry in reversed(TIME_ENTRIES):
        if (
            entry["project_id"] == payload.project_id
            and entry["username"] == x_username
            and not entry["clock_out"]
        ):
            entry["clock_out"] = datetime.now().strftime("%I:%M %p")
            entry["hours"] = "manual-calc-later"
            return {"status": "clocked_out", "entry": entry}

    return {"status": "no_active_session"}