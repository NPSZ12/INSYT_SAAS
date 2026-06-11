from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services.project_store import BATCHES
from app.services.azure_blob_service import list_project_files
from app.services.project_store import SEARCH_HITS

router = APIRouter(prefix="/api/batches", tags=["Batches"])


class BatchCheckoutRequest(BaseModel):
    project_id: str
    batch_id: str

class BatchCreateRequest(BaseModel):
    project_id: str
    batch_name: str
    docs_per_batch: int


class AltBatchCreateRequest(BaseModel):
    project_id: str
    folder_id: str
    batch_name: str
    docs_per_batch: int

@router.get("/")
def list_batches(project: str, x_username: str = Header(default="")):
    return [b for b in BATCHES if b["project_id"] == project]


@router.post("/checkout")
def checkout_batch(payload: BatchCheckoutRequest, x_username: str = Header(default="")):
    # Only allow one active checked-out batch per user per project
    for batch in BATCHES:
        if (
            batch["project_id"] == payload.project_id
            and batch["checked_out_by"] == x_username
            and batch["status"] == "Checked Out"
        ):
            return {
                "status": "user_already_has_batch",
                "message": "You already have a batch checked out for this project.",
                "batch": batch,
            }

    for batch in BATCHES:
        if batch["project_id"] == payload.project_id and batch["batch_id"] == payload.batch_id:
            if batch["status"] == "Available":
                batch["status"] = "Checked Out"
                batch["checked_out_by"] = x_username
                return {
                    "status": "checked_out",
                    "message": "Batch checked out successfully.",
                    "batch": batch,
                }

            return {
                "status": "not_available",
                "message": "This batch is not available.",
                "batch": batch,
            }

    return {
        "status": "not_found",
        "message": "Batch not found.",
    }
    
@router.get("/files")
def list_batch_files(project: str, batch: str):
    # Temporary: pull sample text files from Azure project.
    # Later this should filter against a real batch/document assignment table.
    

    files = list_project_files(project)

    text_files = [
        file for file in files
        if file["name"].lower().endswith(".txt")
    ]

    rows = []

    for index, file in enumerate(text_files, start=1):
        file_name = file["name"].split("/")[-1]
        doc_id = file_name.rsplit(".", 1)[0]

        rows.append({
            "doc_id": doc_id,
            "file_name": file_name,
            "status": "Ready",
        })

    return rows

@router.post("/create-review")
def create_review_batches(payload: BatchCreateRequest):
    from app.services.azure_blob_service import list_project_files

    files = list_project_files(payload.project_id)

    text_files = [
        file for file in files
        if file["name"].lower().endswith(".txt")
    ]

    already_batched_doc_ids = set()

    for batch in BATCHES:
        if batch.get("project_id") == payload.project_id:
            for doc_id in batch.get("doc_ids", []):
                already_batched_doc_ids.add(doc_id)

    available_docs = []

    for file in text_files:
        file_name = file["name"].split("/")[-1]
        doc_id = file_name.rsplit(".", 1)[0]

        if doc_id not in already_batched_doc_ids:
            available_docs.append(doc_id)

    created = []
    prefix = payload.batch_name or "Review"

    for index in range(0, len(available_docs), payload.docs_per_batch):
        chunk = available_docs[index:index + payload.docs_per_batch]
        batch_number = len([
            batch for batch in BATCHES
            if batch.get("project_id") == payload.project_id
            and batch.get("batch_type") == "review"
        ]) + 1

        batch_id = f"{prefix}_{batch_number:05d}"

        batch = {
            "project_id": payload.project_id,
            "batch_id": batch_id,
            "name": batch_id,
            "status": "Available",
            "documents": str(len(chunk)),
            "checked_out_by": "",
            "batch_type": "review",
            "doc_ids": chunk,
        }

        BATCHES.append(batch)
        created.append(batch)

    return {
        "status": "created",
        "message": f"Created {len(created)} review batch(es).",
        "batches": created,
    }


@router.post("/create-qc")
def create_qc_batches(payload: BatchCreateRequest):
    reviewed_batches = [
        batch for batch in BATCHES
        if batch.get("project_id") == payload.project_id
        and batch.get("status") == "Completed"
        and batch.get("batch_type", "review") == "review"
    ]

    reviewed_docs = []

    for batch in reviewed_batches:
        reviewed_docs.extend(batch.get("doc_ids", []))

    created = []
    prefix = payload.batch_name or "QC"

    for index in range(0, len(reviewed_docs), payload.docs_per_batch):
        chunk = reviewed_docs[index:index + payload.docs_per_batch]
        batch_number = len([
            batch for batch in BATCHES
            if batch.get("project_id") == payload.project_id
            and batch.get("batch_type") == "qc"
        ]) + 1

        batch_id = f"{prefix}_{batch_number:05d}"

        batch = {
            "project_id": payload.project_id,
            "batch_id": batch_id,
            "name": batch_id,
            "status": "Available",
            "documents": str(len(chunk)),
            "checked_out_by": "",
            "batch_type": "qc",
            "doc_ids": chunk,
        }

        BATCHES.append(batch)
        created.append(batch)

    return {
        "status": "created",
        "message": f"Created {len(created)} QC batch(es).",
        "batches": created,
    }


@router.post("/create-alt")
def create_alt_batches(payload: AltBatchCreateRequest):
    folder_hits = [
        hit for hit in SEARCH_HITS
        if hit.get("project_id") == payload.project_id
        and hit.get("folder_id") == payload.folder_id
    ]

    unique_docs = []

    for hit in folder_hits:
        doc_id = hit.get("doc_id")

        if doc_id and doc_id not in unique_docs:
            unique_docs.append(doc_id)

    created = []
    prefix = payload.batch_name or payload.folder_id

    for index in range(0, len(unique_docs), payload.docs_per_batch):
        chunk = unique_docs[index:index + payload.docs_per_batch]
        batch_number = len([
            batch for batch in BATCHES
            if batch.get("project_id") == payload.project_id
            and batch.get("batch_type") == "alt"
            and batch.get("source_folder_id") == payload.folder_id
        ]) + 1

        batch_id = f"{prefix}_{batch_number:05d}"

        batch = {
            "project_id": payload.project_id,
            "batch_id": batch_id,
            "name": batch_id,
            "status": "Available",
            "documents": str(len(chunk)),
            "checked_out_by": "",
            "batch_type": "alt",
            "source_folder_id": payload.folder_id,
            "doc_ids": chunk,
        }

        BATCHES.append(batch)
        created.append(batch)

    return {
        "status": "created",
        "message": f"Created {len(created)} Alt batch(es).",
        "batches": created,
    }