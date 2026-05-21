from app.models.job import Job
from app.models.project import Project
from app.models.user import User


class CapturedEntity:
    pass


__all__ = [
    "Job",
    "Project",
    "User",
    "CapturedEntity",
]