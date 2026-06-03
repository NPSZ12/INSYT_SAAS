from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import (
    create_project_batch,
    list_project_batches,
    remove_docs_from_batch,
)

router = APIRouter(
    prefix="/api/capture",
    tags=["capture-batches"],
)


class CreateBatchRequest(BaseModel):
    batch_size: int
    level: str
    workflow_type: str = "standard"
    created_by: str = "admin"
    search_folder_doc_ids: list[str] | None = None
    
class RemoveDocsRequest(BaseModel):
    batch_name: str
    doc_ids: list[str]
    username: str = "admin"


@router.get("/projects/{project_id}/batches")
def get_capture_batches(
    project_id: str,
    client: str = "",
):
    try:
        return list_project_batches(
            "capture",
            project_id,
            client,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list capture batches: {type(e).__name__}: {e}",
        )


@router.post("/projects/{project_id}/batches/create")
def create_capture_batch(
    project_id: str,
    payload: CreateBatchRequest,
    client: str = "",
):
    try:
        return create_project_batch(
            workspace="capture",
            project_id=project_id,
            client_id=client,
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
            detail=f"Unable to create capture batch: {type(e).__name__}: {e}",
        )
        
@router.post("/projects/{project_id}/batches/remove-docs")
def remove_docs_from_capture_batch_save_data(
    project_id: str,
    payload: RemoveDocsRequest,
):
    try:
        return remove_docs_from_batch(
            workspace="capture",
            project_id=project_id,
            batch_name=payload.batch_name,
            doc_ids=payload.doc_ids,
            username=payload.username,
            preserve_captured_data=True,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to remove docs from capture batch: {type(e).__name__}: {e}",
        )


@router.post("/projects/{project_id}/batches/remove-docs-no-save")
def remove_docs_from_capture_batch_no_save(
    project_id: str,
    payload: RemoveDocsRequest,
):
    try:
        return remove_docs_from_batch(
            workspace="capture",
            project_id=project_id,
            batch_name=payload.batch_name,
            doc_ids=payload.doc_ids,
            username=payload.username,
            preserve_captured_data=False,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to remove docs without saving: {type(e).__name__}: {e}",
        )