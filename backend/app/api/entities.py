import io
import os
import re
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.project_store import CAPTURED_ENTITIES
from app.services.protocol_service import load_protocol_fields

import csv
import json
from typing import Any

from app.services.batch_service import get_container_client
from app.services.storage_paths import build_project_base_path
from app.api.processing_center_azure import (
    _read_processing_json_blob,
    _write_processing_json_blob,
)


def clean_path(value: str | None) -> str:
    return str(value or "").strip().strip("/")


def project_base_path(
    workspace: str,
    client: str | None,
    project: str,
) -> str:
    client_name = clean_path(client)
    project_name = clean_path(project)
    workspace_name = clean_path(workspace)

    if not client_name:
        raise HTTPException(
            status_code=400,
            detail="Client is required for entity paths.",
        )

    return build_project_base_path(
        workspace=workspace_name,
        client=client_name,
        project=project_name,
    )


def normalize_doc_lookup(value: str) -> str:
    clean = str(value or "").strip()
    clean = clean.split("/")[-1]

    #
    # Preserve INSYT workbook-child Doc IDs such as:
    #
    #   INSYT000000034.1
    #   INSYT000000034.2
    #
    # Strip only a real file extension, not the numeric
    # child suffix.
    #
    known_extensions = (
        ".csv",
        ".txt",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        ".ods",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".msg",
        ".eml",
        ".rtf",
        ".html",
        ".htm",
        ".xml",
        ".json",
    )

    lower_clean = clean.lower()

    for extension in known_extensions:
        if lower_clean.endswith(extension):
            clean = clean[
                : -len(extension)
            ]
            break

    return (
        clean
        .replace("_", " ")
        .lower()
    )

def get_document_review_blob_name(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
) -> str:
    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )
    clean_doc_id = (
        str(
            doc_id
            or ""
        )
        .strip()
        .split("/")[-1]
    )

    known_extensions = (
        ".csv",
        ".txt",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        ".ods",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".msg",
        ".eml",
        ".rtf",
        ".html",
        ".htm",
        ".xml",
        ".json",
    )

    lower_clean_doc_id = (
        clean_doc_id.lower()
    )

    for extension in known_extensions:
        if lower_clean_doc_id.endswith(
            extension
        ):
            clean_doc_id = clean_doc_id[
                : -len(extension)
            ]
            break

    return (
        f"{base_path}/Review/documents/"
        f"{clean_doc_id}.json"
    )


def load_document_review_state(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
) -> dict:
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
        workspace,
        client,
        project,
        doc_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return {}

    return json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )


def list_project_document_review_states(
    workspace: str,
    client: str | None,
    project: str,
) -> list[dict[str, Any]]:
    container = get_container_client(workspace)
    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )
    prefix = f"{base_path}/Review/documents/"

    states = []

    for blob in container.list_blobs(name_starts_with=prefix):
        if not blob.name.endswith(".json"):
            continue

        states.append(
            json.loads(
                container
                .get_blob_client(blob.name)
                .download_blob()
                .readall()
                .decode("utf-8")
            )
        )

    return states


def entity_from_review_state(
    state: dict,
    linked_entity: dict,
    index: int,
) -> dict:
    ucid = (
        linked_entity.get("ucid")
        or linked_entity.get("UCID")
        or ""
    )

    return {
        "id": linked_entity.get("id") or ucid or f"{state.get('doc_id', '')}-{index}",
        "ucid": ucid,
        "UCID": ucid,
        "project_id": state.get("project_id", ""),
        "batch_id": linked_entity.get(
            "batch_id",
            state.get("last_batch_id", ""),
        ),
        "doc_id": state.get("doc_id", ""),
        "captured_by": linked_entity.get(
            "linked_by",
            state.get("last_reviewed_by", ""),
        ),
        "linked": linked_entity.get("linked", True),
        "source": linked_entity.get("source", "manual"),
        "values": {
            "UCID": ucid,
            **linked_entity.get("values", {}),
        },
    }
    
def is_deleted_entity(
    state: dict,
    entity: dict,
) -> bool:
    entity_ucid = (
        entity.get("ucid")
        or entity.get("UCID")
        or entity.get("values", {}).get("UCID")
        or ""
    )

    entity_id = str(entity.get("id", ""))

    for deleted in state.get("deleted_entities", []):
        deleted_ucid = (
            deleted.get("ucid")
            or deleted.get("UCID")
            or deleted.get("values", {}).get("UCID")
            or ""
        )

        deleted_id = str(deleted.get("id", ""))

        if entity_ucid and deleted_ucid and entity_ucid == deleted_ucid:
            return True

        if entity_id and deleted_id and entity_id == deleted_id:
            return True

    return False

def load_latest_overlay_records(
    workspace: str,
    client: str | None,
    project: str,
    overlay_view: str = "raw",
) -> list[dict[str, Any]]:
    container = get_container_client(workspace)
    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )
    latest_path = f"{base_path}/overlays/{overlay_view}/latest_overlay.json"

    blob_client = container.get_blob_client(latest_path)

    if not blob_client.exists():
        return []

    payload = json.loads(
        blob_client.download_blob().readall().decode("utf-8")
    )

    return payload.get("records", [])

def load_cyber2_raw_capture_records(
    workspace: str,
    client: str | None,
    project: str,
) -> list[dict[str, Any]]:

    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    raw_capture_path = (
        f"{base_path}/cyber2/"
        f"raw_capture/"
        f"latest_raw_capture.json"
    )

    try:
        payload = (
            _read_processing_json_blob(
                raw_capture_path
            )
        )

    except Exception:
        return []

    if not isinstance(
        payload,
        dict,
    ):
        return []

    records = (
        payload.get(
            "records"
        )
        or []
    )

    if not isinstance(
        records,
        list,
    ):
        return []

    return [
        record
        for record
        in records
        if isinstance(
            record,
            dict,
        )
    ]

def load_cyber2_ai_capture_records(
    workspace: str,
    client: str | None,
    project: str,
) -> list[dict[str, Any]]:

    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    ai_capture_path = (
        f"{base_path}/cyber2/"
        f"ai_capture/"
        f"latest_ai_capture.json"
    )

    try:
        payload = (
            _read_processing_json_blob(
                ai_capture_path
            )
        )

    except Exception:
        return []

    if not isinstance(
        payload,
        dict,
    ):
        return []

    records = (
        payload.get(
            "records"
        )
        or []
    )

    if not isinstance(
        records,
        list,
    ):
        return []

    return [
        record
        for record
        in records
        if isinstance(
            record,
            dict,
        )
    ]

def safe_export_name(value: str, fallback: str = "export") -> str:
    clean = "".join(
        character
        if character.isalnum() or character in (" ", "-", "_")
        else "_"
        for character in str(value or "").strip()
    )

    clean = "_".join(clean.split())

    return clean or fallback


def find_blob_for_doc_id(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
    folder: str,
):
    container = get_container_client(workspace)
    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )
    normalized_target = normalize_doc_lookup(doc_id)

    prefix = f"{base_path}/{folder.strip('/')}/"

    for blob in container.list_blobs(name_starts_with=prefix):
        if blob.name.endswith("/"):
            continue

        filename = blob.name.split("/")[-1]

        if not filename or filename == ".keep":
            continue

        blob_doc_id = normalize_doc_lookup(filename)

        if blob_doc_id == normalized_target:
            return blob.name

    return ""


def read_blob_bytes(
    workspace: str,
    blob_name: str,
) -> bytes:
    container = get_container_client(workspace)

    return (
        container
        .get_blob_client(blob_name)
        .download_blob()
        .readall()
    )


def build_source_docs_csv(
    payload: "EntitySourceDocsExportRequest",
    exported_rows: list[dict[str, Any]],
) -> bytes:
    output = io.StringIO()

    fieldnames = [
        "Captured Entity",
        "INSYT UID",
        "Project",
        "Doc ID",
        "Native Exported",
        "Text Exported",
        "Native Blob",
        "Text Blob",
        "Status",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in exported_rows:
        writer.writerow(
            {
                "Captured Entity": payload.entity,
                "INSYT UID": payload.entity_uid,
                "Project": payload.project,
                "Doc ID": row.get("doc_id", ""),
                "Native Exported": "Yes" if row.get("native_exported") else "",
                "Text Exported": "Yes" if row.get("text_exported") else "",
                "Native Blob": row.get("native_blob", ""),
                "Text Blob": row.get("text_blob", ""),
                "Status": row.get("status", ""),
            }
        )

    return output.getvalue().encode("utf-8-sig")

def build_filtered_source_docs_csv(
    payload: "FilteredSourceDocsZipRequest",
    exported_rows: list[dict[str, Any]],
) -> bytes:
    output = io.StringIO()

    fieldnames = [
        "Project",
        "Doc ID",
        "Native Exported",
        "Text Exported",
        "Native Blob",
        "Text Blob",
        "Status",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in exported_rows:
        writer.writerow(
            {
                "Project": payload.project,
                "Doc ID": row.get("doc_id", ""),
                "Native Exported": "Yes" if row.get("native_exported") else "",
                "Text Exported": "Yes" if row.get("text_exported") else "",
                "Native Blob": row.get("native_blob", ""),
                "Text Blob": row.get("text_blob", ""),
                "Status": row.get("status", ""),
            }
        )

    return output.getvalue().encode("utf-8-sig")

router = APIRouter(prefix="/api/entities", tags=["Captured Entities"])


class EntityUpdateRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    doc_id: str
    ucid: str
    values: dict


class EntityUnlinkRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    doc_id: str
    ucid: str


class EntityDeleteRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    doc_id: str
    ucid: str = ""
    entity_id: str | int = ""

class AiEntityReviewRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    doc_id: str
    ai_entity_id: str
    status: str
    reviewed_values: dict[str, Any] | None = None
    reviewed_by: str = ""

class EntitySourceDocsExportRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    entity: str = ""
    entity_uid: str = ""
    doc_ids: list[str]
    include_native: bool = True
    include_text: bool = True
    
class FilteredSourceDocsZipRequest(BaseModel):
    workspace: str = "capture"
    client: str = ""
    project: str
    doc_ids: list[str]
    zip_label: str = "Filtered_Source_Documents"
    include_native: bool = True
    include_text: bool = True

@router.get("/")
def list_entities(
    project: str,
    batch: str = "",
    workspace: str = "capture",
    client: str = "",
    view: str = "raw",
    x_username: str = Header(default=""),
):
    protocol_fields = load_protocol_fields(project)

    headers = [
        field.get("label") or field.get("data_element") or ""
        for field in protocol_fields
    ]

    headers = [
        header for header in headers
        if header and header.upper() != "UCID"
    ]

    requested_view = str(
        view or ""
    ).strip().lower()

    normalized_view = (
        "final"
        if requested_view == "final"
        else (
            "ai"
            if requested_view == "ai"
            else "raw"
        )
    )
    
    if normalized_view == "final":
        final_records = load_latest_overlay_records(
            workspace=workspace,
            client=client,
            project=project,
            overlay_view="final",
        )

        final_headers = []

        for record in final_records:
            metadata = record.get("metadata", {})

            for key in metadata.keys():
                if key and key not in final_headers:
                    final_headers.append(key)

        rows = []

        for record in final_records:
            row = {
                "Doc ID": record.get("doc_id", ""),
            }

            metadata = record.get("metadata", {})

            for header in final_headers:
                value = metadata.get(header, "")

                if isinstance(value, bool):
                    row[header] = "Yes" if value else ""
                else:
                    row[header] = value

            rows.append(row)

        return {
            "headers": ["Doc ID"] + final_headers,
            "rows": rows,
            "source": "final_overlay",
        }

    if normalized_view == "ai":

        ai_records = (
            load_cyber2_ai_capture_records(
                workspace=workspace,
                client=client,
                project=project,
            )
        )

        ai_headers = [
            "AI Entity ID",
            "AI Status",
            "AI Confidence",
            "Source Filename",
        ]

        value_headers: list[str] = []

        rows = []

        for record in ai_records:

            values = (
                record.get(
                    "values"
                )
                or {}
            )

            if not isinstance(
                values,
                dict,
            ):
                values = {}

            for key in values.keys():
                clean_key = str(
                    key or ""
                ).strip()

                if (
                    clean_key
                    and clean_key
                    not in value_headers
                ):
                    value_headers.append(
                        clean_key
                    )

            provenance = (
                record.get(
                    "provenance"
                )
                or {}
            )

            confidence = (
                record.get(
                    "confidence"
                )
            )

            confidence_display = ""

            if confidence is not None:
                try:
                    confidence_display = (
                        f"{float(confidence) * 100:.0f}%"
                    )
                except Exception:
                    confidence_display = (
                        str(
                            confidence
                        )
                    )

            row = {
                "Doc ID": (
                    record.get(
                        "doc_id"
                    )
                    or ""
                ),

                "AI Entity ID": (
                    record.get(
                        "ai_entity_id"
                    )
                    or ""
                ),

                "AI Status": (
                    record.get(
                        "status"
                    )
                    or "pending"
                ),

                "AI Confidence":
                    confidence_display,

                "Source Filename": (
                    provenance.get(
                        "source_filename"
                    )
                    or ""
                ),

                **values,
            }

            rows.append(
                row
            )

        return {
            "headers": [
                "Doc ID",
                *ai_headers,
                *value_headers,
            ],
            "rows":
                rows,
            "source":
                "cyber2_ai_capture",
        }

    matching_entities = []

    for state in list_project_document_review_states(
        workspace=workspace,
        client=client,
        project=project,
    ):
        for index, linked_entity in enumerate(
            state.get("linked_entities", [])
        ):
            if not linked_entity.get("linked", True):
                continue

            if is_deleted_entity(state, linked_entity):
                continue

            matching_entities.append(
                entity_from_review_state(
                    state,
                    linked_entity,
                    index,
                )
            )

    matching_entities.extend(
        entity for entity in CAPTURED_ENTITIES
        if entity.get("project_id") == project
        and entity.get("linked", True)
        and (not batch or entity.get("batch_id") == batch)
        and entity.get("entity_view", "raw") == normalized_view
    )
    
    if normalized_view == "raw":
        for index, record in enumerate(
            load_cyber2_raw_capture_records(
                workspace=workspace,
                client=client,
                project=project,
            )
        ):
            metadata = (
                record.get(
                    "metadata"
                )
                or {}
            )

            provenance = (
                record.get(
                    "provenance"
                )
                or {}
            )

            matching_entities.append(
                {
                    "id": (
                        f"cyber2-xl-"
                        f"{index}"
                    ),

                    "ucid": (
                        record.get(
                            "ucid"
                        )
                        or metadata.get(
                            "UCID"
                        )
                        or ""
                    ),

                    "UCID": (
                        record.get(
                            "ucid"
                        )
                        or metadata.get(
                            "UCID"
                        )
                        or ""
                    ),

                    "project_id":
                        project,

                    "batch_id":
                        "Cyber2 XL",

                    "doc_id": (
                        record.get(
                            "doc_id"
                        )
                        or ""
                    ),

                    "captured_by":
                        "Cyber² XL",

                    "linked":
                        True,

                    "source":
                        "cyber2_xl",

                    "xl_mapped":
                        True,

                    "values":
                        metadata,

                    "provenance":
                        provenance,
                }
            )

    captured_value_headers = []

    for entity in matching_entities:
        for key in entity.get("values", {}).keys():
            if (
                key
                and key.upper() != "UCID"
                and key not in headers
                and key not in captured_value_headers
            ):
                captured_value_headers.append(key)

    headers = headers + captured_value_headers

    rows = []

    for entity in matching_entities:
        row = {
            "UCID": entity.get("ucid", "") or entity.get("UCID", ""),
            "Doc ID": entity.get("doc_id", ""),
        }

        values = entity.get("values", {})

        for header in headers:
            value = values.get(header, "")

            if isinstance(value, bool):
                row[header] = "Yes" if value else ""
            else:
                row[header] = value

        rows.append(row)

    return { 
        "headers": ["UCID", "Doc ID"] + headers,
        "rows": rows,
    }


@router.get("/document")
def list_document_entities(
    project: str,
    batch: str = "",
    doc: str = "",
    client: str = "",
    workspace: str = "capture",
    view: str = "raw",
    x_username: str = Header(default=""),
):
    normalized_doc = normalize_doc_lookup(doc)

    requested_view = str(
        view or ""
    ).strip().lower()

    if requested_view == "ai":

        matching_ai_entities = []

        for record in (
            load_cyber2_ai_capture_records(
                workspace=workspace,
                client=client,
                project=project,
            )
        ):
            record_doc_id = str(
                record.get(
                    "doc_id"
                )
                or ""
            ).strip()

            if (
                normalize_doc_lookup(
                    record_doc_id
                )
                != normalized_doc
            ):
                continue

            provenance = (
                record.get(
                    "provenance"
                )
                or {}
            )

            matching_ai_entities.append(
                {
                    "id": (
                        record.get(
                            "ai_entity_id"
                        )
                        or ""
                    ),

                    "ai_entity_id": (
                        record.get(
                            "ai_entity_id"
                        )
                        or ""
                    ),

                    "doc_id":
                        record_doc_id,

                    "status": (
                        record.get(
                            "status"
                        )
                        or "pending"
                    ),

                    "confidence":
                        record.get(
                            "confidence"
                        ),

                    "values": (
                        record.get(
                            "values"
                        )
                        or {}
                    ),

                    "source_text": (
                        record.get(
                            "source_text"
                        )
                        or ""
                    ),

                    "source_page": (
                        record.get(
                            "source_page"
                        )
                        or ""
                    ),

                    "source_record_id": (
                        record.get(
                            "source_record_id"
                        )
                        or ""
                    ),

                    "source_field": (
                        record.get(
                            "source_field"
                        )
                        or ""
                    ),

                    "provenance":
                        provenance,

                    "source":
                        "ai_extraction",
                }
            )

        return matching_ai_entities

    review_state = load_document_review_state(
        workspace=workspace,
        client=client,
        project=project,
        doc_id=doc,
    )

    manual_entities = []

    for index, linked_entity in enumerate(
        review_state.get("linked_entities", [])
    ):
        if not linked_entity.get("linked", True):
            continue

        if is_deleted_entity(review_state, linked_entity):
            continue

        manual_entities.append(
            entity_from_review_state(
                review_state,
                linked_entity,
                index,
            )
        )

    overlay_entities = []

    for index, record in enumerate(
        load_latest_overlay_records(
            workspace=workspace,
            client=client,
            project=project,
            overlay_view=view,
        )
    ):
        record_doc_id = str(record.get("doc_id", "")).strip()

        if normalize_doc_lookup(record_doc_id) != normalized_doc:
            continue

        overlay_entity = {
            "id": f"overlay-{index}",
            "ucid": record.get("ucid", "") or record.get("metadata", {}).get("UCID", ""),
            "UCID": record.get("ucid", "") or record.get("metadata", {}).get("UCID", ""),
            "project_id": project,
            "batch_id": batch or "Overlay",
            "doc_id": record_doc_id,
            "captured_by": "Overlay Upload",
            "linked": True,
            "source": "overlay",
            "xl_mapped": True,
            "values": record.get("metadata", {}),
        }

        if is_deleted_entity(review_state, overlay_entity):
            continue

        overlay_entities.append(
            overlay_entity
        )

    cyber2_entities = []

    if (
        str(
            view or ""
        ).strip().lower()
        != "final"
    ):
        for index, record in enumerate(
            load_cyber2_raw_capture_records(
                workspace=workspace,
                client=client,
                project=project,
            )
        ):
            record_doc_id = str(
                record.get(
                    "doc_id"
                )
                or ""
            ).strip()

            if (
                normalize_doc_lookup(
                    record_doc_id
                )
                != normalized_doc
            ):
                continue

            metadata = (
                record.get(
                    "metadata"
                )
                or {}
            )

            provenance = (
                record.get(
                    "provenance"
                )
                or {}
            )

            cyber2_entity = {
                "id": (
                    f"cyber2-xl-"
                    f"{index}"
                ),

                "ucid": (
                    record.get(
                        "ucid"
                    )
                    or metadata.get(
                        "UCID"
                    )
                    or ""
                ),

                "UCID": (
                    record.get(
                        "ucid"
                    )
                    or metadata.get(
                        "UCID"
                    )
                    or ""
                ),

                "project_id":
                    project,

                "batch_id":
                    "Cyber2 XL",

                "doc_id":
                    record_doc_id,

                "captured_by":
                    "Cyber² XL",

                "linked":
                    True,

                "source":
                    "cyber2_xl",

                "xl_mapped":
                    True,

                "values":
                    metadata,

                "provenance":
                    provenance,
            }

            if is_deleted_entity(
                review_state,
                cyber2_entity,
            ):
                continue

            cyber2_entities.append(
                cyber2_entity
            )

    return (
        manual_entities
        + overlay_entities
        + cyber2_entities
    )

@router.post("/ai-candidate/review")
def review_ai_candidate(
    payload: AiEntityReviewRequest,
):
    workspace = clean_path(
        payload.workspace
    ) or "capture"

    client = clean_path(
        payload.client
    )

    project = clean_path(
        payload.project
    )

    doc_id = str(
        payload.doc_id or ""
    ).strip()

    ai_entity_id = str(
        payload.ai_entity_id or ""
    ).strip()

    status = str(
        payload.status or ""
    ).strip().lower()

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not doc_id:
        raise HTTPException(
            status_code=400,
            detail="Doc ID is required.",
        )

    if not ai_entity_id:
        raise HTTPException(
            status_code=400,
            detail="AI Entity ID is required.",
        )

    if status not in {
        "approved",
        "rejected",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "AI Entity status must be "
                "approved or rejected."
            ),
        )

    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    ai_capture_path = (
        f"{base_path}/cyber2/"
        f"ai_capture/"
        f"latest_ai_capture.json"
    )

    try:
        ai_capture_payload = (
            _read_processing_json_blob(
                ai_capture_path
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "AI Capture data was not found."
            ),
        ) from exc

    if not isinstance(
        ai_capture_payload,
        dict,
    ):
        raise HTTPException(
            status_code=500,
            detail="AI Capture data is invalid.",
        )

    records = (
        ai_capture_payload.get(
            "records"
        )
        or []
    )

    if not isinstance(
        records,
        list,
    ):
        raise HTTPException(
            status_code=500,
            detail="AI Capture records are invalid.",
        )

    matched_record = None

    normalized_doc = (
        normalize_doc_lookup(
            doc_id
        )
    )

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            continue

        record_ai_entity_id = str(
            record.get(
                "ai_entity_id"
            )
            or ""
        ).strip()

        record_doc_id = str(
            record.get(
                "doc_id"
            )
            or ""
        ).strip()

        if (
            record_ai_entity_id
            != ai_entity_id
        ):
            continue

        if (
            normalize_doc_lookup(
                record_doc_id
            )
            != normalized_doc
        ):
            continue

        matched_record = record
        break

    if matched_record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "AI Entity candidate was not found "
                "for this document."
            ),
        )

    reviewed_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    original_values = (
        matched_record.get(
            "values"
        )
        or {}
    )

    if not isinstance(
        original_values,
        dict,
    ):
        original_values = {}

    reviewed_values = (
        payload.reviewed_values
        if isinstance(
            payload.reviewed_values,
            dict,
        )
        else {}
    )

    matched_record[
        "status"
    ] = status

    matched_record[
        "reviewed_at"
    ] = reviewed_at

    matched_record[
        "reviewed_by"
    ] = str(
        payload.reviewed_by or ""
    ).strip()

    if status == "approved":
        matched_record[
            "reviewed_values"
        ] = reviewed_values

        matched_record[
            "review_result"
        ] = (
            "approved"
            if reviewed_values
            == original_values
            else "edited_approved"
        )

    else:
        matched_record[
            "reviewed_values"
        ] = None

        matched_record[
            "review_result"
        ] = "rejected"

    ai_capture_payload[
        "updated_at"
    ] = reviewed_at

    _write_processing_json_blob(
        blob_path=ai_capture_path,
        payload=ai_capture_payload,
        overwrite=True,
    )

    return {
        "status": status,
        "ai_entity_id":
            ai_entity_id,
        "doc_id":
            doc_id,
        "review_result":
            matched_record.get(
                "review_result"
            ),
        "reviewed_at":
            reviewed_at,
    }

