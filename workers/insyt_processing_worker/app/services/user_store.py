USERS = [
    {
        "username": "admin",
        "display_name": "INSYT Admin",
        "role": "INSYT Admin",
        "email": "admin@insyt360.com",
        "status": "Active",
        "password": "password",
        "project_access": ["Project_Timber", "Alpine_Claims"],
    },
    {
        "username": "reviewer1",
        "display_name": "Reviewer One",
        "role": "1L Reviewer",
        "email": "admin@insyt360.com",
        "status": "Active",
        "password": "review123",
        "project_access": ["Project_Timber"],
    },
    {
        "username": "qc1",
        "display_name": "QC Lead",
        "role": "QC",
        "email": "admin@insyt360.com",
        "status": "Active",
        "password": "qc123",
        "project_access": ["Project_Timber"],
    },
]


def find_user(username: str):
    for user in USERS:
        if user["username"] == username:
            return user
    return None