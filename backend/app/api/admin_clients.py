import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.services.azure_blob_storage import get_container_client
from app.database.connection import get_db
from app.models.user import User
from app.services.security import require_admin
from sqlalchemy import func

from app.models.time_entry import TimeEntry


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Clients"],
)


ALLOWED_ROLES = ["INSYT Admin", "Admin", "RM"]


def safe_list(value):
    try:
        return json.loads(value or "[]")
    except Exception:
        return []


@router.get("/clients-overview")
def clients_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if admin.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    workspace_names = ["capture", "discovery", "summaries"]

    clients = defaultdict(
        lambda: {
            "client": "",
            "workspaces": defaultdict(
                lambda: {
                    "workspace": "",
                    "projects": defaultdict(
                        lambda: {
                            "project": "",
                            "reviewers": [],
                        }
                    ),
                }
            ),
        }
    )

    def add_project(
        client: str,
        workspace: str,
        project: str,
    ):
        if not client or not workspace or not project:
            return

        if client in [
            "source",
            "Batches",
            "SearchFolders",
            "QC",
            "Audit",
            "processing_center",
            "overlays",
        ]:
            return

        if workspace not in workspace_names and workspace != "unknown":
            return

        if project in [
            "source",
            "native",
            "natives",
            "text",
            "protocol",
            "processing_center",
            "uploads",
            "jobs",
            "preview",
            "overlays",
        ]:
            return

        client_node = clients[client]
        client_node["client"] = client

        workspace_node = client_node["workspaces"][workspace]
        workspace_node["workspace"] = workspace

        project_node = workspace_node["projects"][project]
        project_node["project"] = project

        return project_node

    def reviewer_payload(user: User):
        return {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "auth_provider": user.auth_provider,
        }

    def reviewer_already_added(project_node: dict, username: str) -> bool:
        return any(
            reviewer.get("username") == username
            for reviewer in project_node.get("reviewers", [])
        )

    def project_access_matches(
        access_key: str,
        client: str,
        workspace: str,
        project: str,
    ) -> bool:
        normalized = str(access_key or "").strip()

        if not normalized:
            return False

        possible_keys = {
            project,
            f"{client}/{project}",
            f"{workspace}/{client}/{project}",
            f"{client}/{workspace}/{project}",
        }

        return normalized in possible_keys

    # 1. Discover real clients/projects from Azure blob paths.
    #
    # Supported new path:
    #   Client1/capture/Project_Client1/source/...
    #
    # Supported older path:
    #   capture/Client1/Project_Client1/source/...
    for workspace_name in workspace_names:
        try:
            container = get_container_client(workspace_name)

            for blob in container.list_blobs():
                blob_name = blob.name or ""
                parts = [
                    part
                    for part in blob_name.split("/")
                    if part
                ]

                if len(parts) < 3:
                    continue

                # New/current path:
                # Client/workspace/project/...
                if parts[1] in workspace_names:
                    client = parts[0]
                    workspace = parts[1]
                    project = parts[2]
                    add_project(client, workspace, project)
                    continue

                # Older path:
                # workspace/client/project/...
                if parts[0] in workspace_names:
                    workspace = parts[0]
                    client = parts[1]
                    project = parts[2]
                    add_project(client, workspace, project)
                    continue

        except Exception as error:
            print(
                f"clients_overview storage scan failed for "
                f"{workspace_name}: {error}"
            )

    # 2. Merge reviewer/project access from the database.
    users = db.query(User).all()

    for user in users:
        if user.role in ["INSYT Admin", "Admin"]:
            continue

        client_access = safe_list(user.client_access)
        project_access = safe_list(user.project_access)
        workspace_access = safe_list(user.workspace_access)

        if not project_access:
            continue

        user_workspaces = workspace_access or ["unknown"]

        for access_key in project_access:
            access_key = str(access_key or "").strip()

            if not access_key:
                continue

            parsed_client = None
            parsed_workspace = None
            parsed_project = None

            parts = [
                part
                for part in access_key.split("/")
                if part
            ]

            if len(parts) >= 3:
                # Accept either:
                # workspace/client/project
                # client/workspace/project
                if parts[0] in workspace_names:
                    parsed_workspace = parts[0]
                    parsed_client = parts[1]
                    parsed_project = parts[2]
                elif parts[1] in workspace_names:
                    parsed_client = parts[0]
                    parsed_workspace = parts[1]
                    parsed_project = parts[2]

            elif len(parts) == 2:
                parsed_client = parts[0]
                parsed_project = parts[1]

            else:
                parsed_project = access_key

            target_clients = (
                [parsed_client]
                if parsed_client
                else client_access or ["Unassigned"]
            )

            target_workspaces = (
                [parsed_workspace]
                if parsed_workspace
                else user_workspaces
            )

            for client in target_clients:
                for workspace in target_workspaces:
                    project_node = add_project(
                        client,
                        workspace,
                        parsed_project,
                    )

                    if not project_node:
                        continue

                    if not reviewer_already_added(
                        project_node,
                        user.username,
                    ):
                        project_node["reviewers"].append(
                            reviewer_payload(user)
                        )

    # 3. Convert nested defaultdicts into sorted lists for frontend.
    result = []

    for client_name in sorted(clients.keys(), key=str.lower):
        client_node = clients[client_name]

        workspaces = []

        for workspace_name in sorted(
            client_node["workspaces"].keys(),
            key=str.lower,
        ):
            workspace_node = client_node["workspaces"][workspace_name]

            projects = []

            for project_name in sorted(
                workspace_node["projects"].keys(),
                key=str.lower,
            ):
                project_node = workspace_node["projects"][project_name]
                projects.append(project_node)

            workspace_node["projects"] = projects
            workspaces.append(workspace_node)

        client_node["workspaces"] = workspaces
        result.append(client_node)

    return {
        "status": "success",
        "clients": result,
    }


