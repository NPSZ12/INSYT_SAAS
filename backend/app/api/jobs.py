from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.job import Job
from app.models.user import User
from app.services.security import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


class JobCreateRequest(BaseModel):
    job_type: str
    project_id: Optional[str] = None
    input_blob_path: Optional[str] = None
    message: Optional[str] = None


@router.post("")
def create_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = Job(
        job_type=payload.job_type,
        status="Queued",
        project_id=payload.project_id,
        requested_by=current_user.username,
        input_blob_path=payload.input_blob_path,
        message=payload.message,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return {"status": "success", "job_id": job.id, "job": serialize_job(job)}


@router.get("")
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(100).all()
    return {"status": "success", "jobs": [serialize_job(job) for job in jobs]}


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"status": "success", "job": serialize_job(job)}


def serialize_job(job: Job):
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "project_id": job.project_id,
        "requested_by": job.requested_by,
        "input_blob_path": job.input_blob_path,
        "output_blob_path": job.output_blob_path,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }