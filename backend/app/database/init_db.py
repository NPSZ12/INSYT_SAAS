import json

from app.database.connection import Base, engine, SessionLocal
from app.models.user import User
from app.services.security import hash_password
from app.models.project import Project, Batch, DocumentStatus, CapturedEntity


def init_db():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        existing_admin = (
            db.query(User)
            .filter(User.username == "admin")
            .first()
        )

        if not existing_admin:
            admin = User(
                username="admin",
                display_name="INSYT Admin",
                email="admin@insyt360.com",
                role="Admin",
                status="Active",
                password_hash=hash_password("password"),
                project_access=json.dumps(["Project_Timber"]),
                launches=json.dumps(["INSYT™ Capture"]),
                permissions=json.dumps([
                    "Download Docs",
                    "Upload Docs",
                    "Edit Captured Entities",
                    "Delete Captured Entities",
                    "Create Batches",
                    "Create Search Folders",
                    "View Messaging",
                    "Send Messaging",
                ]),
            )

            db.add(admin)
            db.commit()

    finally:
        db.close()