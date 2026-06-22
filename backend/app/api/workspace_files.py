import os

from fastapi import APIRouter, HTTPException, Query

from io import BytesIO

import pandas as pd

from azure.storage.blob import BlobServiceClient

from app.services.storage_paths import build_project_prefix

try:
    from docx import Document
except Exception:
    Document = None

router = APIRouter(
    prefix="/api",
    tags=["workspace-files"],
)

VALID_WORKSPACES = {"capture", "summaries", "discovery"}


def clean_folder(value: str) -> str:
    return value.strip().strip("/")


def get_container_name(workspace: str) -> str:
    workspace_clean = workspace.lower().strip()

    if workspace_clean == "capture":
        return os.getenv("AZURE_CAPTURE_CONTAINER", "insyt-capture")

    if workspace_clean == "discovery":
        return os.getenv("AZURE_DISCOVERY_CONTAINER", "insyt-discovery")

    if workspace_clean == "summaries":
        return os.getenv("AZURE_SUMMARIES_CONTAINER", "insyt-summaries")

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported workspace: {workspace}",
    )


def get_workspace_container(workspace: str):
    workspace = workspace.lower().strip()

    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    conn = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    if not conn:
        raise HTTPException(
            status_code=500,
            detail=(
                "Live source storage is not configured. Set "
                "INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING, "
                "CDS_STORAGE_CONNECTION_STRING, or "
                "AZURE_STORAGE_CONNECTION_STRING."
            ),
        )

    service = BlobServiceClient.from_connection_string(conn)
    return service.get_container_client(get_container_name(workspace))


def build_prefix(
    workspace: str,
    project: str,
    client: str | None = None,
    folder: str | None = None,
) -> str:
    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required for workspace file paths.",
        )

    return build_project_prefix(
        workspace,
        client,
        project,
        folder or "",
    )

def find_matching_blob_by_doc_id(
    blob_paths: list[str],
    doc_id: str,
) -> str | None:
    doc_id_clean = str(doc_id or "").lower().strip()

    if not doc_id_clean:
        return None

    for blob_path in blob_paths:
        file_name = blob_path.split("/")[-1]
        stem = file_name.rsplit(".", 1)[0].lower()

        if stem == doc_id_clean:
            return blob_path

    for blob_path in blob_paths:
        file_name = blob_path.split("/")[-1].lower()

        if doc_id_clean in file_name:
            return blob_path

    return None

@router.get("/{workspace}/files")
def list_workspace_files(
    workspace: str,
    project: str = Query(...),
    client: str | None = Query(default=None),
    folder: str | None = Query(default=None),
):
    workspace = workspace.lower().strip()

    container = get_workspace_container(workspace)

    project_name = clean_folder(project)
    client_name = clean_folder(client) if client else ""
    resolved_folder = folder or "source/native"

    prefix = build_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder=resolved_folder,
    )
    print(
        "WORKSPACE FILES:",
        workspace,
        project,
        client,
        resolved_folder,
        prefix,
    )

    files = []

    text_blobs: list[str] = []
    outline_blobs: list[str] = []

    if workspace == "summaries":
        text_prefix = build_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/text",
        )

        outline_prefix = build_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="review/summary-outlines",
        )

        text_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=text_prefix)
            if not blob.name.endswith("/")
        ]

        outline_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=outline_prefix)
            if not blob.name.endswith("/")
        ]

    for blob in container.list_blobs(name_starts_with=prefix):
        blob_path = blob.name
        file_name = blob_path.split("/")[-1]

        if not file_name:
            continue

        # Skip virtual folders
        if "." not in file_name:
            continue

        # Skip system files
        if file_name.startswith("."):
            continue

        # Skip metadata files
        if file_name.lower().endswith(".json"):
            continue

        if not file_name:
            continue

        extension = (
            file_name.rsplit(".", 1)[-1].lower()
            if "." in file_name
            else ""
        )

        doc_id = (
            file_name.rsplit(".", 1)[0]
            if "." in file_name
            else file_name
        )

        text_blob = None
        outline_blob = None

        if workspace == "summaries":
            text_blob = find_matching_blob_by_doc_id(text_blobs, doc_id)
            outline_blob = find_matching_blob_by_doc_id(outline_blobs, doc_id)

        files.append(
            {
                "doc_id": doc_id,

                # Existing INSYT fields
                "file_name": file_name,
                "blob_path": blob_path,

                # Summaries review-ready file links
                "native_blob": blob_path,
                "text_blob": text_blob,
                "outline_blob": outline_blob,

                # Frontend compatibility aliases
                "name": file_name,
                "filename": file_name,
                "path": blob_path,

                "extension": extension,
                "size": str(blob.size or ""),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if blob.last_modified
                    else ""
                ),
                "workspace": workspace,
                "client": client_name,
                "project": project_name,
                "folder": clean_folder(resolved_folder),
                "status": (
                    "outlined"
                    if workspace == "summaries" and outline_blob
                    else "ready"
                ),
            }
        )

    return files

