from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.projects import router as projects_router
from app.api.users import router as users_router
from app.api.review import router as review_router
from app.api.auth import router as auth_router
from app.api.azure_projects import router as azure_projects_router
from app.api.batches import router as batches_router
from app.api.entities import router as entities_router
from app.api.timesheet import router as timesheet_router
from app.api.messages import router as messages_router
from app.api.search_folders import router as search_folders_router
from app.api.files import router as files_router
from app.database.init_db import init_db

app = FastAPI(title="INSYT SaaS API")

init_db()

from fastapi.middleware.cors import CORSMiddleware

allow_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",

    "https://insyt360.com",
    "https://www.insyt360.com",

    "https://app.insyt360.com",
    "https://portal.insyt360.com",
    "https://media.insyt360.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(users_router)
app.include_router(review_router)
app.include_router(auth_router)
app.include_router(azure_projects_router)
app.include_router(batches_router)
app.include_router(entities_router)
app.include_router(timesheet_router)
app.include_router(messages_router)
app.include_router(search_folders_router)
app.include_router(files_router)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "INSYT SaaS API"
    }