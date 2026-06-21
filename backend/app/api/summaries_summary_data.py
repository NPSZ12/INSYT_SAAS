import json
import os
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

def summary_sets_project_key(value: str | None) -> str:
    return (
        str(value or "")
        .strip()
        .strip("/")
        .replace("\\", "/")
        .replace(" ", "_")
    )


def summary_sets_project_root(client: str, project: str) -> str:
    return (
        f"{str(client or '').strip().strip('/')}"
        f"/summaries/{summary_sets_project_key(project)}"
    )


def list_summary_set_qc_blobs(container, client: str, project: str):
    prefix = f"{summary_sets_project_root(client, project)}/QC/summary_sets/"

    return [
        blob.name
        for blob in container.list_blobs(name_starts_with=prefix)
        if str(blob.name).endswith(".json")
    ]


def read_json_blob(container, blob_name: str):
    data = (
        container
        .get_blob_client(blob_name)
        .download_blob()
        .readall()
    )

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

    legacy_prefix = f"{client}/{project}/review/summary-data/"

    rows = []

    # Existing / legacy completed QC summaries.
    for blob in container.list_blobs(name_starts_with=legacy_prefix):
        if not blob.name.endswith(".json"):
            continue

        try:
            payload = read_json_blob(container, blob.name)
        except Exception:
            continue

        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue

            rows.append(
                {
                    **row,
                    "source": row.get("source") or "summary_data",
                }
            )

    # New Summary Set QC linked saves.
    for qc_blob_path in list_summary_set_qc_blobs(
        container,
        client,
        project,
    ):
        try:
            qc_payload = read_json_blob(container, qc_blob_path)
        except Exception:
            continue

        for saved in qc_payload.get("saved_summaries") or []:
            if not isinstance(saved, dict):
                continue

            if not saved.get("linked", True):
                continue

            rows.append(
                {
                    "client": client,
                    "project": project,
                    "project_id": project,
                    "pdf_name": (
                        qc_payload.get("source_pdf_name")
                        or saved.get("source_pdf_name")
                        or saved.get("source_doc_id")
                        or ""
                    ),
                    "batch_id": (
                        saved.get("batch_summary_set_id")
                        or qc_payload.get("batch_summary_set_id")
                        or ""
                    ),
                    "summary_doc_id": saved.get("summary_id") or "",
                    "summary_key": (
                        saved.get("title")
                        or saved.get("summary_id")
                        or ""
                    ),
                    "title": saved.get("title") or "",
                    "citation": saved.get("citation") or "",
                    "original_summary": saved.get("original_summary") or "",
                    "qc_summary": saved.get("qc_summary") or "",
                    "saved_by": saved.get("saved_by") or "",
                    "saved_at": saved.get("saved_at") or "",
                    "last_modified": (
                        saved.get("updated_at")
                        or saved.get("saved_at")
                        or ""
                    ),
                    "updated_at": (
                        saved.get("updated_at")
                        or saved.get("saved_at")
                        or ""
                    ),
                    "source": "summary_set_qc",
                    "batch_summary_set_id": (
                        saved.get("batch_summary_set_id")
                        or qc_payload.get("batch_summary_set_id")
                        or ""
                    ),
                    "source_doc_id": (
                        saved.get("source_doc_id")
                        or qc_payload.get("source_doc_id")
                        or ""
                    ),
                    "link_id": saved.get("link_id") or "",
                    "linked": saved.get("linked", True),
                }
            )

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
        "count": len(rows),
    }