from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import (
    create_project_batch,
    list_project_batches,
)

router = APIRouter(
    prefix="/api/discovery",
    tags=["discovery-batches"],
)


class CreateBatchRequest(BaseModel):
    batch_size: int
    level: str
    workflow_type: str = "standard"
    created_by: str = "admin"
    search_folder_doc_ids: list[str] | None = None

class BatchCheckoutRequest(BaseModel):
    batch_name: str
    username: str

@router.get("/projects/{project_id}/batches")
def get_discovery_batches(project_id: str):
    try:
        return list_project_batches("discovery", project_id)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list discovery batches: {type(e).__name__}: {e}",
        )


@router.post("/projects/{project_id}/batches/create")
def create_discovery_batch(
    project_id: str,
    payload: CreateBatchRequest,
):
    try:
        return create_project_batch(
            workspace="discovery",
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
            detail=f"Unable to create discovery batch: {type(e).__name__}: {e}",
        )
        
@router.post("/projects/{project_id}/batches/checkout")
def checkout_discovery_batch(
    project_id: str,
    payload: BatchCheckoutRequest,
):
    try:
        return checkout_project_batch(
            workspace="discovery",
            project_id=project_id,
            batch_name=payload.batch_name,
            username=payload.username,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Discovery batch checkout failed: {type(e).__name__}: {e}",
        )