@router.post("/export-source-docs")
def export_source_docs(
    payload: EntitySourceDocsExportRequest,
):
    if not payload.project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    clean_doc_ids = [
        str(doc_id or "").strip()
        for doc_id in payload.doc_ids
        if str(doc_id or "").strip()
    ]

    if not clean_doc_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one Doc ID is required.",
        )

    zip_buffer = io.BytesIO()
    exported_rows = []

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for doc_id in clean_doc_ids:
            native_blob = ""
            text_blob = ""
            native_exported = False
            text_exported = False
            status_parts = []

            if payload.include_native:
                native_blob = find_blob_for_doc_id(
                    workspace=payload.workspace,
                    client=payload.client,
                    project=payload.project,
                    doc_id=doc_id,
                    folder="source/native",
                )

                if native_blob:
                    native_bytes = read_blob_bytes(
                        workspace=payload.workspace,
                        blob_name=native_blob,
                    )

                    native_filename = native_blob.split("/")[-1]

                    zip_file.writestr(
                        f"native/{native_filename}",
                        native_bytes,
                    )

                    native_exported = True
                    status_parts.append("native exported")
                else:
                    status_parts.append("native missing")

            if payload.include_text:
                text_blob = find_blob_for_doc_id(
                    workspace=payload.workspace,
                    client=payload.client,
                    project=payload.project,
                    doc_id=doc_id,
                    folder="source/text",
                )

                if text_blob:
                    text_bytes = read_blob_bytes(
                        workspace=payload.workspace,
                        blob_name=text_blob,
                    )

                    text_filename = text_blob.split("/")[-1]

                    zip_file.writestr(
                        f"text/{text_filename}",
                        text_bytes,
                    )

                    text_exported = True
                    status_parts.append("text exported")
                else:
                    status_parts.append("text missing")

            exported_rows.append(
                {
                    "doc_id": doc_id,
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "native_exported": native_exported,
                    "text_exported": text_exported,
                    "status": "; ".join(status_parts),
                }
            )

        zip_file.writestr(
            "final_source_docs_export.csv",
            build_source_docs_csv(
                payload=payload,
                exported_rows=exported_rows,
            ),
        )

    zip_buffer.seek(0)

    safe_export_id = safe_export_name(
        payload.entity_uid,
        fallback="final_entity",
    )

    filename = f"{safe_export_id}_source_docs.zip"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers=headers,
    )
    
