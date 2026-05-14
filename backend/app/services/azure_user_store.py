import json
from app.services.azure_blob_service import get_container_client

USERS_BLOB_NAME = "_system/users.json"


DEFAULT_USERS = [
    {
        "username": "admin",
        "display_name": "CDS Admin",
        "email": "admin@cyber-discovery.com",
        "role": "Admin",
        "status": "Active",
        "password": "password",
        "project_access": ["Project_Timber"],
        "launches": ["INSYT™ Capture"],
        "permissions": [
            "Download Docs",
            "Upload Docs",
            "Edit Captured Entities",
            "Delete Captured Entities",
            "Create Batches",
            "Create Search Folders",
            "View Messaging",
            "Send Messaging",
        ],
    }
]


def load_users():
    container = get_container_client()
    blob_client = container.get_blob_client(USERS_BLOB_NAME)

    if not blob_client.exists():
        save_users(DEFAULT_USERS)
        return DEFAULT_USERS

    data = blob_client.download_blob().readall()
    return json.loads(data.decode("utf-8"))


def save_users(users):
    container = get_container_client()
    blob_client = container.get_blob_client(USERS_BLOB_NAME)

    blob_client.upload_blob(
        json.dumps(users, indent=2),
        overwrite=True,
        content_type="application/json",
    )


def find_user(username: str):
    users = load_users()

    for user in users:
        if user["username"] == username:
            return user

    return None