def get_file_extension(blob_path: str) -> str:
    file_name = blob_path.split("/")[-1]

    if "." not in file_name:
        return ""

    return file_name.rsplit(".", 1)[-1].lower()


def dataframe_preview(df: pd.DataFrame, limit: int):
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    df = df.fillna("")

    df.columns = [str(column) for column in df.columns]

    preview_df = df.head(limit)

    return {
        "columns": preview_df.columns.tolist(),
        "rows": preview_df.astype(str).to_dict(orient="records"),
        "row_count_previewed": len(preview_df),
        "total_columns": len(preview_df.columns),
    }


def read_text_preview(file_bytes: bytes, limit: int):
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="replace")

    lines = text.splitlines()
    preview_lines = lines[:limit]

    return {
        "text": "\n".join(preview_lines),
        "line_count_previewed": len(preview_lines),
        "total_lines_detected": len(lines),
    }


def read_docx_preview(file_bytes: bytes):
    if Document is None:
        raise HTTPException(
            status_code=500,
            detail="DOCX preview requires python-docx to be installed.",
        )

    document = Document(BytesIO(file_bytes))

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return {
        "text": "\n\n".join(paragraphs),
        "paragraph_count": len(paragraphs),
    }


@router.get("/{workspace}/native-preview")
def preview_workspace_native_file(
    workspace: str,
    blob_path: str = Query(...),
    sheet_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    workspace = workspace.lower().strip()

    container = get_workspace_container(workspace)

    extension = get_file_extension(blob_path)
    file_name = blob_path.split("/")[-1]

    if not extension:
        raise HTTPException(
            status_code=400,
            detail="File extension could not be detected.",
        )

    try:
        file_bytes = container.download_blob(blob_path).readall()
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to load native file: {exc}",
        )

    if extension == "pdf":
        return {
            "file_name": file_name,
            "extension": extension,
            "preview_type": "pdf",
            "message": "PDF preview should use the existing PDF viewer.",
        }

    if extension in {"csv", "tsv"}:
        delimiter = "\t" if extension == "tsv" else ","

        df = pd.read_csv(
            BytesIO(file_bytes),
            sep=delimiter,
            dtype=str,
            nrows=limit,
        )

        preview = dataframe_preview(df, limit)

        return {
            "file_name": file_name,
            "extension": extension,
            "preview_type": "table",
            "sheets": [],
            "active_sheet": "",
            **preview,
        }

    if extension in {"xlsx", "xls", "xlsm"}:
        excel_file = pd.ExcelFile(BytesIO(file_bytes))
        sheets = excel_file.sheet_names

        active_sheet = sheet_name or sheets[0]

        if active_sheet not in sheets:
            raise HTTPException(
                status_code=400,
                detail="Requested sheet was not found in workbook.",
            )

        df = pd.read_excel(
            excel_file,
            sheet_name=active_sheet,
            dtype=str,
            nrows=limit,
        )

        preview = dataframe_preview(df, limit)

        return {
            "file_name": file_name,
            "extension": extension,
            "preview_type": "table",
            "sheets": sheets,
            "active_sheet": active_sheet,
            **preview,
        }

    if extension == "docx":
        preview = read_docx_preview(file_bytes)

        return {
            "file_name": file_name,
            "extension": extension,
            "preview_type": "text",
            **preview,
        }

    if extension in {"txt", "log", "json", "xml", "html", "htm"}:
        preview = read_text_preview(file_bytes, limit)

        return {
            "file_name": file_name,
            "extension": extension,
            "preview_type": "text",
            **preview,
        }

    return {
        "file_name": file_name,
        "extension": extension,
        "preview_type": "unsupported",
        "message": "This file type cannot yet be rendered directly in-browser.",
    }