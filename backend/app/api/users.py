from fastapi import APIRouter
from pydantic import BaseModel
from app.services.azure_user_store import load_users, save_users, find_user

router = APIRouter(prefix="/api/users", tags=["Users"])


class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    password: str
    project_access: list[str] = []
    launches: list[str] = []
    permissions: list[str] = []
    
class UserUpdateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    password: str = ""
    project_access: list[str] = []
    launches: list[str] = []
    permissions: list[str] = []

class UserDeleteRequest(BaseModel):
    username: str

class PasswordResetRequest(BaseModel):
    username: str
    new_password: str


class ProjectAccessRequest(BaseModel):
    username: str
    project_id: str
    allowed: bool


@router.get("")
def list_users():
    return load_users()


@router.post("/create")
def create_user(payload: UserCreateRequest):
    users = load_users()

    existing = find_user(payload.username)

    if existing:
        return {
            "status": "duplicate_user",
            "message": "A user with this username already exists.",
        }

    users.append({
        "username": payload.username,
        "display_name": payload.display_name,
        "email": payload.email,
        "role": payload.role,
        "status": "Active",
        "password": payload.password,
        "project_access": payload.project_access,
        "launches": payload.launches,
        "permissions": payload.permissions,
    })

    save_users(users)

    return {"status": "created", "user": payload.username}

@router.post("/update")
def update_user(payload: UserUpdateRequest):
    users = load_users()

    for user in users:
        if user["username"] == payload.username:
            user["display_name"] = payload.display_name
            user["email"] = payload.email
            user["role"] = payload.role
            user["project_access"] = payload.project_access
            user["launches"] = payload.launches
            user["permissions"] = payload.permissions

            if payload.password:
                user["password"] = payload.password

            save_users(users)

            return {
                "status": "updated",
                "user": payload.username,
            }

    return {"status": "not_found"}

@router.post("/delete")
def delete_user(payload: UserDeleteRequest):
    users = load_users()

    updated_users = [
        user for user in users
        if user["username"] != payload.username
    ]

    if len(updated_users) == len(users):
        return {"status": "not_found"}

    save_users(updated_users)

    return {
        "status": "deleted",
        "user": payload.username,
    }

@router.post("/reset-password")
def reset_password(payload: PasswordResetRequest):
    user = find_user(payload.username)

    if not user:
        return {"status": "user_not_found"}

    user["password"] = payload.new_password

    return {
        "status": "password_reset",
        "username": payload.username,
    }


@router.post("/project-access")
def update_project_access(payload: ProjectAccessRequest):
    for user in USERS:
        if user["username"] == payload.username:
            access = user["project_access"]

            if payload.allowed and payload.project_id not in access:
                access.append(payload.project_id)

            if not payload.allowed and payload.project_id in access:
                access.remove(payload.project_id)

            return {
                "status": "updated",
                "username": payload.username,
                "project_access": access,
            }

    return {"status": "user_not_found"}