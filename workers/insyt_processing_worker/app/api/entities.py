from fastapi import APIRouter, Header
from pydantic import BaseModel
from datetime import datetime, timezone

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

def get_document_review_blob_name(
    client: str | None,
    project: str,
    doc_id: str,
) -> str:
    base_path = project_base_path(client, project)
    clean_doc_id = str(doc_id or "").strip().split("/")[-1]

    if "." in clean_doc_id:
        clean_doc_id = clean_doc_id.rsplit(".", 1)[0]

    return f"{base_path}/Review/documents/{clean_doc_id}.json"


def load_document_review_state(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
) -> dict:
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
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
    base_path = project_base_path(client, project)
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

    normalized_view = "final" if view == "final" else "raw"
    
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

        overlay_entities.append(overlay_entity)

    return manual_entities + overlay_entities

def save_document_review_state(
    workspace: str,
    client: str | None,
    project: str,
    doc_id: str,
    state: dict,
):
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
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
    base_path = project_base_path(client, project)

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