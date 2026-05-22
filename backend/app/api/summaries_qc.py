import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client


router = APIRouter(
    prefix="/api/summaries/qc",
    tags=["summaries-qc"],
)


class SaveQcSummaryRequest(BaseModel):
    project_id: str
    batch_id: str = ""
    summary_doc_id: str
    qc_summary: str


@router.post("/save")
def save_qc_summary(payload: SaveQcSummaryRequest):
    try:
        container = get_container_client("summaries")

        qc_blob_path = (
            f"{payload.project_id}/review/qc/"
            f"{payload.summary_doc_id}_qc.json"
        )

        qc_payload = {
            "project_id": payload.project_id,
            "batch_id": payload.batch_id,
            "summary_doc_id": payload.summary_doc_id,
            "qc_summary": payload.qc_summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        container.upload_blob(
            name=qc_blob_path,
            data=json.dumps(qc_payload, indent=2),
            overwrite=True,
        )

        return {
            "message": "QC Summary saved.",
            "qc_blob_path": qc_blob_path,
            "qc": qc_payload,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save QC Summary: {type(e).__name__}: {e}",
        )