@router.get("/project-users")
def project_users(
    workspace: str,
    client: str,
    project: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if admin.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    users = db.query(User).all()

    project_key = f"{client}/{project}"
    alternate_project_key = project

    assigned_users = []

    for user in users:
        project_access = safe_list(user.project_access)
        workspace_access = safe_list(user.workspace_access)

        if (
            project_key not in project_access
            and alternate_project_key not in project_access
        ):
            continue

        if (
            workspace not in workspace_access
            and "ALL" not in workspace_access
        ):
            continue

        assigned_users.append(
            {
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "status": user.status,
                "auth_provider": user.auth_provider,
            }
        )

    return {
        "status": "success",
        "workspace": workspace,
        "client": client,
        "project": project,
        "users": assigned_users,
    }

@router.get("/project-hours-overview")
def project_hours_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if admin.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    rows = (
        db.query(
            TimeEntry.client,
            TimeEntry.workspace,
            TimeEntry.project,
            TimeEntry.role,
            func.sum(TimeEntry.hours).label("total_hours"),
        )
        .group_by(
            TimeEntry.client,
            TimeEntry.workspace,
            TimeEntry.project,
            TimeEntry.role,
        )
        .order_by(
            TimeEntry.client,
            TimeEntry.workspace,
            TimeEntry.project,
            TimeEntry.role,
        )
        .all()
    )

    return {
        "status": "success",
        "rows": [
            {
                "client": row.client,
                "workspace": row.workspace,
                "project": row.project,
                "role": row.role,
                "total_hours": float(row.total_hours or 0),
            }
            for row in rows
        ],
    }


@router.get("/review-hours")
def review_hours(
    workspace: str,
    client: str,
    project: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if admin.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    rows = (
        db.query(
            TimeEntry.week_ending,
            TimeEntry.username,
            TimeEntry.display_name,
            TimeEntry.role,
            func.sum(TimeEntry.hours).label("total_hours"),
        )
        .filter(TimeEntry.workspace == workspace)
        .filter(TimeEntry.client == client)
        .filter(TimeEntry.project == project)
        .group_by(
            TimeEntry.week_ending,
            TimeEntry.username,
            TimeEntry.display_name,
            TimeEntry.role,
        )
        .order_by(
            TimeEntry.week_ending.desc(),
            TimeEntry.role,
            TimeEntry.display_name,
        )
        .all()
    )

    return {
        "status": "success",
        "workspace": workspace,
        "client": client,
        "project": project,
        "rows": [
            {
                "week_ending": (
                    row.week_ending.isoformat()
                    if row.week_ending
                    else ""
                ),
                "username": row.username,
                "display_name": row.display_name,
                "role": row.role,
                "total_hours": float(row.total_hours or 0),
            }
            for row in rows
        ],
    }

@router.post("/users/status")
def update_user_status(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if admin.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    username = payload.get("username")
    status = payload.get("status")

    if status not in ["Active", "Inactive"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid status.",
        )

    user = db.query(User).filter(User.username == username).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    if user.role == "INSYT Admin":
        raise HTTPException(
            status_code=403,
            detail="INSYT Admin status cannot be changed here.",
        )

    user.status = status

    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "user": {
            "username": user.username,
            "status": user.status,
        },
    }