@router.post("/export-source-docs-zip")
def export_source_docs_zip(
    payload: FilteredSourceDocsZipRequest,
):
    if not payload.project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    clean_doc_ids = [
        str(doc_id or "").strip()
        for doc_id in payload.doc_ids
        if str(doc_id or "").strip()
    ]

    # Preserve order while deduping.
    clean_doc_ids = list(dict.fromkeys(clean_doc_ids))

    if not clean_doc_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one Doc ID is required.",
        )

    zip_buffer = io.BytesIO()
    exported_rows = []
    used_zip_names = set()

    def add_blob_to_zip(
        zip_file: zipfile.ZipFile,
        blob_name: str,
        folder_name: str,
    ):
        blob_bytes = read_blob_bytes(
            workspace=payload.workspace,
            blob_name=blob_name,
        )

        filename = blob_name.split("/")[-1]
        zip_name = f"{folder_name}/{filename}"

        if zip_name in used_zip_names:
            stem, extension = os.path.splitext(filename)
            counter = 2

            while zip_name in used_zip_names:
                zip_name = f"{folder_name}/{stem}_{counter}{extension}"
                counter += 1

        used_zip_names.add(zip_name)
        zip_file.writestr(zip_name, blob_bytes)

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for doc_id in clean_doc_ids:
            native_blob = ""
            text_blob = ""
            native_exported = False
            text_exported = False
            status_parts = []

            if payload.include_native:
                native_blob = find_blob_for_doc_id(
                    workspace=payload.workspace,
                    client=payload.client,
                    project=payload.project,
                    doc_id=doc_id,
                    folder="source/native",
                )

                if native_blob:
                    add_blob_to_zip(
                        zip_file=zip_file,
                        blob_name=native_blob,
                        folder_name="native",
                    )

                    native_exported = True
                    status_parts.append("native exported")
                else:
                    status_parts.append("native missing")

            if payload.include_text:
                text_blob = find_blob_for_doc_id(
                    workspace=payload.workspace,
                    client=payload.client,
                    project=payload.project,
                    doc_id=doc_id,
                    folder="source/text",
                )

                if text_blob:
                    add_blob_to_zip(
                        zip_file=zip_file,
                        blob_name=text_blob,
                        folder_name="text",
                    )

                    text_exported = True
                    status_parts.append("text exported")
                else:
                    status_parts.append("text missing")

            exported_rows.append(
                {
                    "doc_id": doc_id,
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "native_exported": native_exported,
                    "text_exported": text_exported,
                    "status": "; ".join(status_parts),
                }
            )

        zip_file.writestr(
            "filtered_source_docs_export.csv",
            build_filtered_source_docs_csv(
                payload=payload,
                exported_rows=exported_rows,
            ),
        )

    zip_buffer.seek(0)

    safe_label = safe_export_name(
        payload.zip_label,
        fallback="Filtered_Source_Documents",
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_label}_{timestamp}.zip"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers=headers,
    )

