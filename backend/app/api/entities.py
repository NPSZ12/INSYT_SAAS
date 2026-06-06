from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services.project_store import CAPTURED_ENTITIES
from app.services.protocol_service import load_protocol_fields

import json
from typing import Any

from app.services.batch_service import get_container_client


def clean_path(value: str | None) -> str:
    return str(value or "").strip().strip("/")


def project_base_path(client: str | None, project: str) -> str:
    client_name = clean_path(client)
    project_name = clean_path(project)

    if client_name:
        return f"{client_name}/{project_name}"

    return project_name


def normalize_doc_lookup(value: str) -> str:
    clean = str(value or "").strip()
    clean = clean.split("/")[-1]
    clean = clean.rsplit(".", 1)[0]
    return clean.replace("_", " ").lower()


def load_latest_overlay_records(
    workspace: str,
    client: str | None,
    project: str,
    overlay_view: str = "raw",
) -> list[dict[str, Any]]:
    container = get_container_client(workspace)
    base_path = project_base_path(client, project)
    latest_path = f"{base_path}/overlays/{overlay_view}/latest_overlay.json"

    blob_client = container.get_blob_client(latest_path)

    if not blob_client.exists():
        return []

    payload = json.loads(
        blob_client.download_blob().readall().decode("utf-8")
    )

    return payload.get("records", [])


router = APIRouter(prefix="/api/entities", tags=["Captured Entities"])


class EntityUpdateRequest(BaseModel):
    entity_id: int
    values: dict


class EntityUnlinkRequest(BaseModel):
    entity_id: int


class EntityDeleteRequest(BaseModel):
    entity_id: int


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
        if header
    ]

    normalized_view = "final" if view == "final" else "raw"

    matching_entities = [
        entity for entity in CAPTURED_ENTITIES
        if entity.get("project_id") == project
        and entity.get("linked", True)
        and (not batch or entity.get("batch_id") == batch)
        and entity.get("entity_view", "raw") == normalized_view
    ]

    rows = []

    for entity in matching_entities:
        row = {
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
        "headers": ["Doc ID"] + headers,
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

    manual_entities = [
        entity for entity in CAPTURED_ENTITIES
        if entity.get("project_id") == project
        and normalize_doc_lookup(entity.get("doc_id", "")) == normalized_doc
        and entity.get("linked", True)
        and (not batch or entity.get("batch_id") == batch)
    ]

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

        overlay_entities.append(
            {
                "id": f"overlay-{index}",
                "project_id": project,
                "batch_id": batch or "Overlay",
                "doc_id": record_doc_id,
                "captured_by": "Overlay Upload",
                "linked": True,
                "source": "overlay",
                "xl_mapped": True,
                "values": record.get("metadata", {}),
            }
        )

    return manual_entities + overlay_entities


@router.post("/update")
def update_entity(
    payload: EntityUpdateRequest,
    x_username: str = Header(default=""),
):
    for entity in CAPTURED_ENTITIES:
        if entity.get("id") == payload.entity_id:
            entity["values"] = payload.values

            return {
                "status": "updated",
                "entity": entity,
            }

    return {"status": "not_found"}


@router.post("/unlink")
def unlink_entity(
    payload: EntityUnlinkRequest,
    x_username: str = Header(default=""),
):
    for entity in CAPTURED_ENTITIES:
        if entity.get("id") == payload.entity_id:
            entity["linked"] = False

            return {
                "status": "unlinked",
                "entity": entity,
            }

    return {"status": "not_found"}


@router.post("/delete")
def delete_entity(
    payload: EntityDeleteRequest,
    x_username: str = Header(default=""),
):
    for index, entity in enumerate(CAPTURED_ENTITIES):
        if entity.get("id") == payload.entity_id:
            removed = CAPTURED_ENTITIES.pop(index)

            return {
                "status": "deleted",
                "entity": removed,
            }

    return {"status": "not_found"}