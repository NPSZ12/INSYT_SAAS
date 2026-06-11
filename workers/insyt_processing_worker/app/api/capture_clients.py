import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.batch_service import get_container_client
from app.services.security import require_admin


router = APIRouter(
    prefix="/api/capture/clients",
    tags=["capture-clients"],
)


class RemoveUserRequest(BaseModel):
    project_id: str
    username: str


def get_project_client_map():
    container = get_container_client("capture")

    project_client_map = {}

    for blob in container.list_blobs():
        parts = blob.name.split("/")

        if not parts:
            continue

        project_id = parts[0]

        if not project_id:
            continue

        if project_id not in project_client_map:
            project_client_map[project_id] = "Unassigned Client"

        if blob.name.endswith("project.json"):
            try:
                data = container.get_blob_client(blob.name).download_blob().readall()
                metadata = json.loads(data.decode("utf-8"))

                project_client_map[project_id] = (
                    metadata.get("client_name")
                    or metadata.get("client")
                    or "Unassigned Client"
                )
            except Exception:
                pass

    return project_client_map


@router.get("/")
def list_capture_clients(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    project_client_map = get_project_client_map()

    users = db.query(User).all()

    client_projects = defaultdict(lambda: defaultdict(list))

    for project_id, client_name in project_client_map.items():
        client_projects[client_name][project_id] = []

    for user in users:
        try:
            project_access = json.loads(user.project_access or "[]")
        except Exception:
            project_access = []

        for project_id in project_access:
            client_name = project_client_map.get(
                project_id,
                "Unassigned Client",
            )

            client_projects[client_name][project_id].append(
                {
                    "username": user.username,
                    "display_name": user.display_name,
                    "email": user.email,
                    "role": user.role,
                    "status": user.status,
                }
            )

    clients = []

    for client_name in sorted(client_projects.keys()):
        projects = []

        for project_id in sorted(client_projects[client_name].keys()):
            users_for_project = client_projects[client_name][project_id]

            users_for_project = sorted(
                users_for_project,
                key=lambda item: (
                    item.get("role", ""),
                    item.get("display_name", ""),
                ),
            )

            projects.append(
                {
                    "project_id": project_id,
                    "users": users_for_project,
                }
            )

        clients.append(
            {
                "client_name": client_name,
                "projects": projects,
            }
        )

    return {
        "clients": clients,
    }


@router.post("/remove-user")
def remove_user_from_capture_project(
    payload: RemoveUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    try:
        project_access = json.loads(user.project_access or "[]")
    except Exception:
        project_access = []

    project_access = [
        project_id
        for project_id in project_access
        if project_id != payload.project_id
    ]

    user.project_access = json.dumps(project_access)

    db.commit()
    db.refresh(user)

    return {
        "message": "User removed from project.",
        "username": user.username,
        "project_id": payload.project_id,
        "project_access": project_access,
    }