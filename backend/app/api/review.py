from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from app.services.protocol_service import load_protocol_fields
from app.services.azure_blob_service import (
    list_project_files,
    read_blob_text,
    create_blob_read_url,
)
from app.services.project_store import CAPTURED_ENTITIES

router = APIRouter(prefix="/api/review", tags=["Review"])


@router.get("/current")
def get_current_review_document(
    project: str = "Project_Timber",
    batch: str = "Batch_001",
):
    try:
        project_id = project

        protocol_fields = load_protocol_fields(project_id)
        files = list_project_files(project_id)

        text_files = [
            file for file in files
            if file["name"].lower().endswith(".txt")
        ]

        if not text_files:
            return {
                "project": project_id.replace("_", " "),
                "project_id": project_id,
                "batch": batch,
                "doc_id": "No Text File",
                "text": "No .txt files found in this Azure project.",
                "fields": protocol_fields,
            }

        first_text_file = text_files[0]["name"]
        text = read_blob_text(first_text_file)
        doc_id = first_text_file.split("/")[-1].replace(".txt", "")

        base_name = doc_id.lower()

        pdf_files = [
            file for file in files
            if file["name"].lower().endswith(".pdf")
        ]

        matched_pdf = None

        for file in pdf_files:
            pdf_name = file["name"].split("/")[-1].lower().replace(".pdf", "")
            if pdf_name == base_name:
                matched_pdf = file["name"]
                break

        native_url = create_blob_read_url(matched_pdf) if matched_pdf else ""

        return {
            "project": project_id.replace("_", " "),
            "project_id": project_id,
            "batch": batch,
            "doc_id": doc_id,
            "blob_name": first_text_file,
            "text": text,
            "fields": protocol_fields,
            "native_url": native_url,
            "native_blob": matched_pdf,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )

class CaptureSaveRequest(BaseModel):
    project_id: str
    batch_id: str
    doc_id: str
    values: dict


@router.post("/save")
def save_capture(payload: CaptureSaveRequest, x_username: str = Header(default="")):
    entity = {
    "id": len(CAPTURED_ENTITIES) + 1,
    "project_id": payload.project_id,
    "batch_id": payload.batch_id,
    "doc_id": payload.doc_id,
    "captured_by": x_username,
    "linked": True,
    "values": payload.values,
}

    CAPTURED_ENTITIES.append(entity)

    return {
        "status": "saved",
        "doc_id": payload.doc_id,
        "values": payload.values,
    }
    
@router.post("/save-next")
def save_and_next(payload: CaptureSaveRequest):
    print("SAVE & NEXT RECEIVED:")
    print("DOC ID:", payload.doc_id)
    print("VALUES:", payload.values)

    return {
        "status": "saved_next",
        "message": f"Saved {payload.doc_id}. Next document ready.",
        "next_doc": {
            "project": "Project Timber",
            "batch": "Batch 004",
            "doc_id": "Doc 0002",
            "text": "This is the next sample document returned from FastAPI.",
            "fields": [
                {"label": "Name", "type": "text"},
                {"label": "SSN", "type": "text"},
                {"label": "Address", "type": "textarea"},
                {"label": "Entity Tag if Present", "type": "checkbox"},
            ],
        },
    }