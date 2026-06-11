import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.batch_service import get_container_client


router = APIRouter(prefix="/api/messages", tags=["Messages"])


ADMIN_ROLES = {
    "QC",
    "TL",
    "RM",
    "Admin",
    "INSYT Admin",
    "CDS Admin",
}

ADMIN_ALERT_ROLES = {
    "RM",
    "Admin",
    "INSYT Admin",
    "CDS Admin",
}

ChannelType = Literal["project", "admin", "private"]


class MessageCreateRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    channel: ChannelType = "project"

    sender_username: str
    sender_display_name: str | None = None
    sender_role: str | None = None

    recipient_usernames: list[str] = []
    message: str

    parent_message_id: str | None = None
    forwarded_from_message_id: str | None = None
    forwarded_from_sender: str | None = None
    forwarded_body: str | None = None
    
    important: bool = False
    urgent: bool = False
    
class UrgentAcknowledgeRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    message_id: str
    username: str
    display_name: str | None = None
    
class MessageSeenRequest(BaseModel):
    workspace: str
    client_id: str
    project_id: str
    username: str


def get_messages_blob_name(
    client_id: str,
    project_id: str,
):
    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")

    return f"{clean_client_id}/{clean_project_id}/Messaging/messages.json"


def load_messages(
    workspace: str,
    client_id: str,
    project_id: str,
):
    container = get_container_client(workspace)

    blob_name = get_messages_blob_name(
        client_id=client_id,
        project_id=project_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return []

    data = blob_client.download_blob().readall()

    try:
        messages = json.loads(data.decode("utf-8"))
    except Exception:
        messages = []

    if not isinstance(messages, list):
        return []

    return messages


def save_messages(
    workspace: str,
    client_id: str,
    project_id: str,
    messages: list[dict],
):
    container = get_container_client(workspace)

    blob_name = get_messages_blob_name(
        client_id=client_id,
        project_id=project_id,
    )

    container.upload_blob(
        name=blob_name,
        data=json.dumps(messages, indent=2),
        overwrite=True,
    )
    
def get_message_seen_blob_name(
    client_id: str,
    project_id: str,
    username: str,
):
    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")
    clean_username = username.strip().lower()

    return (
        f"{clean_client_id}/{clean_project_id}/Messaging/"
        f"seen/{clean_username}.json"
    )


def load_message_seen(
    workspace: str,
    client_id: str,
    project_id: str,
    username: str,
):
    container = get_container_client(workspace)

    blob_name = get_message_seen_blob_name(
        client_id=client_id,
        project_id=project_id,
        username=username,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return {}

    data = blob_client.download_blob().readall()

    try:
        seen_data = json.loads(data.decode("utf-8"))
    except Exception:
        return {}

    return seen_data if isinstance(seen_data, dict) else {}


def save_message_seen(
    workspace: str,
    client_id: str,
    project_id: str,
    username: str,
    seen_data: dict,
):
    container = get_container_client(workspace)

    blob_name = get_message_seen_blob_name(
        client_id=client_id,
        project_id=project_id,
        username=username,
    )

    container.upload_blob(
        name=blob_name,
        data=json.dumps(seen_data, indent=2),
        overwrite=True,
    )


def can_view_message(
    message: dict,
    username: str,
    role: str,
):
    channel = message.get("channel")

    if channel == "project":
        return True

    if channel == "admin":
        return role in ADMIN_ROLES

    if channel == "private":
        sender = message.get("sender_username")
        recipients = message.get("recipient_usernames") or []

        return username == sender or username in recipients

    return False


def get_ack_blob_name(
    client_id: str,
    project_id: str,
):
    clean_client_id = client_id.strip("/")
    clean_project_id = project_id.strip("/")

    return f"{clean_client_id}/{clean_project_id}/Messaging/urgent_acknowledgements.json"


def load_acknowledgements(
    workspace: str,
    client_id: str,
    project_id: str,
):
    container = get_container_client(workspace)

    blob_name = get_ack_blob_name(
        client_id=client_id,
        project_id=project_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return []

    data = blob_client.download_blob().readall()

    try:
        items = json.loads(data.decode("utf-8"))
    except Exception:
        return []

    return items if isinstance(items, list) else []


def save_acknowledgements(
    workspace: str,
    client_id: str,
    project_id: str,
    items: list[dict],
):
    container = get_container_client(workspace)

    blob_name = get_ack_blob_name(
        client_id=client_id,
        project_id=project_id,
    )

    container.upload_blob(
        name=blob_name,
        data=json.dumps(items, indent=2),
        overwrite=True,
    )

@router.get("/")
def list_messages(
    workspace: str = Query(...),
    client: str = Query(...),
    project: str = Query(...),
    channel: str = Query(default="project"),
    username: str = Query(...),
    role: str = Query(default=""),
):
    messages = load_messages(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    visible_messages = [
        message
        for message in messages
        if message.get("channel") == channel
        and can_view_message(
            message=message,
            username=username,
            role=role,
        )
    ]

    visible_messages.sort(
        key=lambda item: item.get("created_at", "")
    )

    return {
        "messages": visible_messages,
    }

@router.get("/new-status")
def message_new_status(
    workspace: str = Query(...),
    client: str = Query(...),
    project: str = Query(...),
    username: str = Query(...),
    role: str = Query(default=""),
):
    messages = load_messages(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    visible_messages = [
        message
        for message in messages
        if can_view_message(
            message=message,
            username=username,
            role=role,
        )
        and message.get("sender_username") != username
    ]

    latest_message_at = ""

    for message in visible_messages:
        created_at = message.get("created_at") or ""

        if created_at > latest_message_at:
            latest_message_at = created_at

    seen_data = load_message_seen(
        workspace=workspace,
        client_id=client,
        project_id=project,
        username=username,
    )

    last_seen_at = seen_data.get("last_seen_at") or ""

    return {
        "has_new_messages": bool(
            latest_message_at and latest_message_at > last_seen_at
        ),
        "latest_message_at": latest_message_at,
        "last_seen_at": last_seen_at,
    }

@router.post("/mark-seen")
def mark_messages_seen(payload: MessageSeenRequest):
    if not payload.workspace:
        raise HTTPException(
            status_code=400,
            detail="Workspace is required.",
        )

    if not payload.client_id:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not payload.project_id:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not payload.username:
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    seen_at = datetime.now(timezone.utc).isoformat()

    seen_data = {
        "workspace": payload.workspace,
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "username": payload.username,
        "last_seen_at": seen_at,
    }

    save_message_seen(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        username=payload.username,
        seen_data=seen_data,
    )

    return {
        "status": "seen",
        "last_seen_at": seen_at,
    }

@router.post("/send")
def send_message(payload: MessageCreateRequest):
    body = payload.message.strip()

    if not body:
        raise HTTPException(
            status_code=400,
            detail="Message body is required.",
        )

    if payload.channel == "admin" and payload.sender_role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only admin team users can send admin messages.",
        )

    if payload.channel == "private" and not payload.recipient_usernames:
        raise HTTPException(
            status_code=400,
            detail="At least one private recipient is required.",
        )
        
    if (payload.important or payload.urgent) and payload.sender_role not in ADMIN_ALERT_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only RM, Admin, INSYT Admin, or CDS Admin users can send Important or Urgent messages.",
        )

    messages = load_messages(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    now = datetime.now(timezone.utc).isoformat()

    message = {
        "message_id": str(uuid.uuid4()),
        "workspace": payload.workspace,
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "channel": payload.channel,
        "sender_username": payload.sender_username,
        "sender_display_name": payload.sender_display_name
        or payload.sender_username,
        "sender_role": payload.sender_role or "",
        "recipient_usernames": payload.recipient_usernames or [],
        "message": body,
        "parent_message_id": payload.parent_message_id or "",
        "forwarded_from_message_id": payload.forwarded_from_message_id or "",
        "forwarded_from_sender": payload.forwarded_from_sender or "",
        "forwarded_body": payload.forwarded_body or "",
        "created_at": now,
        "important": payload.important,
        "urgent": payload.urgent,
        "acknowledged_by": [],
    }

    messages.append(message)

    save_messages(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
        messages=messages,
    )

    return {
        "status": "sent",
        "message": message,
    }
    
@router.get("/urgent")
def get_urgent_messages(
    workspace: str = Query(...),
    client: str = Query(...),
    project: str = Query(...),
    username: str = Query(...),
    role: str = Query(default=""),
):
    messages = load_messages(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    acknowledgements = load_acknowledgements(
        workspace=workspace,
        client_id=client,
        project_id=project,
    )

    acknowledged_ids = {
        item.get("message_id")
        for item in acknowledgements
        if item.get("username") == username
    }

    urgent_messages = [
        message
        for message in messages
        if message.get("urgent")
        and message.get("message_id") not in acknowledged_ids
        and can_view_message(
            message=message,
            username=username,
            role=role,
        )
    ]

    urgent_messages.sort(
        key=lambda item: item.get("created_at", "")
    )

    return {
        "messages": urgent_messages,
    }


@router.post("/urgent/acknowledge")
def acknowledge_urgent_message(payload: UrgentAcknowledgeRequest):
    acknowledgements = load_acknowledgements(
        workspace=payload.workspace,
        client_id=payload.client_id,
        project_id=payload.project_id,
    )

    already_acknowledged = any(
        item.get("message_id") == payload.message_id
        and item.get("username") == payload.username
        for item in acknowledgements
    )

    if not already_acknowledged:
        acknowledgements.append({
            "message_id": payload.message_id,
            "username": payload.username,
            "display_name": payload.display_name or payload.username,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        })

        save_acknowledgements(
            workspace=payload.workspace,
            client_id=payload.client_id,
            project_id=payload.project_id,
            items=acknowledgements,
        )

    return {
        "status": "acknowledged",
    }