import csv
import io
import json
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.services.batch_service import get_container_client


router = APIRouter(
    prefix="/api/document-overlays",
    tags=["document-overlays"],
)


VALID_WORKSPACES = {"capture", "summaries", "discovery"}
VALID_OVERLAY_VIEWS = {"raw", "final"}

DOC_ID_FIELD_CANDIDATES = [
    "Doc ID",
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

UCID_FIELD_CANDIDATES = [
    "UCID",
    "ucid",
    "Unique Capture ID",
    "unique_capture_id",
    "unique capture id",
]


def clean_path(value: str | None) -> str:
    return (value or "").strip().strip("/")


def validate_workspace(workspace: str):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )


def validate_overlay_view(overlay_view: str):
    if overlay_view not in VALID_OVERLAY_VIEWS:
        raise HTTPException(
            status_code=400,
            detail="overlay_view must be raw or final.",
        )


def project_base_path(client: str | None, project_id: str) -> str:
    project_name = clean_path(project_id)
    client_name = clean_path(client)

    if client_name:
        return f"{client_name}/{project_name}"

    return project_name


def normalize_header(value: str) -> str:
    return value.strip().lower().replace("-", " ").replace("_", " ")


def unique_values(values: list[str]) -> list[str]:
    seen = set()
    output = []

    for value in values:
        clean = value.strip()

        if not clean or clean in seen:
            continue

        seen.add(clean)
        output.append(clean)

    return output

def normalize_doc_id(value: str | None) -> str:
    clean = str(value or "").strip()

    if clean.lower().endswith(".pdf"):
        clean = clean[:-4]

    return clean.strip()


def split_final_doc_ids(value: str | None) -> list[str]:
    if not value:
        return []

    return [
        doc_id
        for doc_id in [
            normalize_doc_id(item)
            for item in str(value).split(";")
        ]
        if doc_id
    ]


def flatten_final_doc_ids(
    rows: list[dict[str, Any]],
    selected_doc_id_field: str,
) -> list[str]:
    doc_ids = []

    for row in rows:
        doc_ids.extend(
            split_final_doc_ids(
                row.get(selected_doc_id_field, "")
            )
        )

    return doc_ids

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

def detect_ucid_field(headers: list[str]) -> str | None:
    normalized_map = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in UCID_FIELD_CANDIDATES:
        normalized_candidate = normalize_header(candidate)

        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]

    return None


def generate_ucid() -> str:
    return f"UCID-{uuid4().hex}"


def get_or_create_ucid(
    row: dict[str, Any],
    headers: list[str],
    overlay_view: str,
) -> str:
    ucid_field = detect_ucid_field(headers)

    if ucid_field:
        existing_ucid = str(row.get(ucid_field, "")).strip()

        if existing_ucid:
            return existing_ucid

    if overlay_view == "raw":
        return generate_ucid()

    return ""

