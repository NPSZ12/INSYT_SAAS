from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database.connection import SessionLocal

from app.database.init_db import init_db
from app.services.security import get_current_user

from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.users import router as users_router
from app.api.review import router as review_router
from app.api.azure_projects import router as azure_projects_router
from app.api.batches import router as batches_router
from app.api.entities import router as entities_router
from app.api.timesheet import router as timesheet_router
from app.api.messages import router as messages_router
from app.api.search_folders import router as search_folders_router
from app.api.files import router as files_router
from app.api.jobs import router as jobs_router
from app.api.capture_projects import router as capture_projects_router
from app.api.protocol_templates import router as protocol_templates_router

from app.api.summaries import router as summaries_router
from app.api.summaries_batches import router as summaries_batches_router
from app.api.capture_batches import router as capture_batches_router
from app.api.capture_review_batches import router as capture_review_batches_router
from app.api.summaries_review_batches import router as summaries_review_batches_router
from app.api.discovery_batches import router as discovery_batches_router
from app.api.cyber_utility import router as cyber_utility_router
from app.api.capture_clients import router as capture_clients_router
from app.api.workspace_protocols import router as workspace_protocols_router
from app.api.summaries_qc import router as summaries_qc_router
from app.api.discovery_review_batches import router as discovery_review_batches_router
from app.api.discovery import router as discovery_router
from app.api.workspace_files import router as workspace_files_router
from app.api.summaries_text import router as summaries_text_router
from app.api import summaries_processing_center
from app.api.workspace_clients import router as workspace_clients_router
from app.api.workspace_file_uploads import router as workspace_file_uploads_router
from app.api.workspace_project_create import router as workspace_project_create_router
from app.api import workspace_projects
from app.api import summaries_summary_data
from app.models.audit_log import AuditLog
from app.api.audit_logs import router as audit_logs_router
from app.api.admin_clients import router as admin_clients_router
from app.api import capture_review_batches
from app.api import discovery_review_batches
from app.api import summaries_review_batches
from app.api import processing_center


from app.api import document_overlays

from app.routes import merge_dedupe
from app.routes import tools_merge_dedupe


app = FastAPI(title="INSYT SaaS API")

def migrate_user_access_columns():
    db = SessionLocal()

    try:
        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS workspace_access TEXT DEFAULT '[]'
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS client_access TEXT DEFAULT '[]'
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) DEFAULT 'local'
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS mfa_secret TEXT DEFAULT ''
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS mfa_backup_codes TEXT DEFAULT '[]'
                """
            )
        )

        db.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS mfa_confirmed_at TIMESTAMP NULL
                """
            )
        )

        db.commit()

        print("User/MFA migration completed.")

    finally:
        db.close()


migrate_user_access_columns()

init_db()


# =========================
# CORS CONFIGURATION
# =========================

allow_origins = [
    # Local Development
    "http://localhost:3000",
    "http://127.0.0.1:3000",

    # Production Domains
    "https://insyt360.com",
    "https://www.insyt360.com",

    # App Subdomains
    "https://app.insyt360.com",
    "https://portal.insyt360.com",
    "https://media.insyt360.com",

    # Optional Azure App Service URL
    # Add your exact Azure URL below if frontend/backend still fail
    # Example:
    # "https://insyt-platform-prod.azurewebsites.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# AUTH ROUTES
# =========================

app.include_router(auth_router)

protected_dependencies = [Depends(get_current_user)]


# =========================
# PROTECTED ROUTES
# =========================

app.include_router(projects_router, dependencies=protected_dependencies)
app.include_router(users_router, dependencies=protected_dependencies)
app.include_router(review_router, dependencies=protected_dependencies)
app.include_router(azure_projects_router, dependencies=protected_dependencies)
app.include_router(batches_router, dependencies=protected_dependencies)
app.include_router(entities_router, dependencies=protected_dependencies)
app.include_router(timesheet_router, dependencies=protected_dependencies)
app.include_router(messages_router, dependencies=protected_dependencies)
app.include_router(search_folders_router, dependencies=protected_dependencies)
app.include_router(files_router, dependencies=protected_dependencies)
app.include_router(jobs_router, dependencies=protected_dependencies)
# app.include_router(capture_projects_router, dependencies=protected_dependencies)


# =========================
# WORKSPACE ROUTES
# =========================

app.include_router(protocol_templates_router)
app.include_router(summaries_router)
app.include_router(summaries_batches_router)
app.include_router(capture_batches_router)
app.include_router(capture_review_batches_router)
app.include_router(summaries_review_batches_router)
app.include_router(discovery_batches_router)
app.include_router(cyber_utility_router)
app.include_router(capture_clients_router)
app.include_router(workspace_protocols_router)
app.include_router(summaries_qc_router)
app.include_router(summaries_processing_center.router)
app.include_router(discovery_review_batches_router)
app.include_router(discovery_router)
app.include_router(workspace_files_router)
app.include_router(summaries_text_router)
app.include_router(workspace_clients_router)
app.include_router(workspace_file_uploads_router)
#app.include_router(workspace_project_create_router)
app.include_router(workspace_projects.router)
app.include_router(summaries_summary_data.router)
app.include_router(audit_logs_router, dependencies=protected_dependencies)
app.include_router(admin_clients_router, dependencies=protected_dependencies)
app.include_router(document_overlays.router)
app.include_router(capture_review_batches.router)
app.include_router(discovery_review_batches.router)
app.include_router(summaries_review_batches.router)
app.include_router(processing_center.router)



# =========================
# TOOLS / UTILITIES
# =========================

app.include_router(merge_dedupe.router)
app.include_router(tools_merge_dedupe.router)


# =========================
# HEALTH CHECK
# =========================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "INSYT SaaS API",
    }