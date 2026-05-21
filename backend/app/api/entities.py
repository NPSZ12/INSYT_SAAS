from fastapi import APIRouter, Header
from app.services.project_store import CAPTURED_ENTITIES
from app.services.protocol_service import load_protocol_fields
from pydantic import BaseModel

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
    x_username: str = Header(default=""),
):
    protocol_fields = load_protocol_fields(project)

    headers = [
        field["label"]
        for field in protocol_fields
    ]

    matching_entities = [
        entity for entity in CAPTURED_ENTITIES
        if entity.get("project_id") == project
        and entity.get("linked", True)
        and (not batch or entity.get("batch_id") == batch)
        and (not x_username or entity.get("captured_by") == x_username)
    ]

    rows = []

    for entity in matching_entities:
        row = {
            "doc_id": entity.get("doc_id", ""),
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
    batch: str,
    doc: str,
    x_username: str = Header(default=""),
):
    return [
        entity for entity in CAPTURED_ENTITIES
        if entity.get("project_id") == project
        and entity.get("batch_id") == batch
        and entity.get("doc_id") == doc
        and entity.get("captured_by") == x_username
    ]
    
@router.post("/update")
def update_entity(payload: EntityUpdateRequest, x_username: str = Header(default="")):
    for entity in CAPTURED_ENTITIES:
        if entity.get("id") == payload.entity_id and entity.get("captured_by") == x_username:
            entity["values"] = payload.values
            return {
                "status": "updated",
                "entity": entity,
            }

    return {"status": "not_found"}


@router.post("/unlink")
def unlink_entity(payload: EntityUnlinkRequest, x_username: str = Header(default="")):
    for entity in CAPTURED_ENTITIES:
        if entity.get("id") == payload.entity_id and entity.get("captured_by") == x_username:
            entity["linked"] = False
            return {
                "status": "unlinked",
                "entity": entity,
            }

    return {"status": "not_found"}


@router.post("/delete")
def delete_entity(payload: EntityDeleteRequest, x_username: str = Header(default="")):
    for index, entity in enumerate(CAPTURED_ENTITIES):
        if entity.get("id") == payload.entity_id and entity.get("captured_by") == x_username:
            removed = CAPTURED_ENTITIES.pop(index)
            return {
                "status": "deleted",
                "entity": removed,
            }

    return {"status": "not_found"}