def parse_csv_overlay(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def parse_dat_overlay(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:5000]

    delimiter = "\x14"
    quotechar = "\xfe"

    if "\xb6" in sample:
        delimiter = "\xb6"
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


def load_protocol_fields(
    workspace: str,
    project_id: str,
    client: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    container = get_container_client(workspace)

    base_path = project_base_path(client, project_id)
    project_name = clean_path(project_id)

    possible_protocol_files = [
        f"{base_path}/source/protocol/{project_name}_Protocol.json",
        f"{base_path}/{project_name}_Protocol.json",
        f"{base_path}/Protocol/{project_name}_Protocol.json",
        f"{base_path}/protocol.json",
        f"{base_path}/source/protocol/{project_name}_Protocol.xlsx",
        f"{base_path}/{project_name}_Protocol.xlsx",
        f"{base_path}/Protocol/{project_name}_Protocol.xlsx",
        f"{base_path}/protocol.xlsx",
        f"{project_name}/source/protocol/{project_name}_Protocol.json",
        f"{project_name}/{project_name}_Protocol.json",
        f"{project_name}/Protocol/{project_name}_Protocol.json",
        f"{project_name}/protocol.json",
        f"{project_name}/source/protocol/{project_name}_Protocol.xlsx",
        f"{project_name}/{project_name}_Protocol.xlsx",
        f"{project_name}/Protocol/{project_name}_Protocol.xlsx",
        f"{project_name}/protocol.xlsx",
    ]

    for blob_name in possible_protocol_files:
        blob_client = container.get_blob_client(blob_name)

        if not blob_client.exists():
            continue

        blob_data = blob_client.download_blob().readall()

        if blob_name.lower().endswith(".json"):
            payload = json.loads(blob_data.decode("utf-8"))
            return payload.get("fields", []), blob_name

        if blob_name.lower().endswith(".xlsx"):
            workbook = pd.ExcelFile(io.BytesIO(blob_data))
            fields = []

            for sheet_name in workbook.sheet_names:
                df = pd.read_excel(
                    io.BytesIO(blob_data),
                    sheet_name=sheet_name,
                    dtype=str,
                ).fillna("")

                df.columns = [str(column).strip() for column in df.columns]

                for _, row in df.iterrows():
                    section = str(
                        row.get("Section")
                        or row.get("section")
                        or ""
                    ).strip()

                    data_element = str(
                        row.get("Data Element")
                        or row.get("DataElement")
                        or row.get("Data element")
                        or row.get("data_element")
                        or ""
                    ).strip()

                    field_format = str(
                        row.get("Format")
                        or row.get("Default Format")
                        or row.get("Capture Type")
                        or row.get("Type")
                        or ""
                    ).strip()

                    notes = str(
                        row.get("Notes")
                        or row.get("Note")
                        or row.get("Description")
                        or ""
                    ).strip()

                    if not data_element:
                        continue

                    fields.append(
                        {
                            "section": section,
                            "data_element": data_element,
                            "format": field_format,
                            "default_format": field_format,
                            "notes": notes,
                            "source_sheet": sheet_name,
                        }
                    )

            return fields, blob_name

    return [], None


def get_protocol_headers(fields: list[dict[str, Any]]) -> list[str]:
    headers = []

    for field in fields:
        header = (
            field.get("data_element")
            or field.get("label")
            or field.get("name")
            or ""
        )

        if header:
            headers.append(str(header).strip())

    return unique_values(headers)


def validate_overlay_headers(
    upload_headers: list[str],
    protocol_headers: list[str],
) -> dict[str, Any]:
    expected_headers = unique_values(["Doc ID", *protocol_headers])

    upload_set = set(upload_headers)
    expected_set = set(expected_headers)

    missing_protocol_headers = [
        header for header in expected_headers
        if header not in upload_set
    ]

    extra_upload_headers = [
        header for header in upload_headers
        if header not in expected_set
    ]

    return {
        "expected_headers": expected_headers,
        "upload_headers": upload_headers,
        "headers_match_exactly": (
            len(missing_protocol_headers) == 0
            and len(extra_upload_headers) == 0
        ),
        "missing_protocol_headers": missing_protocol_headers,
        "extra_upload_headers": extra_upload_headers,
    }


def list_project_doc_ids(
    workspace: str,
    project_id: str,
    client: str | None = None,
) -> set[str]:
    container = get_container_client(workspace)

    base_path = project_base_path(client, project_id)
    prefix = f"{base_path}/source/native/"

    doc_ids = set()

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name

        if name.endswith("/"):
            continue

        filename = name.split("/")[-1]

        if not filename or filename == ".keep":
            continue

        if filename.lower().endswith(".json"):
            continue

        doc_id = filename.rsplit(".", 1)[0].strip()

        if doc_id:
            doc_ids.add(doc_id)

    return doc_ids


def build_overlay_blob_paths(
    client: str | None,
    project_id: str,
    overlay_view: str,
    filename: str,
) -> tuple[str, str]:
    base_path = project_base_path(client, project_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    original_name = filename.replace("\\", "_").replace("/", "_")

    overlay_path = (
        f"{base_path}/overlays/{overlay_view}/"
        f"overlay_{timestamp}_{original_name}.json"
    )

    latest_path = (
        f"{base_path}/overlays/{overlay_view}/latest_overlay.json"
    )

    return overlay_path, latest_path


def build_overlay_records(
    rows: list[dict[str, Any]],
    doc_id_field: str,
    overlay_view: str,
) -> tuple[list[dict[str, Any]], int]:
    headers = list(rows[0].keys()) if rows else []
    records = []
    missing_doc_id_count = 0

    for row in rows:
        doc_id = str(row.get(doc_id_field, "")).strip()

        if not doc_id:
            missing_doc_id_count += 1
            continue

        metadata = dict(row)
        ucid = get_or_create_ucid(
            row=metadata,
            headers=headers,
            overlay_view=overlay_view,
        )

        if ucid:
            metadata["UCID"] = ucid

        records.append(
            {
                "ucid": ucid,
                "doc_id": doc_id,
                "metadata": metadata,
            }
        )

    return records, missing_doc_id_count


def build_overlay_validation(
    rows: list[dict[str, Any]],
    selected_doc_id_field: str,
    project_doc_ids: set[str],
    overlay_view: str = "raw",
):
    duplicate_doc_ids = set()
    seen_doc_ids = set()
    overlay_doc_ids = set()
    all_final_doc_ids = []

    for row in rows:
        if overlay_view == "final":
            row_doc_ids = split_final_doc_ids(
                row.get(selected_doc_id_field, "")
            )

            
            all_final_doc_ids.extend(row_doc_ids)

        else:
            doc_id = normalize_doc_id(
                row.get(selected_doc_id_field, "")
            )
            row_doc_ids = [doc_id] if doc_id else []

        for doc_id in row_doc_ids:
            if not doc_id:
                continue

            if overlay_view != "final" and doc_id in seen_doc_ids:
                duplicate_doc_ids.add(doc_id)

            seen_doc_ids.add(doc_id)
            overlay_doc_ids.add(doc_id)

    normalized_project_doc_ids = {
        normalize_doc_id(doc_id)
        for doc_id in project_doc_ids
        if normalize_doc_id(doc_id)
    }

    matched_doc_ids = overlay_doc_ids.intersection(
        normalized_project_doc_ids
    )

    unmatched_overlay_doc_ids = (
        overlay_doc_ids.difference(normalized_project_doc_ids)
        if normalized_project_doc_ids
        else set()
    )

    missing_overlay_doc_ids = (
        normalized_project_doc_ids.difference(overlay_doc_ids)
        if normalized_project_doc_ids
        else set()
    )

    repeated_final_source_doc_ids = []

    if overlay_view == "final":
        final_seen = set()
        final_repeated = set()

        for doc_id in all_final_doc_ids:
            if doc_id in final_seen:
                final_repeated.add(doc_id)

            final_seen.add(doc_id)

        repeated_final_source_doc_ids = sorted(
            list(final_repeated)
        )

    return {
        "project_file_count": len(normalized_project_doc_ids),
        "overlay_doc_id_count": len(overlay_doc_ids),
        "matched_doc_id_count": len(matched_doc_ids),
        "unmatched_overlay_doc_id_count": len(unmatched_overlay_doc_ids),
        "missing_overlay_doc_id_count": len(missing_overlay_doc_ids),
        "duplicate_doc_id_count": len(duplicate_doc_ids),
        "duplicate_doc_ids_sample": sorted(list(duplicate_doc_ids))[:25],
        "repeated_final_source_doc_id_count": len(
            repeated_final_source_doc_ids
        ),
        "repeated_final_source_doc_ids_sample": repeated_final_source_doc_ids[:25],
        "unmatched_overlay_doc_ids_sample": sorted(list(unmatched_overlay_doc_ids))[:25],
        "missing_overlay_doc_ids_sample": sorted(list(missing_overlay_doc_ids))[:25],
    }


@router.post("/preview")
async def preview_document_overlay(
    workspace: str = Form(...),
    project_id: str = Form(...),
    client: str | None = Form(default=None),
    overlay_view: str = Form(...),
    file: UploadFile = File(...),
    doc_id_field: str | None = Form(None),
):
    validate_workspace(workspace)
    validate_overlay_view(overlay_view)

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

    protocol_fields, protocol_blob = load_protocol_fields(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    protocol_headers = get_protocol_headers(protocol_fields)
    header_validation = validate_overlay_headers(
        upload_headers=headers,
        protocol_headers=protocol_headers,
    )

    if overlay_view == "final":
        header_validation = {
            **header_validation,
            "headers_match_exactly": True,
            "missing_protocol_headers": [],
            "extra_upload_headers": [],
            "final_header_validation_note": (
                "Final overlays preserve uploaded deliverable headers and "
                "are not required to match the project protocol exactly."
            ),
        }

    project_doc_ids = list_project_doc_ids(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    doc_validation = build_overlay_validation(
        rows=rows,
        selected_doc_id_field=selected_doc_id_field,
        project_doc_ids=project_doc_ids,
        overlay_view=overlay_view,
    )

    preview_rows = []

    for index, row in enumerate(rows[:50]):
        metadata = dict(row)

        if overlay_view == "final":
            doc_ids = split_final_doc_ids(
                row.get(selected_doc_id_field, "")
            )

            preview_rows.append(
                {
                    "ucid": "",
                    "final_entity_id": f"final-{index + 1:06d}",
                    "doc_id": ";".join(doc_ids),
                    "doc_ids": doc_ids,
                    "metadata": metadata,
                }
            )

            continue

        doc_id = normalize_doc_id(
            row.get(selected_doc_id_field, "")
        )

        ucid = get_or_create_ucid(
            row=metadata,
            headers=headers,
            overlay_view=overlay_view,
        )

        if ucid:
            metadata["UCID"] = ucid

        preview_rows.append(
            {
                "ucid": ucid,
                "doc_id": doc_id,
                "metadata": metadata,
            }
        )
        
    final_doc_ids = (
        flatten_final_doc_ids(
            rows=rows,
            selected_doc_id_field=selected_doc_id_field,
        )
        if overlay_view == "final"
        else []
    )

    return {
        "workspace": workspace,
        "client": clean_path(client),
        "project_id": project_id,
        "overlay_view": overlay_view,
        "filename": file.filename,
        "row_count": len(rows),
        "detected_doc_id_field": selected_doc_id_field,
        "final_entity_count": len(rows) if overlay_view == "final" else 0,
        "expanded_doc_id_count": len(final_doc_ids),
        "unique_expanded_doc_id_count": len(set(final_doc_ids)),
        "expanded_doc_ids_sample": sorted(set(final_doc_ids))[:25],
        "headers": headers,
        "protocol_blob": protocol_blob,
        "protocol_header_count": len(protocol_headers),
        "validation_available": bool(project_doc_ids),
        **header_validation,
        **doc_validation,
        "preview_rows": preview_rows,
    }


@router.post("/commit")
async def commit_document_overlay(
    workspace: str = Form(...),
    project_id: str = Form(...),
    client: str | None = Form(default=None),
    overlay_view: str = Form(...),
    file: UploadFile = File(...),
    doc_id_field: str | None = Form(None),
):
    validate_workspace(workspace)
    validate_overlay_view(overlay_view)

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

    protocol_fields, protocol_blob = load_protocol_fields(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    protocol_headers = get_protocol_headers(protocol_fields)
    header_validation = validate_overlay_headers(
        upload_headers=headers,
        protocol_headers=protocol_headers,
    )

    if overlay_view == "final":
        header_validation = {
            **header_validation,
            "headers_match_exactly": True,
            "missing_protocol_headers": [],
            "extra_upload_headers": [],
            "final_header_validation_note": (
                "Final overlays preserve uploaded deliverable headers and "
                "are not required to match the project protocol exactly."
            ),
        }

    if overlay_view == "final":
        committed_headers = headers
    else:
        committed_headers = [
            header for header in header_validation["expected_headers"]
            if header in headers and header != "Doc ID"
        ]

    overlay_records = []
    missing_doc_id_count = 0

    for index, row in enumerate(rows):
        metadata = {
            header: row.get(header, "")
            for header in committed_headers
        }

        if overlay_view == "final":
            doc_ids = split_final_doc_ids(
                row.get(selected_doc_id_field, "")
            )

            if not doc_ids:
                missing_doc_id_count += 1
                continue

            overlay_records.append(
                {
                    "ucid": "",
                    "final_entity_id": f"final-{index + 1:06d}",
                    "doc_id": ";".join(doc_ids),
                    "doc_ids": doc_ids,
                    "metadata": metadata,
                }
            )

            continue

        doc_id = normalize_doc_id(
            row.get(selected_doc_id_field, "")
        )

        if not doc_id:
            missing_doc_id_count += 1
            continue

        ucid = get_or_create_ucid(
            row=row,
            headers=headers,
            overlay_view=overlay_view,
        )

        if ucid:
            metadata["UCID"] = ucid

        overlay_records.append(
            {
                "ucid": ucid,
                "doc_id": doc_id,
                "metadata": metadata,
            }
        )

    project_doc_ids = list_project_doc_ids(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    doc_validation = build_overlay_validation(
        rows=rows,
        selected_doc_id_field=selected_doc_id_field,
        project_doc_ids=project_doc_ids,
        overlay_view=overlay_view,
    )
    
    final_doc_ids = (
        flatten_final_doc_ids(
            rows=rows,
            selected_doc_id_field=selected_doc_id_field,
        )
        if overlay_view == "final"
        else []
    )

    overlay_payload = {
        "workspace": workspace,
        "client": clean_path(client),
        "project_id": project_id,
        "overlay_view": overlay_view,
        "source_filename": file.filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "doc_id_field": selected_doc_id_field,
        "row_count": len(rows),
        "final_entity_count": len(rows) if overlay_view == "final" else 0,
        "expanded_doc_id_count": len(final_doc_ids),
        "unique_expanded_doc_id_count": len(set(final_doc_ids)),
        "committed_record_count": len(overlay_records),
        "missing_doc_id_count": missing_doc_id_count,
        "upload_headers": headers,
        "committed_headers": committed_headers,
        "ignored_extra_headers": header_validation["extra_upload_headers"],
        "missing_protocol_headers": header_validation["missing_protocol_headers"],
        "protocol_blob": protocol_blob,
        "records": overlay_records,
        "validation": {
            **header_validation,
            **doc_validation,
        },
    }

    try:
        container = get_container_client(workspace)

        overlay_path, latest_path = build_overlay_blob_paths(
            client=client,
            project_id=project_id,
            overlay_view=overlay_view,
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
        "workspace": workspace,
        "client": clean_path(client),
        "project_id": project_id,
        "overlay_view": overlay_view,
        "source_filename": file.filename,
        "stored_overlay_path": overlay_path,
        "latest_overlay_path": latest_path,
        "doc_id_field": selected_doc_id_field,
        "row_count": len(rows),
        "final_entity_count": len(rows) if overlay_view == "final" else 0,
        "expanded_doc_id_count": len(final_doc_ids),
        "unique_expanded_doc_id_count": len(set(final_doc_ids)),
        "committed_record_count": len(overlay_records),
        "missing_doc_id_count": missing_doc_id_count,
        "headers_match_exactly": header_validation["headers_match_exactly"],
        "committed_headers": committed_headers,
        "ignored_extra_headers": header_validation["extra_upload_headers"],
        "missing_protocol_headers": header_validation["missing_protocol_headers"],
        "validation": {
            **header_validation,
            **doc_validation,
        },
    }


@router.get("/{project_id}/list")
def list_document_overlays(
    project_id: str,
    workspace: str = Query(default="capture"),
    client: str | None = Query(default=None),
    overlay_view: str | None = Query(default=None),
):
    validate_workspace(workspace)

    if overlay_view:
        validate_overlay_view(overlay_view)

    try:
        container = get_container_client(workspace)
        base_path = project_base_path(client, project_id)

        if overlay_view:
            prefix = f"{base_path}/overlays/{overlay_view}/"
        else:
            prefix = f"{base_path}/overlays/"

        overlays = []

        for blob in container.list_blobs(name_starts_with=prefix):
            if not blob.name.endswith(".json"):
                continue

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
            "workspace": workspace,
            "client": clean_path(client),
            "project_id": project_id,
            "overlay_view": overlay_view,
            "count": len(overlays),
            "overlays": overlays,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list overlays: {str(exc)}",
        )


@router.get("/{project_id}/latest")
def get_latest_document_overlay(
    project_id: str,
    workspace: str = Query(default="capture"),
    client: str | None = Query(default=None),
    overlay_view: str = Query(default="raw"),
):
    validate_workspace(workspace)
    validate_overlay_view(overlay_view)

    try:
        container = get_container_client(workspace)
        base_path = project_base_path(client, project_id)
        latest_path = f"{base_path}/overlays/{overlay_view}/latest_overlay.json"

        blob_client = container.get_blob_client(latest_path)

        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail="No latest overlay found for this project/view.",
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