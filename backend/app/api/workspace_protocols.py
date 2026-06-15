import io
import json

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timezone

from app.services.batch_service import get_container_client
from app.services.storage_paths import build_project_path


class SaveProtocolRequest(BaseModel):
    protocol_template: str
    fields: list[dict]
    override: bool = False
    client: str | None = None


router = APIRouter(
    prefix="/api",
    tags=["workspace-protocols"],
)


@router.get("/{workspace}/projects/{project_id}/protocol")
def get_workspace_protocol(
    workspace: str,
    project_id: str,
    client: str = Query(...),
):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    try:
        container = get_container_client(workspace)

        possible_protocol_files = [
            build_project_path(
                workspace,
                client,
                project_id,
                "source/protocol",
                f"{project_id}_Protocol.json",
            ),
            build_project_path(
                workspace,
                client,
                project_id,
                "source/protocol",
                f"{project_id}_Protocol.xlsx",
            ),
            build_project_path(
                workspace,
                client,
                project_id,
                "protocol.json",
            ),
            build_project_path(
                workspace,
                client,
                project_id,
                "protocol.xlsx",
            ),
        ]

        for blob_name in possible_protocol_files:
            blob_client = container.get_blob_client(blob_name)

            if not blob_client.exists():
                continue

            props = blob_client.get_blob_properties()
            blob_data = blob_client.download_blob().readall()

            if blob_name.lower().endswith(".json"):
                protocol_payload = json.loads(blob_data.decode("utf-8"))

                fields = protocol_payload.get("fields", [])

                return {
                    "workspace": workspace,
                    "client": client,
                    "project_id": project_id,
                    "has_protocol": True,
                    "protocol_blob": blob_name,
                    "protocol_blob_path": blob_name,
                    "protocol_filename": blob_name.split("/")[-1],
                    "download_url": blob_client.url,
                    "last_modified": props.last_modified.isoformat()
                    if props.last_modified
                    else None,
                    "size": props.size,
                    "protocol": {
                        "protocol_template": protocol_payload.get(
                            "protocol_template",
                            blob_name.split("/")[-1],
                        ),
                        "fields": fields,
                    },
                    "fields": fields,
                }

            if blob_name.lower().endswith(".xlsx"):
                workbook = pd.ExcelFile(io.BytesIO(blob_data))

                fields = []

                for sheet_name in workbook.sheet_names:
                    df = pd.read_excel(
                        io.BytesIO(blob_data),
                        sheet_name=sheet_name,
                        dtype=str,
                    ).fillna("")

                    df.columns = [str(col).strip() for col in df.columns]

                    def get_column(row, names):
                        for name in names:
                            value = row.get(name, "")
                            if value:
                                return str(value).strip()
                        return ""

                    for _, row in df.iterrows():
                        section = get_column(row, ["Section", "section"])

                        data_element = get_column(
                            row,
                            [
                                "Data Element",
                                "DataElement",
                                "Data element",
                                "data_element",
                            ],
                        )

                        default_format = get_column(
                            row,
                            [
                                "Format",
                                "Default Format",
                                "Capture Type",
                                "Type",
                            ],
                        )

                        notes = get_column(
                            row,
                            [
                                "Notes",
                                "Note",
                                "Description",
                            ],
                        )

                        if not data_element:
                            continue

                        fields.append(
                            {
                                "section": section,
                                "data_element": data_element,
                                "format": default_format,
                                "default_format": default_format,
                                "notes": notes,
                                "source_sheet": sheet_name,
                            }
                        )

                return {
                    "workspace": workspace,
                    "client": client,
                    "project_id": project_id,
                    "has_protocol": True,
                    "protocol_blob": blob_name,
                    "protocol_blob_path": blob_name,
                    "protocol_filename": blob_name.split("/")[-1],
                    "download_url": blob_client.url,
                    "last_modified": props.last_modified.isoformat()
                    if props.last_modified
                    else None,
                    "size": props.size,
                    "protocol": {
                        "protocol_template": blob_name.split("/")[-1],
                        "fields": fields,
                    },
                    "fields": fields,
                }

        return {
            "workspace": workspace,
            "client": client,
            "project_id": project_id,
            "has_protocol": False,
            "protocol_blob": None,
            "protocol_blob_path": None,
            "protocol_filename": None,
            "download_url": None,
            "protocol": {
                "protocol_template": None,
                "fields": [],
            },
            "fields": [],
            "message": "No protocol found.",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load protocol: {type(e).__name__}: {e}",
        )


@router.post("/{workspace}/projects/{project_id}/protocol")
def save_workspace_protocol(
    workspace: str,
    project_id: str,
    payload: SaveProtocolRequest,
    client: str | None = Query(default=None),
):
    client = client or payload.client

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    container = get_container_client(workspace)

    protocol_blob = build_project_path(
        workspace,
        client,
        project_id,
        "source/protocol",
        f"{project_id}_Protocol.json",
    )
    blob_client = container.get_blob_client(protocol_blob)

    if blob_client.exists() and not payload.override:
        raise HTTPException(
            status_code=409,
            detail="Protocol already selected. Do you want to override?",
        )

    protocol_payload = {
        "project_id": project_id,
        "workspace": workspace,
        "client": client,
        "protocol_template": payload.protocol_template,
        "fields": payload.fields,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    container.upload_blob(
        name=protocol_blob,
        data=json.dumps(protocol_payload, indent=2),
        overwrite=True,
    )

    return {
        "message": "Protocol saved.",
        "workspace": workspace,
        "client": client,
        "project_id": project_id,
        "has_protocol": True,
        "protocol_blob": protocol_blob,
        "protocol_blob_path": protocol_blob,
        "protocol_filename": protocol_blob.split("/")[-1],
        "protocol": protocol_payload,
        "fields": payload.fields,
    }