import io
import os

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


@router.get("/{workspace}/protocol-templates")
def get_protocol_templates(workspace: str):
    if workspace not in ["capture", "summaries", "discovery"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    try:
        container = get_capture_container_client()
        template_paths = TEMPLATE_BLOB_PATHS.get(workspace, [])

        blob_client = None
        template_blob_path = None

        for path in template_paths:
            candidate = container.get_blob_client(path)

            if candidate.exists():
                blob_client = candidate
                template_blob_path = path
                break

        if not blob_client or not template_blob_path:
            raise HTTPException(
                status_code=404,
                detail=f"No protocol template file found for workspace: {workspace}",
            )

        blob_data = blob_client.download_blob().readall()
        workbook = pd.ExcelFile(io.BytesIO(blob_data))

        templates = {}

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

            fields = []

            for _, row in df.iterrows():
                section = get_column(row, ["Section", "section"])
                data_element = get_column(row, ["Data Element", "DataElement", "Data element", "data_element"])
                default_format = get_column(row, ["Format", "Default Format", "Capture Type", "Type"])
                notes = get_column(row, ["Notes", "Note", "Description"])

                if not data_element:
                    continue

                fields.append({
                    "section": section,
                    "data_element": data_element,
                    "default_format": default_format,
                    "notes": notes,
                })

            templates[sheet_name] = fields

        return {
            "workspace": workspace,
            "template_blob_path": template_blob_path,
            "templates": templates,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Protocol template load failed: {str(e)}",
        )
        
