import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client

router = APIRouter(
    prefix="/api/summaries/summary-data",
    tags=["summaries-summary-data"],
)


class SummaryDataExistsRequest(BaseModel):
    client: str
    project_id: str
    pdf_name: str
    summary_key: str


class SummaryDataSaveRequest(BaseModel):
    client: str
    project_id: str
    batch_id: str | None = None
    pdf_name: str
    summary_doc_id: str | None = None
    summary_key: str
    title: str
    citation: str = ""
    original_summary: str = ""
    qc_summary: str = ""


def get_summary_data_blob_name(
    client: str,
    project_id: str,
    pdf_name: str,
):
    safe_pdf_name = pdf_name.replace("/", "_").replace("\\", "_")

    return (
        f"{client}/{project_id}/review/summary-data/"
        f"{safe_pdf_name}.json"
    )


def load_summary_data(container, blob_name: str, pdf_name: str):
    blob = container.get_blob_client(blob_name)

    if not blob.exists():
        return {
            "pdf_name": pdf_name,
            "rows": [],
        }

    data = blob.download_blob().readall()
    return json.loads(data.decode("utf-8"))


@router.post("/exists")
def summary_data_exists(payload: SummaryDataExistsRequest):
    container = get_container_client("summaries")

    blob_name = get_summary_data_blob_name(
        payload.client,
        payload.project_id,
        payload.pdf_name,
    )

    data = load_summary_data(
        container,
        blob_name,
        payload.pdf_name,
    )

    exists = any(
        row.get("summary_key") == payload.summary_key
        for row in data.get("rows", [])
    )

    return {
        "exists": exists,
        "blob_name": blob_name,
    }


@router.post("/save")
def save_summary_data(payload: SummaryDataSaveRequest):
    container = get_container_client("summaries")

    blob_name = get_summary_data_blob_name(
        payload.client,
        payload.project_id,
        payload.pdf_name,
    )

    data = load_summary_data(
        container,
        blob_name,
        payload.pdf_name,
    )

    now = datetime.now(timezone.utc).isoformat()

    new_row = {
        "pdf_name": payload.pdf_name,
        "batch_id": payload.batch_id,
        "summary_doc_id": payload.summary_doc_id,
        "summary_key": payload.summary_key,
        "title": payload.title,
        "citation": payload.citation,
        "original_summary": payload.original_summary,
        "qc_summary": payload.qc_summary,
        "last_modified": now,
    }

    rows = data.get("rows", [])

    updated = False

    for index, row in enumerate(rows):
        if row.get("summary_key") == payload.summary_key:
            rows[index] = new_row
            updated = True
            break

    if not updated:
        rows.append(new_row)

    data["pdf_name"] = payload.pdf_name
    data["rows"] = rows
    data["last_modified"] = now

    container.upload_blob(
        name=blob_name,
        data=json.dumps(data, indent=2),
        overwrite=True,
    )

    return {
        "message": "Summary data saved.",
        "updated": updated,
        "blob_name": blob_name,
        "row": new_row,
    }
    
@router.get("")
def list_summary_data(
    client: str,
    project: str,
):
    container = get_container_client("summaries")

    prefix = f"{client}/{project}/review/summary-data/"

    rows = []

    for blob in container.list_blobs(name_starts_with=prefix):
        if not blob.name.endswith(".json"):
            continue

        data = (
            container
            .get_blob_client(blob.name)
            .download_blob()
            .readall()
        )

        payload = json.loads(data.decode("utf-8"))

        for row in payload.get("rows", []):
            rows.append(row)

    rows.sort(
        key=lambda row: (
            row.get("pdf_name", ""),
            row.get("summary_key", ""),
        )
    )

    return {
        "client": client,
        "project": project,
        "rows": rows,
    }