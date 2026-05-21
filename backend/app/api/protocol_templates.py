import io
import os

import pandas as pd
from azure.storage.blob import BlobServiceClient
from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api",
    tags=["protocol-templates"],
)

TEMPLATE_BLOB_PATH = "Protocol_Templates.xlsx"


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
        blob_client = container.get_blob_client(TEMPLATE_BLOB_PATH)

        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Template file not found: {TEMPLATE_BLOB_PATH}",
            )

        blob_data = blob_client.download_blob().readall()
        workbook = pd.ExcelFile(io.BytesIO(blob_data))

        templates = {}

        for sheet_name in workbook.sheet_names:
            df = pd.read_excel(
                io.BytesIO(blob_data),
                sheet_name=sheet_name,
            )

            df = df.fillna("")

            fields = []

            for _, row in df.iterrows():
                data_element = clean_cell(row.get("Data Element", ""))

                if not data_element:
                    continue

                fields.append(
                    {
                        "section": clean_cell(row.get("Section", "")),
                        "data_element": data_element,
                        "default_format": clean_cell(row.get("Format", "")),
                        "notes": clean_cell(row.get("Notes", "")),
                    }
                )

            templates[sheet_name] = fields

        return {
            "templates": templates,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Protocol template load failed: {str(e)}",
        )