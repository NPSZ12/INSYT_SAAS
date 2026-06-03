import csv
import io
import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from datetime import datetime, timezone
from app.services.batch_service import get_container_client

router = APIRouter(
    prefix="/api/document-overlays",
    tags=["document-overlays"],
)


DOC_ID_FIELD_CANDIDATES = [
    "doc_id",
    "doc id",
    "document id",
    "document_id",
    "docid",
    "begdoc",
    "beg doc",
    "control number",
    "control_number",
    "cds id",
    "insyt doc id",
    "insyt_doc_id",
]

def build_overlay_blob_paths(project_id: str, filename: str) -> tuple[str, str]:
    safe_project_id = project_id.strip("/")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    original_name = filename.replace("\\", "_").replace("/", "_")

    overlay_path = (
        f"{safe_project_id}/overlays/"
        f"overlay_{timestamp}_{original_name}.json"
    )

    latest_path = f"{safe_project_id}/overlays/latest_overlay.json"

    return overlay_path, latest_path

def normalize_header(value: str) -> str:
    return value.strip().lower().replace("-", " ").replace("_", " ")


def detect_doc_id_field(headers: list[str]) -> str | None:
    normalized_map = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in DOC_ID_FIELD_CANDIDATES:
        normalized_candidate = normalize_header(candidate)

        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]

    return None


def parse_csv_overlay(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    return [dict(row) for row in reader]


def parse_dat_overlay(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")

    # Concordance-style DAT usually uses þ as quote and ¶ as delimiter.
    sample = text[:5000]

    delimiter = "\x14"
    quotechar = "þ"

    if "¶" in sample:
        delimiter = "¶"
    elif "\t" in sample:
        delimiter = "\t"
    elif "," in sample:
        delimiter = ","

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter,
        quotechar=quotechar,
    )

    return [dict(row) for row in reader]


def parse_json_overlay(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")

    data = json.loads(text)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["records", "documents", "data", "rows"]:
            value = data.get(key)

            if isinstance(value, list):
                return value

    raise HTTPException(
        status_code=400,
        detail="JSON overlay must be a list or contain records/documents/data/rows.",
    )


def parse_overlay_file(filename: str, content: bytes) -> list[dict[str, Any]]:
    lower_name = filename.lower()

    if lower_name.endswith(".csv"):
        return parse_csv_overlay(content)

    if lower_name.endswith(".dat"):
        return parse_dat_overlay(content)

    if lower_name.endswith(".json"):
        return parse_json_overlay(content)

    raise HTTPException(
        status_code=400,
        detail="Unsupported overlay file type. Upload CSV, DAT, or JSON.",
    )
    
def list_project_doc_ids(project_id: str) -> set[str]:
    container = get_container_client()
    prefix = f"{project_id.strip('/')}/"

    doc_ids = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name

        if "/overlays/" in name:
            continue

        filename = name.split("/")[-1]

        if not filename:
            continue

        doc_id = filename.rsplit(".", 1)[0].strip()

        if doc_id:
            doc_ids.add(doc_id)

    return doc_ids


@router.post("/preview")
async def preview_document_overlay(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    doc_id_field: str | None = Form(None),
):
    content = await file.read()

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Missing filename.",
        )

    rows = parse_overlay_file(file.filename, content)

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Overlay file did not contain any rows.",
        )

    headers = list(rows[0].keys())

    selected_doc_id_field = doc_id_field or detect_doc_id_field(headers)

    if not selected_doc_id_field:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Could not detect Doc ID field.",
                "available_fields": headers,
            },
        )

    preview_rows = []

    for row in rows[:50]:
        doc_id = str(row.get(selected_doc_id_field, "")).strip()

        preview_rows.append(
            {
                "doc_id": doc_id,
                "metadata": row,
            }
        )

    duplicate_doc_ids = set()
    seen_doc_ids = set()

    for row in rows:
        doc_id = str(row.get(selected_doc_id_field, "")).strip()

        if not doc_id:
            continue

        if doc_id in seen_doc_ids:
            duplicate_doc_ids.add(doc_id)

        seen_doc_ids.add(doc_id)
    
    overlay_doc_ids = set()

    for row in rows:
        doc_id = str(row.get(selected_doc_id_field, "")).strip()

        if doc_id:
            overlay_doc_ids.add(doc_id)

    project_doc_ids = set()

    try:
        project_doc_ids = list_project_doc_ids(project_id)
    except Exception:
        project_doc_ids = set()

    matched_doc_ids = overlay_doc_ids.intersection(
        project_doc_ids
    )

    unmatched_overlay_doc_ids = (
        overlay_doc_ids.difference(project_doc_ids)
        if project_doc_ids
        else set()
    )

    missing_overlay_doc_ids = (
        project_doc_ids.difference(overlay_doc_ids)
        if project_doc_ids
        else set()
    )

    return {
        "project_id": project_id,
        "filename": file.filename,
        "row_count": len(rows),
        "detected_doc_id_field": selected_doc_id_field,
        "headers": headers,
        "duplicate_doc_id_count": len(duplicate_doc_ids),
        "duplicate_doc_ids_sample": sorted(list(duplicate_doc_ids))[:25],
        "validation_available": bool(project_doc_ids),
        "project_file_count": len(project_doc_ids),
        "overlay_doc_id_count": len(overlay_doc_ids),
        "matched_doc_id_count": len(matched_doc_ids),
        "unmatched_overlay_doc_id_count": len(unmatched_overlay_doc_ids),
        "missing_overlay_doc_id_count": len(missing_overlay_doc_ids),
        "unmatched_overlay_doc_ids_sample": sorted(list(unmatched_overlay_doc_ids))[:25],
        "missing_overlay_doc_ids_sample": sorted(list(missing_overlay_doc_ids))[:25],
        "preview_rows": preview_rows,
    }
    
