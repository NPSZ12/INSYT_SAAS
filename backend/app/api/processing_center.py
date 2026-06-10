import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from azure.storage.blob import BlobServiceClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel


router = APIRouter(
    prefix="/api/{workspace}/processing-center",
    tags=["Processing Center"],
)


class StartProcessingPayload(BaseModel):
    client: str
    project_id: str


class ProcessingFilePayload(BaseModel):
    client: str
    project_id: str
    file_name: str


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


def get_blob_service_client() -> BlobServiceClient:
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not conn:
        raise HTTPException(
            status_code=500,
            detail="AZURE_STORAGE_CONNECTION_STRING is not configured",
        )

    return BlobServiceClient.from_connection_string(conn)


def clean_path_part(value: str) -> str:
    return str(value or "").strip().strip("/")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def processing_base_path(client: str, project_id: str) -> str:
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    return f"{client}/{project_id}/source/processing_center"


def upload_path(client: str, project_id: str, file_name: str) -> str:
    return f"{processing_base_path(client, project_id)}/uploads/{file_name}"


def in_progress_path(client: str, project_id: str, file_name: str) -> str:
    return f"{processing_base_path(client, project_id)}/in_progress/{file_name}"


def processed_native_path(client: str, project_id: str, file_name: str) -> str:
    return f"{processing_base_path(client, project_id)}/processed/native/{file_name}"


def processed_text_path(client: str, project_id: str, doc_id: str) -> str:
    return f"{processing_base_path(client, project_id)}/processed/text/{doc_id}.txt"


def processed_metadata_path(client: str, project_id: str, doc_id: str) -> str:
    return f"{processing_base_path(client, project_id)}/processed/metadata/{doc_id}.json"


def final_native_path(client: str, project_id: str, file_name: str) -> str:
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    return f"{client}/{project_id}/source/native/{file_name}"


def final_text_path(client: str, project_id: str, doc_id: str) -> str:
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    return f"{client}/{project_id}/source/text/{doc_id}.txt"


def errors_path(client: str, project_id: str, file_name: str) -> str:
    return f"{processing_base_path(client, project_id)}/errors/{file_name}"


def manifest_path(client: str, project_id: str) -> str:
    return f"{processing_base_path(client, project_id)}/manifest.json"


def get_doc_id(file_name: str) -> str:
    base = file_name.rsplit(".", 1)[0]
    return base.strip()

def get_extension(file_name: str) -> str:
    if "." not in file_name:
        return ""

    return "." + file_name.rsplit(".", 1)[-1].lower().strip()


def preview_pdf_path(client: str, project_id: str, doc_id: str) -> str:
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    return f"{client}/{project_id}/source/preview/{doc_id}.pdf"


def preview_html_path(client: str, project_id: str, doc_id: str) -> str:
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    return f"{client}/{project_id}/source/preview/{doc_id}.html"


def determine_viewer_type(file_name: str, extracted_text: str = "") -> str:
    extension = get_extension(file_name)

    if extension == ".pdf":
        return "pdf"

    if extension in [
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
    ]:
        return "image"

    if extension in [
        ".txt",
        ".csv",
        ".log",
        ".json",
        ".xml",
        ".html",
        ".htm",
    ]:
        return "text"

    if extension in [
        ".doc",
        ".docx",
        ".rtf",
        ".odt",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    ]:
        return "needs_preview_conversion"

    if extension in [".msg", ".eml"]:
        return "email"

    if extracted_text:
        return "text"

    return "unsupported"

def is_ocr_candidate(file_name: str) -> bool:
    extension = get_extension(file_name)

    return extension in [
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
    ]