def save_document_review_state(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
    state: dict,
):
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
        workspace,
        client,
        project,
        doc_id,
    )

    blob_client = container.get_blob_client(blob_name)

    blob_client.upload_blob(
        json.dumps(state, indent=2),
        overwrite=True,
    )
    
def save_deleted_entity_record(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
    entity: dict,
):
    container = get_container_client(workspace)
    base_path = project_base_path(
        workspace=workspace,
        client=client,
        project=project,
    )

    ucid = (
        entity.get("ucid")
        or entity.get("UCID")
        or "no_ucid"
    )

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    clean_doc_id = (
        str(doc_id or "")
        .strip()
        .split("/")[-1]
        .rsplit(".", 1)[0]
    )

    blob_name = (
        f"{base_path}/Deleted Data/linked_entities/"
        f"{clean_doc_id}_{ucid}_{timestamp}.json"
    )

    container.upload_blob(
        name=blob_name,
        data=json.dumps(entity, indent=2),
        overwrite=True,
    )

    return blob_name

@router.post("/update")
def update_entity(
    payload: EntityUpdateRequest,
    x_username: str = Header(default=""),
):
    state = load_document_review_state(
        workspace=payload.workspace,
        client=payload.client,
        project=payload.project,
        doc_id=payload.doc_id,
    )

    for index, entity in enumerate(state.get("linked_entities", [])):
        entity_ucid = (
            entity.get("ucid")
            or entity.get("UCID")
            or ""
        )

        if entity_ucid != payload.ucid:
            continue

        entity["values"] = payload.values
        entity["linked"] = True
        entity["updated_by"] = x_username
        entity["updated_at"] = datetime.now(timezone.utc).isoformat()

        state["linked_entities"][index] = entity

        save_document_review_state(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            state=state,
        )

        return {
            "status": "updated",
            "entity": entity_from_review_state(
                state,
                entity,
                index,
            ),
        }

    return {"status": "not_found"}