@router.post("/commit")
async def commit_document_overlay(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    doc_id_field: str | None = Form(None),
):
    content = await file.read()

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Missing filename.",
        )

    rows = parse_overlay_file(file.filename, content)

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Overlay file did not contain any rows.",
        )

    headers = list(rows[0].keys())

    selected_doc_id_field = doc_id_field or detect_doc_id_field(headers)

    if not selected_doc_id_field:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Could not detect Doc ID field.",
                "available_fields": headers,
            },
        )

    overlay_records = []
    missing_doc_id_count = 0

    for row in rows:
        doc_id = str(row.get(selected_doc_id_field, "")).strip()

        if not doc_id:
            missing_doc_id_count += 1
            continue

        overlay_records.append(
            {
                "doc_id": doc_id,
                "metadata": row,
            }
        )

    overlay_payload = {
        "project_id": project_id,
        "source_filename": file.filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "doc_id_field": selected_doc_id_field,
        "row_count": len(rows),
        "committed_record_count": len(overlay_records),
        "missing_doc_id_count": missing_doc_id_count,
        "headers": headers,
        "records": overlay_records,
    }

    try:
        container = get_container_client()

        overlay_path, latest_path = build_overlay_blob_paths(
            project_id=project_id,
            filename=file.filename,
        )

        payload_bytes = json.dumps(
            overlay_payload,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")

        container.upload_blob(
            name=overlay_path,
            data=payload_bytes,
            overwrite=True,
        )

        container.upload_blob(
            name=latest_path,
            data=payload_bytes,
            overwrite=True,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save overlay: {str(exc)}",
        )

    return {
        "message": "Document overlay committed successfully.",
        "project_id": project_id,
        "source_filename": file.filename,
        "stored_overlay_path": overlay_path,
        "latest_overlay_path": latest_path,
        "doc_id_field": selected_doc_id_field,
        "row_count": len(rows),
        "committed_record_count": len(overlay_records),
        "missing_doc_id_count": missing_doc_id_count,
    }
    
@router.get("/{project_id}/list")
def list_document_overlays(project_id: str):
    try:
        container = get_container_client()
        prefix = f"{project_id.strip('/')}/overlays/"

        overlays = []

        for blob in container.list_blobs(name_starts_with=prefix):
            if blob.name.endswith(".json"):
                overlays.append(
                    {
                        "name": blob.name,
                        "size": blob.size,
                        "last_modified": blob.last_modified.isoformat()
                        if blob.last_modified
                        else None,
                    }
                )

        overlays.sort(
            key=lambda item: item["last_modified"] or "",
            reverse=True,
        )

        return {
            "project_id": project_id,
            "count": len(overlays),
            "overlays": overlays,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list overlays: {str(exc)}",
        )
        
@router.get("/{project_id}/latest")
def get_latest_document_overlay(project_id: str):
    try:
        container = get_container_client()
        latest_path = f"{project_id.strip('/')}/overlays/latest_overlay.json"

        blob_client = container.get_blob_client(latest_path)

        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail="No latest overlay found for this project.",
            )

        content = blob_client.download_blob().readall()
        payload = json.loads(content.decode("utf-8"))

        return payload

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read latest overlay: {str(exc)}",
        )