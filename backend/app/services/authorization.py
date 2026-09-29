from __future__ import annotations

import json
from typing import Iterable

from fastapi import HTTPException

from app.models.user import User


# ---------------------------------------------------------------------------
# INSYT Auth Core v1
# Canonical roles
# ---------------------------------------------------------------------------

ROLE_INSYT_ADMIN = "INSYT Admin"
ROLE_INSYT_MANAGER = "INSYT Manager"
ROLE_CLIENT_ADMIN = "Client Admin"
ROLE_CLIENT = "Client"
ROLE_TL = "TL"
ROLE_QC = "QC"
ROLE_REVIEWER = "Reviewer"


CANONICAL_ROLES = {
    ROLE_INSYT_ADMIN,
    ROLE_INSYT_MANAGER,
    ROLE_CLIENT_ADMIN,
    ROLE_CLIENT,
    ROLE_TL,
    ROLE_QC,
    ROLE_REVIEWER,
}


ENTRA_ROLES = {
    ROLE_INSYT_MANAGER,
    ROLE_CLIENT_ADMIN,
    ROLE_CLIENT,
    ROLE_TL,
    ROLE_QC,
    ROLE_REVIEWER,
}


LOCAL_MFA_ROLES = {
    ROLE_INSYT_ADMIN,
}


# ---------------------------------------------------------------------------
# Legacy migration aliases
# These exist only so existing records can be migrated deliberately.
# New writes must use canonical roles.
# ---------------------------------------------------------------------------

LEGACY_ROLE_ALIASES = {
    "RM": ROLE_INSYT_MANAGER,
    "Admin": ROLE_CLIENT_ADMIN,
    "1L": ROLE_REVIEWER,
    "1L Reviewer": ROLE_REVIEWER,
}


# ---------------------------------------------------------------------------
# Canonical granular permissions
# ---------------------------------------------------------------------------

PERMISSION_VIEW = "Can: View"
PERMISSION_DOWNLOAD = "Can: Download"
PERMISSION_UPLOAD = "Can: Upload"
PERMISSION_PROCESS = "Can: Process"
PERMISSION_RUN_DETECTION = "Can: Run Detection"

PERMISSION_CREATE_PROJECTS = "Can: Create Projects"
PERMISSION_MANAGE_PROJECTS = "Can: Manage Projects"
PERMISSION_MANAGE_PROJECT_ACCESS = "Can: Manage Project Access"

PERMISSION_INVITE_USERS = "Can: Invite Users"
PERMISSION_MANAGE_USERS = "Can: Manage Users"

PERMISSION_CREATE_BATCHES = "Can: Create Batches"
PERMISSION_MANAGE_BATCHES = "Can: Manage Batches"

PERMISSION_REVIEW = "Can: Review"
PERMISSION_QC = "Can: QC"
PERMISSION_MANAGE_REVIEW_TEAM = "Can: Manage Review Team"

PERMISSION_MANAGE_PROTOCOL = "Can: Manage Protocol"

PERMISSION_EXPORT = "Can: Export"
PERMISSION_VIEW_REPORTS = "Can: View Reports"

PERMISSION_APPROVE_CHARGES = "Can: Approve Charges"
PERMISSION_MANAGE_BILLING = "Can: Manage Billing"


CANONICAL_PERMISSIONS = {
    PERMISSION_VIEW,
    PERMISSION_DOWNLOAD,
    PERMISSION_UPLOAD,
    PERMISSION_PROCESS,
    PERMISSION_RUN_DETECTION,
    PERMISSION_CREATE_PROJECTS,
    PERMISSION_MANAGE_PROJECTS,
    PERMISSION_MANAGE_PROJECT_ACCESS,
    PERMISSION_INVITE_USERS,
    PERMISSION_MANAGE_USERS,
    PERMISSION_CREATE_BATCHES,
    PERMISSION_MANAGE_BATCHES,
    PERMISSION_REVIEW,
    PERMISSION_QC,
    PERMISSION_MANAGE_REVIEW_TEAM,
    PERMISSION_MANAGE_PROTOCOL,
    PERMISSION_EXPORT,
    PERMISSION_VIEW_REPORTS,
    PERMISSION_APPROVE_CHARGES,
    PERMISSION_MANAGE_BILLING,
}


# ---------------------------------------------------------------------------
# Default permission profiles
# ---------------------------------------------------------------------------

