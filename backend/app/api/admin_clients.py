import json
import os
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
    return clients_overview_storage_test(
        db=db,
        admin=admin,
    )


@router.get("/clients-overview-storage-test")
def clients_overview_storage_test(
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

    warnings = []

    def add_project(
        client: str,
        workspace: str,
        project: str,
    ):
        client = str(client or "").strip()
        workspace = str(workspace or "").strip()
        project = str(project or "").strip()

        if not client or not workspace or not project:
            return None

        ignored_names = {
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
            "Batches",
            "SearchFolders",
            "QC",
            "Audit",
        }

        if client in ignored_names:
            return None

        if project in ignored_names:
            return None

        if workspace not in workspace_names and workspace != "unknown":
            return None

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

    discovered_project_keys = set()

    # 1. Discover real clients/projects from INSYT storage only.
    # Source: AZURE_STORAGE_CONNECTION_STRING = insytprodstorage.
    #
    # Only accept the new path:
    #   Client1/capture/Project_Client1/...
    #
    # Do not create clients/projects from DB-only legacy user access.
    try:
        from azure.storage.blob import BlobServiceClient

        source_connection_string = os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING"
        )

        if not source_connection_string:
            warnings.append(
                "AZURE_STORAGE_CONNECTION_STRING is not configured. "
                "Clients overview storage scan cannot run."
            )
            source_blob_service = None
        elif "AccountName=insytprodstorage" not in source_connection_string:
            warnings.append(
                "AZURE_STORAGE_CONNECTION_STRING is not pointing to "
                "insytprodstorage. Clients overview scan skipped to avoid "
                "reading from the wrong storage account."
            )
            source_blob_service = None
        else:
            source_blob_service = BlobServiceClient.from_connection_string(
                source_connection_string
            )

        container_names_by_workspace = {
            "capture": "insyt-capture",
            "summaries": "insyt-summaries",
            "discovery": "insyt-discovery",
        }

        ignored_top_level_names = {
            "capture",
            "discovery",
            "summaries",
            "development",
            "System",
            "_system",
            "_registry",
            "source",
            "processing_center",
            "Batches",
            "SearchFolders",
            "QC",
            "Audit",
            "overlays",
        }

        for workspace_name, container_name in container_names_by_workspace.items():
            try:
                if not source_blob_service:
                    continue

                container = source_blob_service.get_container_client(
                    container_name
                )

                for blob in container.list_blobs():
                    blob_name = blob.name or ""

                    parts = [
                        part
                        for part in blob_name.split("/")
                        if part
                    ]

                    if len(parts) < 3:
                        continue

                    # Correct current path:
                    # Client1/capture/Project_Capture1/...
                    # Client1/summaries/Project_Summaries1/...
                    # Client1/discovery/Project_Discovery1/...
                    if parts[1] != workspace_name:
                        continue

                    client = parts[0]
                    workspace = parts[1]
                    project = parts[2]

                    if client in ignored_top_level_names:
                        continue

                    project_node = add_project(
                        client,
                        workspace,
                        project,
                    )

                    if project_node:
                        discovered_project_keys.add(
                            f"{client}/{workspace}/{project}"
                        )

            except Exception as error:
                warnings.append(
                    f"Storage scan failed for {container_name}: {error}"
                )

    except Exception as error:
        warnings.append(
            f"Storage discovery unavailable: {error}"
        )

    # 2. Merge reviewers from DB only onto projects already discovered
    # in INSYT storage. Do not create DB-only clients/projects.
    users = db.query(User).all()

    for user in users:
        if user.role in ["INSYT Admin", "Admin"]:
            continue

        project_access = safe_list(user.project_access)
        workspace_access = safe_list(user.workspace_access)
        client_access = safe_list(user.client_access)

        if not project_access:
            continue

        for project_key in project_access:
            project_key = str(project_key or "").strip()

            if not project_key:
                continue

            parts = [
                part
                for part in project_key.split("/")
                if part
            ]

            possible_matches = set()

            # Supported access formats:
            #   Project_Client1
            #   Client1/Project_Client1
            #   capture/Client1/Project_Client1
            #   Client1/capture/Project_Client1
            if len(parts) >= 3:
                if parts[0] in workspace_names:
                    possible_matches.add(
                        f"{parts[1]}/{parts[0]}/{parts[2]}"
                    )
                elif parts[1] in workspace_names:
                    possible_matches.add(
                        f"{parts[0]}/{parts[1]}/{parts[2]}"
                    )

            elif len(parts) == 2:
                access_client = parts[0]
                access_project = parts[1]

                for workspace in workspace_names:
                    possible_matches.add(
                        f"{access_client}/{workspace}/{access_project}"
                    )

            else:
                access_project = parts[0]

                for access_client in client_access or []:
                    for workspace in workspace_access or workspace_names:
                        possible_matches.add(
                            f"{access_client}/{workspace}/{access_project}"
                        )

            matched_keys = possible_matches.intersection(
                discovered_project_keys
            )

            for matched_key in matched_keys:
                client, workspace, project = matched_key.split("/", 2)

                project_node = add_project(
                    client,
                    workspace,
                    project,
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
        "warnings": warnings,
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