from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import (
    create_project_batch,
    list_project_batches,
    checkout_project_batch,
)

router = APIRouter(
    prefix="/api/summaries",
    tags=["summaries-batches"],
)


class CreateBatchRequest(BaseModel):
    batch_size: int
    level: str
    workflow_type: str = "standard"
    created_by: str = "admin"
    search_folder_doc_ids: list[str] | None = None
    
class CheckoutBatchRequest(BaseModel):
    batch_name: str
    username: str


@router.get("/projects/{project_id}/batches")
def get_summaries_batches(
    project_id: str,
    client: str = "",
):
    try:
        return list_project_batches(
            "summaries",
            project_id,
            client,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list summaries batches: {type(e).__name__}: {e}",
        )


@router.post("/projects/{project_id}/batches/create")
def create_summaries_batch(
    project_id: str,
    payload: CreateBatchRequest,
    client: str = "",
):
    try:
        return create_project_batch(
            workspace="summaries",
            client_id=client,
            project_id=project_id,
            batch_size=payload.batch_size,
            level=payload.level,
            workflow_type=payload.workflow_type,
            created_by=payload.created_by,
            search_folder_doc_ids=payload.search_folder_doc_ids,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create summaries batch: {type(e).__name__}: {e}",
        )
        
@router.post("/projects/{project_id}/batches/checkout")
def checkout_summaries_batch(
    project_id: str,
    payload: CheckoutBatchRequest,
    client: str = "",
):
    try:
        return checkout_project_batch(
            workspace="summaries",
            client_id=client,
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to checkout summaries batch: {type(e).__name__}: {e}",
        )