from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.review_batch_service import (
    checkout_batch,
    complete_batch,
)

router = APIRouter(
    prefix="/api/discovery",
    tags=["summaries-review-batches"],
)


class BatchActionRequest(BaseModel):
    batch_name: str
    username: str


@router.post("/projects/{project_id}/batches/checkout")
def checkout_summaries_batch(
    project_id: str,
    payload: BatchActionRequest,
):
    try:
        return checkout_batch(
            workspace="discovery",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
        )

    except HTTPException:
        raise


@router.post("/projects/{project_id}/batches/complete")
def complete_summaries_batch(
    project_id: str,
    payload: BatchActionRequest,
):
    try:
        return complete_batch(
            workspace="discovery",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
        )

    except HTTPException:
        raise