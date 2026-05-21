from datetime import datetime
from fastapi import APIRouter, Header
from pydantic import BaseModel
from app.services.project_store import MESSAGES

router = APIRouter(prefix="/api/messages", tags=["Messages"])


class MessageCreateRequest(BaseModel):
    project_id: str
    message: str


@router.get("/")
def list_messages(project: str):
    return [
        message for message in MESSAGES
        if message["project_id"] == project
    ]


@router.post("/send")
def send_message(payload: MessageCreateRequest, x_username: str = Header(default="")):
    message = {
        "project_id": payload.project_id,
        "sender": x_username or "Unknown User",
        "time": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "message": payload.message,
    }

    MESSAGES.append(message)

    return {"status": "sent", "message": message}