ROLE_DEFAULT_PERMISSIONS = {
    ROLE_INSYT_ADMIN: {"ALL"},

    ROLE_INSYT_MANAGER: {
        PERMISSION_VIEW,
        PERMISSION_DOWNLOAD,
        PERMISSION_UPLOAD,
        PERMISSION_PROCESS,
        PERMISSION_RUN_DETECTION,
        PERMISSION_CREATE_PROJECTS,
        PERMISSION_MANAGE_PROJECTS,
        PERMISSION_MANAGE_PROJECT_ACCESS,
        PERMISSION_INVITE_USERS,
        PERMISSION_MANAGE_USERS,
        PERMISSION_CREATE_BATCHES,
        PERMISSION_MANAGE_BATCHES,
        PERMISSION_REVIEW,
        PERMISSION_QC,
        PERMISSION_MANAGE_REVIEW_TEAM,
        PERMISSION_MANAGE_PROTOCOL,
        PERMISSION_EXPORT,
        PERMISSION_VIEW_REPORTS,
    },

    ROLE_CLIENT_ADMIN: {
        PERMISSION_VIEW,
        PERMISSION_DOWNLOAD,
        PERMISSION_UPLOAD,
        PERMISSION_PROCESS,
        PERMISSION_MANAGE_PROJECT_ACCESS,
        PERMISSION_INVITE_USERS,
        PERMISSION_EXPORT,
        PERMISSION_VIEW_REPORTS,
        PERMISSION_APPROVE_CHARGES,
    },

    ROLE_CLIENT: {
        PERMISSION_VIEW,
        PERMISSION_INVITE_USERS,
        PERMISSION_VIEW_REPORTS,
    },

    ROLE_TL: {
        PERMISSION_VIEW,
        PERMISSION_DOWNLOAD,
        PERMISSION_CREATE_BATCHES,
        PERMISSION_MANAGE_BATCHES,
        PERMISSION_REVIEW,
        PERMISSION_QC,
        PERMISSION_MANAGE_REVIEW_TEAM,
        PERMISSION_VIEW_REPORTS,
    },

    ROLE_QC: {
        PERMISSION_VIEW,
        PERMISSION_DOWNLOAD,
        PERMISSION_REVIEW,
        PERMISSION_QC,
        PERMISSION_VIEW_REPORTS,
    },

    ROLE_REVIEWER: {
        PERMISSION_VIEW,
        PERMISSION_REVIEW,
    },
}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_role(role: str | None) -> str:
    value = str(role or "").strip()

    if value in CANONICAL_ROLES:
        return value

    return LEGACY_ROLE_ALIASES.get(value, value)


def validate_canonical_role(role: str | None) -> str:
    normalized = normalize_role(role)

    if normalized not in CANONICAL_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported INSYT role: {role!r}",
        )

    return normalized


def default_permissions_for_role(role: str) -> list[str]:
    normalized = validate_canonical_role(role)

    values = ROLE_DEFAULT_PERMISSIONS.get(normalized, set())

    if "ALL" in values:
        return ["ALL"]

    return sorted(values)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _json_list(value: str | None) -> list[str]:
    try:
        decoded = json.loads(value or "[]")
    except Exception:
        return []

    if not isinstance(decoded, list):
        return []

    return [
        str(item).strip()
        for item in decoded
        if str(item).strip()
    ]


def user_permissions(user: User) -> set[str]:
    values = set(_json_list(user.permissions))

    if normalize_role(user.role) == ROLE_INSYT_ADMIN:
        values.add("ALL")

    return values


def has_permission(
    user: User,
    permission: str,
) -> bool:
    values = user_permissions(user)

    return (
        "ALL" in values
        or permission in values
    )


def require_permission(
    user: User,
    permission: str,
) -> User:
    if not has_permission(user, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Permission required: {permission}",
        )

    return user


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

def _has_scope(
    stored_value: str | None,
    requested_value: str | None,
) -> bool:
    values = set(_json_list(stored_value))

    if "ALL" in values:
        return True

    requested = str(requested_value or "").strip()

    if not requested:
        return False

    return requested in values


def has_workspace_access(
    user: User,
    workspace: str,
) -> bool:
    if normalize_role(user.role) == ROLE_INSYT_ADMIN:
        return True

    return _has_scope(
        user.workspace_access,
        workspace,
    )


