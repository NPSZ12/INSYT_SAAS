import io
import os
from urllib.parse import unquote

import pandas as pd
from azure.storage.blob import BlobServiceClient
from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api",
    tags=["protocol-templates"],
)

TEMPLATE_BLOB_PATHS = {
    "capture": [
        "System/ProtocolTemplates/Capture_Templates.xlsx",
        "System/ProtocolTemplates/Protocol_Templates.xlsx",
        "Protocol_Templates.xlsx",
    ],
    "summaries": [
        "System/ProtocolTemplates/Summaries_Templates.xlsx",
        "System/ProtocolTemplates/Protocol_Templates.xlsx",
        "Protocol_Templates.xlsx",
    ],
    "discovery": [
        "System/ProtocolTemplates/Discovery_Templates.xlsx",
        "System/ProtocolTemplates/Protocol_Templates.xlsx",
        "Protocol_Templates.xlsx",
        "system/ProtocolTemplates/Discovery_Templates.xlsx",
    ],
}


def get_capture_container_client():
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_CAPTURE_CONTAINER", "insyt-capture")

    if not connection_string:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    service_client = BlobServiceClient.from_connection_string(connection_string)

    return service_client.get_container_client(container_name)


def clean_cell(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def validate_workspace(workspace: str):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )


def get_column(row, names):
    for name in names:
        value = row.get(name, "")

        if value:
            return str(value).strip()

    return ""


def load_protocol_template_workbook(workspace: str):
    validate_workspace(workspace)

    container = get_capture_container_client()
    template_paths = TEMPLATE_BLOB_PATHS.get(workspace, [])

    for path in template_paths:
        blob_client = container.get_blob_client(path)

        if not blob_client.exists():
            continue

        blob_data = blob_client.download_blob().readall()
        workbook = pd.ExcelFile(io.BytesIO(blob_data))

        return {
            "container": container.container_name,
            "template_blob_path": path,
            "blob_data": blob_data,
            "workbook": workbook,
        }

    raise HTTPException(
        status_code=404,
        detail=f"No protocol template file found for workspace: {workspace}",
    )


def parse_protocol_templates(workspace: str):
    loaded = load_protocol_template_workbook(workspace)
    blob_data = loaded["blob_data"]
    workbook = loaded["workbook"]

    templates_by_name = {}
    protocols = []

    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(
            io.BytesIO(blob_data),
            sheet_name=sheet_name,
            dtype=str,
        ).fillna("")

        df.columns = [str(col).strip() for col in df.columns]

        fields = []

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
                }
            )

        templates_by_name[sheet_name] = fields

        protocols.append(
            {
                "name": sheet_name,
                "protocol_name": sheet_name,
                "protocol_template": sheet_name,
                "fields": fields,
                "field_count": len(fields),
            }
        )

    return {
        "workspace": workspace,
        "template_blob_path": loaded["template_blob_path"],
        "templates": templates_by_name,
        "protocols": protocols,
        "protocol_names": [item["name"] for item in protocols],
    }


@router.get("/{workspace}/protocol-templates")
def get_protocol_templates(workspace: str):
    try:
        return parse_protocol_templates(workspace)

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Protocol template load failed: {str(e)}",
        )


@router.get("/{workspace}/protocol-templates/{protocol_name}")
def get_protocol_template(
    workspace: str,
    protocol_name: str,
):
    try:
        decoded_protocol_name = unquote(protocol_name)

        payload = parse_protocol_templates(workspace)
        templates = payload.get("templates", {})

        fields = templates.get(decoded_protocol_name)

        if fields is None:
            normalized_target = decoded_protocol_name.lower().replace("_", " ")

            for name, candidate_fields in templates.items():
                normalized_name = str(name).lower().replace("_", " ")

                if normalized_name == normalized_target:
                    fields = candidate_fields
                    decoded_protocol_name = name
                    break

        if fields is None:
            raise HTTPException(
                status_code=404,
                detail=f"Protocol template not found: {protocol_name}",
            )

        return {
            "workspace": workspace,
            "protocol_name": decoded_protocol_name,
            "protocol_template": decoded_protocol_name,
            "fields": fields,
            "field_count": len(fields),
            "template_blob_path": payload.get("template_blob_path"),
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Protocol template load failed: {str(e)}",
        )


@router.get("/{workspace}/protocol-templates/{protocol_name}/fields")
def get_protocol_template_fields(
    workspace: str,
    protocol_name: str,
):
    template = get_protocol_template(
        workspace=workspace,
        protocol_name=protocol_name,
    )

    return {
        "workspace": workspace,
        "protocol_name": template["protocol_name"],
        "fields": template["fields"],
        "field_count": template["field_count"],
    }