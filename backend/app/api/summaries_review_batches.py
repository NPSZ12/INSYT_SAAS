from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.review_batch_service import (
    checkout_batch,
    release_batch,
    complete_batch,
)

router = APIRouter(
    prefix="/api/summaries",
    tags=["summaries-review-batches"],
)


class BatchActionRequest(BaseModel):
    batch_name: str
    username: str
    role: str | None = None


@router.post("/projects/{project_id}/batches/checkout")
def checkout_summaries_batch(
    project_id: str,
    payload: BatchActionRequest,
    client: str = Query(default=""),
):
    try:
        return checkout_batch(
            workspace="summaries",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
            client_id=client,
        )

    except HTTPException:
        raise

@router.post("/projects/{project_id}/batches/release")
def release_summaries_batch(
    project_id: str,
    payload: BatchActionRequest,
    client: str = Query(default=""),
):
    try:
        return release_batch(
            workspace="summaries",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
            role=payload.role,
            client_id=client,
        )

    except HTTPException:
        raise


@router.post("/projects/{project_id}/batches/complete")
def complete_summaries_batch(
    project_id: str,
    payload: BatchActionRequest,
    client: str = Query(default=""),
):
    try:
        return complete_batch(
            workspace="summaries",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
            client_id=client,
        )

    except HTTPException:
        raise