def has_client_access(
    user: User,
    client: str,
) -> bool:
    if normalize_role(user.role) == ROLE_INSYT_ADMIN:
        return True

    return _has_scope(
        user.client_access,
        client,
    )


def has_project_access(
    user: User,
    project: str,
) -> bool:
    if normalize_role(user.role) == ROLE_INSYT_ADMIN:
        return True

    return _has_scope(
        user.project_access,
        project,
    )

def has_scoped_project_access(
    user: User,
    workspace: str,
    client: str,
    project: str,
) -> bool:
    """
    Canonical Auth Core project-scope check.

    INSYT Admin:
        unrestricted.

    All other roles:
        must have matching workspace, client, and project scope.

    Client / Client Admin:
        global ALL scope is never accepted.

    Project scope must be client-qualified. Bare project names are
    intentionally not accepted because identical project names may
    exist beneath different clients.
    """
    role = normalize_role(user.role)

    if role == ROLE_INSYT_ADMIN:
        return True

    requested_workspace = str(
        workspace or ""
    ).strip()

    requested_client = str(
        client or ""
    ).strip()

    requested_project = str(
        project or ""
    ).strip()

    if (
        not requested_workspace
        or not requested_client
        or not requested_project
    ):
        return False

    workspace_scope = {
        str(value or "").strip()
        for value in _json_list(
            user.workspace_access
        )
        if str(value or "").strip()
    }

    client_scope = {
        str(value or "").strip()
        for value in _json_list(
            user.client_access
        )
        if str(value or "").strip()
    }

    project_scope = {
        str(value or "").strip()
        for value in _json_list(
            user.project_access
        )
        if str(value or "").strip()
    }

    external_roles = {
        ROLE_CLIENT,
        ROLE_CLIENT_ADMIN,
    }

    if role in external_roles:
        if (
            "ALL" in workspace_scope
            or "ALL" in client_scope
            or "ALL" in project_scope
        ):
            return False

    workspace_allowed = (
        "ALL" in workspace_scope
        or requested_workspace
        in workspace_scope
    )

    client_candidates = {
        requested_client,
        (
            f"{requested_workspace}/"
            f"{requested_client}"
        ),
    }

    client_allowed = (
        "ALL" in client_scope
        or bool(
            client_candidates
            & client_scope
        )
    )

    project_candidates = {
        (
            f"{requested_workspace}/"
            f"{requested_client}/"
            f"{requested_project}"
        ),
        (
            f"{requested_client}/"
            f"{requested_project}"
        ),
        (
            f"{requested_client}/"
            f"{requested_workspace}/"
            f"{requested_project}"
        ),
    }

    project_allowed = (
        "ALL" in project_scope
        or bool(
            project_candidates
            & project_scope
        )
    )

    return (
        workspace_allowed
        and client_allowed
        and project_allowed
    )


def require_scoped_project_access(
    user: User,
    workspace: str,
    client: str,
    project: str,
) -> None:
    if has_scoped_project_access(
        user,
        workspace,
        client,
        project,
    ):
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "Access denied. This account is not "
            "authorized for the requested "
            "workspace, client, and project."
        ),
    )

# ---------------------------------------------------------------------------
# Authentication policy
# ---------------------------------------------------------------------------

def role_requires_local_mfa(role: str | None) -> bool:
    return normalize_role(role) in LOCAL_MFA_ROLES


def role_requires_entra(role: str | None) -> bool:
    return normalize_role(role) in ENTRA_ROLES


def validate_auth_provider_for_role(
    role: str,
    auth_provider: str,
) -> None:
    normalized_role = validate_canonical_role(role)
    provider = str(auth_provider or "").strip().lower()

    if normalized_role == ROLE_INSYT_ADMIN:
        if provider != "local":
            raise HTTPException(
                status_code=400,
                detail="INSYT Admin must use local INSYT authentication with MFA.",
            )

        return

    if normalized_role in ENTRA_ROLES:
        if provider != "entra":
            raise HTTPException(
                status_code=400,
                detail=f"{normalized_role} must use Microsoft Entra authentication.",
            )

        return

    raise HTTPException(
        status_code=400,
        detail="Unsupported authentication configuration.",
    )


# ---------------------------------------------------------------------------
# Role-management boundaries
# ---------------------------------------------------------------------------

def may_manage_role(
    actor: User,
    target_role: str,
) -> bool:
    actor_role = normalize_role(actor.role)
    target = validate_canonical_role(target_role)

    if actor_role == ROLE_INSYT_ADMIN:
        return True

    if actor_role == ROLE_INSYT_MANAGER:
        return target in {
            ROLE_INSYT_MANAGER,
            ROLE_CLIENT_ADMIN,
            ROLE_CLIENT,
            ROLE_TL,
            ROLE_QC,
            ROLE_REVIEWER,
        }

    if actor_role == ROLE_CLIENT_ADMIN:
        return target in {
            ROLE_CLIENT,
            ROLE_TL,
            ROLE_QC,
            ROLE_REVIEWER,
        }

    if actor_role == ROLE_CLIENT:
        return target == ROLE_CLIENT

    return False

def _scope_set(value: str | None) -> set[str]:
    return set(_json_list(value))


def requested_scope_is_within_user_scope(
    actor: User,
    requested_values: Iterable[str],
    scope_name: str,
) -> bool:
    normalized_role = normalize_role(actor.role)

    if normalized_role == ROLE_INSYT_ADMIN:
        return True

    requested = {
        str(value).strip()
        for value in requested_values
        if str(value).strip()
    }

    if scope_name == "workspace":
        actor_scope = _scope_set(actor.workspace_access)
    elif scope_name == "client":
        actor_scope = _scope_set(actor.client_access)
    elif scope_name == "project":
        actor_scope = _scope_set(actor.project_access)
    else:
        return False

    if "ALL" in actor_scope:
        return True

    return requested.issubset(actor_scope)


def require_user_scope_assignment(
    actor: User,
    workspace_access: Iterable[str],
    client_access: Iterable[str],
    project_access: Iterable[str],
) -> None:
    normalized_role = normalize_role(actor.role)

    if normalized_role == ROLE_INSYT_ADMIN:
        return

    if not requested_scope_is_within_user_scope(
        actor,
        workspace_access,
        "workspace",
    ):
        raise HTTPException(
            status_code=403,
            detail="Cannot assign workspace access outside your authorized scope.",
        )

    if not requested_scope_is_within_user_scope(
        actor,
        client_access,
        "client",
    ):
        raise HTTPException(
            status_code=403,
            detail="Cannot assign client access outside your authorized scope.",
        )

    if not requested_scope_is_within_user_scope(
        actor,
        project_access,
        "project",
    ):
        raise HTTPException(
            status_code=403,
            detail="Cannot assign project access outside your authorized scope.",
        )

    if normalized_role == ROLE_CLIENT_ADMIN:
        requested_clients = {
            str(value).strip()
            for value in client_access
            if str(value).strip()
        }

        actor_clients = _scope_set(actor.client_access)

        if not requested_clients:
            raise HTTPException(
                status_code=403,
                detail="Client Admin users must remain assigned to a client.",
            )

        if "ALL" not in actor_clients and not requested_clients.issubset(actor_clients):
            raise HTTPException(
                status_code=403,
                detail="Client Admin may only manage users within their own client.",
            )


def user_is_within_actor_client_scope(
    actor: User,
    target: User,
) -> bool:
    normalized_role = normalize_role(actor.role)

    if normalized_role == ROLE_INSYT_ADMIN:
        return True

    actor_clients = _scope_set(actor.client_access)
    target_clients = _scope_set(target.client_access)

    if "ALL" in actor_clients:
        return True

    if not target_clients:
        return False

    return target_clients.issubset(actor_clients)

def user_is_within_actor_scope(
    actor: User,
    target: User,
) -> bool:
    normalized_role = normalize_role(actor.role)

    if normalized_role == ROLE_INSYT_ADMIN:
        return True

    actor_workspaces = _scope_set(
        actor.workspace_access
    )
    actor_clients = _scope_set(
        actor.client_access
    )
    actor_projects = _scope_set(
        actor.project_access
    )

    target_workspaces = _scope_set(
        target.workspace_access
    )
    target_clients = _scope_set(
        target.client_access
    )
    target_projects = _scope_set(
        target.project_access
    )

    def contained(
        actor_scope: set[str],
        target_scope: set[str],
    ) -> bool:
        if "ALL" in actor_scope:
            return True

        if "ALL" in target_scope:
            return False

        return target_scope.issubset(
            actor_scope
        )

    return (
        contained(
            actor_workspaces,
            target_workspaces,
        )
        and contained(
            actor_clients,
            target_clients,
        )
        and contained(
            actor_projects,
            target_projects,
        )
    )