def extract_text_with_document_intelligence(
    local_file_path: str,
    file_name: str,
) -> dict:
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "").strip()

    if not endpoint or not key:
        raise RuntimeError(
            "Azure Document Intelligence endpoint/key are not configured."
        )

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )

    with open(local_file_path, "rb") as file:
        poller = client.begin_analyze_document(
            model_id="prebuilt-read",
            body=file,
        )

    result = poller.result()

    text_parts = []
    page_count = len(result.pages or [])

    for page in result.pages or []:
        page_number = getattr(page, "page_number", "")

        if page_number:
            text_parts.append(f"\n\n--- Page {page_number} ---\n")

        for line in page.lines or []:
            content = getattr(line, "content", "")

            if content:
                text_parts.append(content)

    extracted = "\n".join(text_parts).strip()

    if not extracted and getattr(result, "content", ""):
        extracted = result.content.strip()

    text_length = len(extracted or "")

    if text_length == 0:
        quality = "No Text"
        confidence_score = 0
        warning = "OCR completed but no text was extracted."
    elif page_count > 0 and text_length / page_count < 50:
        quality = "Low"
        confidence_score = 40
        warning = "OCR completed with low text yield."
    elif page_count > 0 and text_length / page_count < 250:
        quality = "Medium"
        confidence_score = 70
        warning = ""
    else:
        quality = "High"
        confidence_score = 90
        warning = ""

    return {
        "text": extracted,
        "ocr_status": "Completed",
        "ocr_applied": True,
        "ocr_engine": "azure_document_intelligence_read",
        "ocr_page_count": page_count,
        "ocr_text_length": text_length,
        "ocr_confidence_score": confidence_score,
        "ocr_quality": quality,
        "ocr_warning": warning,
    }

def read_json_blob(container_client, blob_path: str, fallback: Any):
    blob_client = container_client.get_blob_client(blob_path)

    if not blob_client.exists():
        return fallback

    raw = blob_client.download_blob().readall().decode("utf-8")

    if not raw.strip():
        return fallback

    return json.loads(raw)


def write_json_blob(container_client, blob_path: str, data: Any):
    blob_client = container_client.get_blob_client(blob_path)
    blob_client.upload_blob(
        json.dumps(data, indent=2),
        overwrite=True,
    )


def copy_blob(container_client, source_blob_path: str, destination_blob_path: str):
    source_blob = container_client.get_blob_client(source_blob_path)
    destination_blob = container_client.get_blob_client(destination_blob_path)

    if not source_blob.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source blob not found: {source_blob_path}",
        )

    source_data = source_blob.download_blob().readall()
    destination_blob.upload_blob(source_data, overwrite=True)


def delete_blob_if_exists(container_client, blob_path: str):
    blob_client = container_client.get_blob_client(blob_path)

    if blob_client.exists():
        blob_client.delete_blob()