@router.post("/unlink")
def unlink_entity(
    payload: EntityUnlinkRequest,
    x_username: str = Header(default=""),
):
    state = load_document_review_state(
        workspace=payload.workspace,
        client=payload.client,
        project=payload.project,
        doc_id=payload.doc_id,
    )

    for index, entity in enumerate(state.get("linked_entities", [])):
        entity_ucid = (
            entity.get("ucid")
            or entity.get("UCID")
            or ""
        )

        if entity_ucid != payload.ucid:
            continue

        entity["linked"] = False
        entity["unlinked_by"] = x_username
        entity["unlinked_at"] = datetime.now(timezone.utc).isoformat()

        state["linked_entities"][index] = entity

        save_document_review_state(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            state=state,
        )

        return {
            "status": "unlinked",
            "entity": entity_from_review_state(
                state,
                entity,
                index,
            ),
        }

    return {"status": "not_found"}


@router.post("/delete")
def delete_entity(
    payload: EntityDeleteRequest,
    x_username: str = Header(default=""),
):
    state = load_document_review_state(
        workspace=payload.workspace,
        client=payload.client,
        project=payload.project,
        doc_id=payload.doc_id,
    )

    linked_entities = state.get("linked_entities", [])

    for index, entity in enumerate(linked_entities):
        entity_ucid = (
            entity.get("ucid")
            or entity.get("UCID")
            or ""
        )

        entity_id = str(entity.get("id", ""))
        payload_entity_id = str(payload.entity_id or "")

        if payload.ucid:
            if entity_ucid != payload.ucid:
                continue
        elif payload_entity_id:
            if entity_id != payload_entity_id:
                continue
        else:
            continue

        removed = linked_entities.pop(index)

        deleted_record = {
            **removed,
            "deleted_by": x_username,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "workspace": payload.workspace,
            "client": payload.client,
            "project": payload.project,
            "doc_id": payload.doc_id,
        }

        deleted_blob = save_deleted_entity_record(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            entity=deleted_record,
        )

        state["linked_entities"] = linked_entities
        state.setdefault("deleted_entities", []).append(
            {
                **deleted_record,
                "deleted_blob": deleted_blob,
            }
        )

        save_document_review_state(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            state=state,
        )

        return {
            "status": "deleted",
            "entity": removed,
            "deleted_blob": deleted_blob,
        }

    if payload.ucid or payload.entity_id:
        deleted_record = {
            "id": payload.entity_id,
            "ucid": payload.ucid,
            "UCID": payload.ucid,
            "linked": False,
            "source": "delete_marker",
            "deleted_by": x_username,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "workspace": payload.workspace,
            "client": payload.client,
            "project": payload.project,
            "doc_id": payload.doc_id,
        }

        deleted_blob = save_deleted_entity_record(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            entity=deleted_record,
        )

        state.setdefault("deleted_entities", []).append(
            {
                **deleted_record,
                "deleted_blob": deleted_blob,
            }
        )

        save_document_review_state(
            workspace=payload.workspace,
            client=payload.client,
            project=payload.project,
            doc_id=payload.doc_id,
            state=state,
        )

        return {
            "status": "deleted_marker_created",
            "entity": deleted_record,
            "deleted_blob": deleted_blob,
        }

    return {"status": "not_found"}