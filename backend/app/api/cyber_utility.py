from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(
    prefix="/api/cyber-utility",
    tags=["cyber-utility"],
)


class UtilityJobRequest(BaseModel):
    workspace: str
    project_id: str
    tool_name: str
    input_path: str | None = None
    output_path: str | None = None
    options: dict = {}


@router.post("/jobs")
def create_utility_job(payload: UtilityJobRequest):
    if payload.workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="workspace must be capture, summaries, or discovery",
        )

    job_id = str(uuid4())

    return {
        "job_id": job_id,
        "status": "queued",
        "workspace": payload.workspace,
        "project_id": payload.project_id,
        "tool_name": payload.tool_name,
        "input_path": payload.input_path,
        "output_path": payload.output_path,
        "options": payload.options,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": "Cyber² Utility job queued.",
    }


@router.get("/jobs/{job_id}")
def get_utility_job(job_id: str):
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Job status persistence will be connected next.",
    }