def extract_text_basic(local_file_path: str, file_name: str) -> dict:
    """
    Processing Center extraction layer.

    Phase 1:
    - Direct text extraction for text-like files
    - Azure Document Intelligence OCR for PDFs/images

    Later phases:
    - Office document conversion
    - MSG/EML parsing
    - family/attachment expansion
    - OCR confidence/page metadata
    """

    lower = file_name.lower()

    default = {
        "text": "",
        "ocr_status": "Not Required",
        "ocr_applied": False,
        "ocr_engine": "",
        "ocr_page_count": 0,
        "ocr_text_length": 0,
        "ocr_confidence_score": None,
        "ocr_quality": "",
        "ocr_warning": "",
    }

    if lower.endswith((
        ".txt",
        ".csv",
        ".log",
        ".json",
        ".xml",
        ".html",
        ".htm",
        ".dat",
    )):
        with open(
            local_file_path,
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as f:
            text = f.read()

        return {
            **default,
            "text": text,
            "ocr_text_length": len(text or ""),
        }

    if is_ocr_candidate(file_name):
        return extract_text_with_document_intelligence(
            local_file_path,
            file_name,
        )

    return default


def update_manifest_item(
    container_client,
    client: str,
    project_id: str,
    file_name: str,
    updates: Dict[str, Any],
):
    path = manifest_path(client, project_id)
    manifest = read_json_blob(
        container_client,
        path,
        {
            "client": client,
            "project_id": project_id,
            "files": [],
            "updated_at": "",
        },
    )

    files = manifest.get("files", [])

    existing = next(
        (
            item
            for item in files
            if item.get("file_name") == file_name
        ),
        None,
    )

    if existing:
        existing.update(updates)
    else:
        files.append(
            {
                "id": str(uuid.uuid4()),
                "file_name": file_name,
                **updates,
            }
        )

    manifest["files"] = files
    manifest["updated_at"] = now_iso()

    write_json_blob(container_client, path, manifest)


@router.get("/manifest")
def get_processing_manifest(
    workspace: str,
    client: str,
    project_id: str,
):
    container_name = get_container_name(workspace)
    service = get_blob_service_client()
    container = service.get_container_client(container_name)

    manifest = read_json_blob(
        container,
        manifest_path(client, project_id),
        {
            "client": client,
            "project_id": project_id,
            "files": [],
            "updated_at": "",
        },
    )

    return manifest


@router.post("/upload")
async def upload_processing_file(
    workspace: str,
    client: str = Form(...),
    project_id: str = Form(...),
    file: UploadFile = File(...),
):
    container_name = get_container_name(workspace)
    service = get_blob_service_client()
    container = service.get_container_client(container_name)

    file_name = file.filename or "uploaded_file"
    destination = upload_path(client, project_id, file_name)

    data = await file.read()

    container.get_blob_client(destination).upload_blob(
        data,
        overwrite=True,
    )

    doc_id = get_doc_id(file_name)
    extension = get_extension(file_name)

    update_manifest_item(
        container,
        client,
        project_id,
        file_name,
        {
            "doc_id": doc_id,
            "extension": extension,
            "status": "Uploaded",
            "uploaded_at": now_iso(),
            "upload_path": destination,
            "in_progress_path": "",
            "processed_native_path": "",
            "processed_text_path": "",
            "final_native_path": "",
            "final_text_path": "",
            "preview_pdf_path": preview_pdf_path(client, project_id, doc_id),
            "preview_html_path": preview_html_path(client, project_id, doc_id),
            "viewer_type": determine_viewer_type(file_name),
            "preview_available": False,
            "error": "",
        },
    )

    return {
        "ok": True,
        "file_name": file_name,
        "path": destination,
    }


@router.post("/start")
def start_processing(
    workspace: str,
    payload: StartProcessingPayload,
):
    container_name = get_container_name(workspace)
    service = get_blob_service_client()
    container = service.get_container_client(container_name)

    base = processing_base_path(payload.client, payload.project_id)
    uploads_prefix = f"{base}/uploads/"

    processed = []
    errors = []

    for blob in container.list_blobs(name_starts_with=uploads_prefix):
        upload_blob_path = blob.name
        file_name = upload_blob_path.split("/")[-1]

        if not file_name:
            continue

        doc_id = get_doc_id(file_name)
        progress_path = in_progress_path(payload.client, payload.project_id, file_name)

        try:
            update_manifest_item(
                container,
                payload.client,
                payload.project_id,
                file_name,
                {
                    "doc_id": doc_id,
                    "status": "In Progress",
                    "started_at": now_iso(),
                    "upload_path": upload_blob_path,
                    "in_progress_path": progress_path,
                    "error": "",
                },
            )

            copy_blob(container, upload_blob_path, progress_path)

            with tempfile.TemporaryDirectory() as tmpdir:
                local_file_path = os.path.join(tmpdir, file_name)

                with open(local_file_path, "wb") as f:
                    f.write(
                        container.get_blob_client(progress_path)
                        .download_blob()
                        .readall()
                    )

                extraction_result = extract_text_basic(local_file_path, file_name)
                extracted_text = extraction_result.get("text", "")

            processed_native = processed_native_path(
                payload.client,
                payload.project_id,
                file_name,
            )

            processed_text = processed_text_path(
                payload.client,
                payload.project_id,
                doc_id,
            )

            metadata_path = processed_metadata_path(
                payload.client,
                payload.project_id,
                doc_id,
            )

            final_native = final_native_path(
                payload.client,
                payload.project_id,
                file_name,
            )

            final_text = final_text_path(
                payload.client,
                payload.project_id,
                doc_id,
            )

            copy_blob(container, progress_path, processed_native)
            copy_blob(container, progress_path, final_native)

            container.get_blob_client(processed_text).upload_blob(
                extracted_text,
                overwrite=True,
            )

            container.get_blob_client(final_text).upload_blob(
                extracted_text,
                overwrite=True,
            )

            extension = get_extension(file_name)
            viewer_type = determine_viewer_type(file_name, extracted_text)

            preview_pdf = preview_pdf_path(
                payload.client,
                payload.project_id,
                doc_id,
            )

            preview_html = preview_html_path(
                payload.client,
                payload.project_id,
                doc_id,
            )

            metadata = {
                "doc_id": doc_id,
                "file_name": file_name,
                "extension": extension,
                "workspace": workspace,
                "client": payload.client,
                "project_id": payload.project_id,
                "status": "Processed",
                "processed_at": now_iso(),
                "upload_path": upload_blob_path,
                "processed_native_path": processed_native,
                "processed_text_path": processed_text,
                "final_native_path": final_native,
                "final_text_path": final_text,
                "preview_pdf_path": preview_pdf,
                "preview_html_path": preview_html,
                "viewer_type": viewer_type,
                "preview_available": viewer_type in ["pdf", "image", "text", "email"],
                "ocr_status": extraction_result.get("ocr_status", ""),
                "ocr_applied": extraction_result.get("ocr_applied", False),
                "ocr_engine": extraction_result.get("ocr_engine", ""),
                "ocr_page_count": extraction_result.get("ocr_page_count", 0),
                "ocr_text_length": extraction_result.get("ocr_text_length", len(extracted_text or "")),
                "ocr_confidence_score": extraction_result.get("ocr_confidence_score"),
                "ocr_quality": extraction_result.get("ocr_quality", ""),
                "ocr_warning": extraction_result.get("ocr_warning", ""),
                "text_length": len(extracted_text or ""),
            }

            write_json_blob(container, metadata_path, metadata)

            delete_blob_if_exists(container, upload_blob_path)
            delete_blob_if_exists(container, progress_path)

            update_manifest_item(
                container,
                payload.client,
                payload.project_id,
                file_name,
                {
                    **metadata,
                    "error": "",
                },
            )

            processed.append(metadata)

        except Exception as exc:
            error_destination = errors_path(
                payload.client,
                payload.project_id,
                file_name,
            )

            try:
                copy_blob(container, upload_blob_path, error_destination)
            except Exception:
                pass

            message = str(exc)

            update_manifest_item(
                container,
                payload.client,
                payload.project_id,
                file_name,
                {
                    "doc_id": doc_id,
                    "extension": get_extension(file_name),
                    "status": "Error",
                    "viewer_type": "unsupported",
                    "preview_available": False,
                    "error": message,
                    "ocr_status": "Failed" if is_ocr_candidate(file_name) else "Not Required",
                    "ocr_applied": is_ocr_candidate(file_name),
                    "ocr_engine": "azure_document_intelligence_read" if is_ocr_candidate(file_name) else "",
                    "ocr_page_count": 0,
                    "ocr_text_length": 0,
                    "ocr_confidence_score": 0 if is_ocr_candidate(file_name) else None,
                    "ocr_quality": "Failed" if is_ocr_candidate(file_name) else "",
                    "ocr_warning": message if is_ocr_candidate(file_name) else "",
                    "error_path": error_destination,
                    "failed_at": now_iso(),
                },
            )

            errors.append(
                {
                    "file_name": file_name,
                    "error": message,
                }
            )

    return {
        "ok": True,
        "processed_count": len(processed),
        "error_count": len(errors),
        "processed": processed,
        "errors": errors,
    }