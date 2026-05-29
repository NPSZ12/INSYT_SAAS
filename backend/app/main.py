from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

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
from app.api.workspace_projects import router as workspace_projects_router
from app.api.discovery_batches import router as discovery_batches_router
from app.api.cyber_utility import router as cyber_utility_router
from app.api.capture_clients import router as capture_clients_router
from app.api.workspace_protocols import router as workspace_protocols_router
from app.api.summaries_qc import router as summaries_qc_router
from app.api.discovery_review_batches import router as discovery_review_batches_router
from app.api.discovery import router as discovery_router
from app.api.workspace_files import router as workspace_files_router

from app.routes import merge_dedupe
from app.routes import tools_merge_dedupe


app = FastAPI(title="INSYT SaaS API")

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
    expose_headers=["*"],
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
app.include_router(capture_projects_router, dependencies=protected_dependencies)


# =========================
# WORKSPACE ROUTES
# =========================

app.include_router(protocol_templates_router)
app.include_router(summaries_router)
app.include_router(summaries_batches_router)
app.include_router(capture_batches_router)
app.include_router(capture_review_batches_router)
app.include_router(summaries_review_batches_router)
app.include_router(workspace_projects_router)
app.include_router(discovery_batches_router)
app.include_router(cyber_utility_router)
app.include_router(capture_clients_router)
app.include_router(workspace_protocols_router)
app.include_router(summaries_qc_router)
app.include_router(discovery_review_batches_router)
app.include_router(discovery_router)
app.include_router(workspace_files_router)


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