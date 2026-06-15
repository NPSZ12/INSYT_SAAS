import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueClient

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
    
class StartProcessingJobPayload(BaseModel):
    client: str
    project_id: str
    job_type: str = "processing"
    requested_by: str = ""

class PromoteProcessingJobPayload(BaseModel):
    client: str
    project_id: str
    doc_ids: List[str] = []
    promote_all: bool = False

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

def get_review_blob_service_client() -> BlobServiceClient:
    conn = (
        os.getenv("AZURE_REVIEW_STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_FINAL_STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    if not conn:
        raise HTTPException(
            status_code=500,
            detail=(
                "Review storage is not configured. Set "
                "AZURE_REVIEW_STORAGE_CONNECTION_STRING or "
                "AZURE_STORAGE_CONNECTION_STRING."
            ),
        )

    return BlobServiceClient.from_connection_string(conn)


def copy_blob_between_containers(
    source_container,
    destination_container,
    source_blob_path: str,
    destination_blob_path: str,
):
    source_blob = source_container.get_blob_client(source_blob_path)
    destination_blob = destination_container.get_blob_client(destination_blob_path)

    if not source_blob.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source blob not found: {source_blob_path}",
        )

    source_data = source_blob.download_blob().readall()

    destination_blob.upload_blob(
        source_data,
        overwrite=True,
    )

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


def final_native_path(
    workspace: str,
    client: str,
    project_id: str,
    file_name: str,
) -> str:
    workspace = clean_path_part(workspace).lower()
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    file_name = clean_path_part(file_name)

    return f"{workspace}/{client}/{project_id}/source/native/{file_name}"


def final_text_path(
    workspace: str,
    client: str,
    project_id: str,
    doc_id: str,
) -> str:
    workspace = clean_path_part(workspace).lower()
    client = clean_path_part(client)
    project_id = clean_path_part(project_id)
    doc_id = clean_path_part(doc_id)

    return f"{workspace}/{client}/{project_id}/source/text/{doc_id}.txt"


def errors_path(client: str, project_id: str, file_name: str) -> str:
    return f"{processing_base_path(client, project_id)}/errors/{file_name}"


def manifest_path(client: str, project_id: str) -> str:
    return f"{processing_base_path(client, project_id)}/manifest.json"

def processing_jobs_base_path(client: str, project_id: str) -> str:
    return f"{processing_base_path(client, project_id)}/jobs"


def processing_job_path(client: str, project_id: str, job_id: str) -> str:
    return f"{processing_jobs_base_path(client, project_id)}/{job_id}.json"


def get_processing_queue_client() -> QueueClient:
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not conn:
        raise HTTPException(
            status_code=500,
            detail="AZURE_STORAGE_CONNECTION_STRING is not configured",
        )

    queue_name = os.getenv(
        "AZURE_PROCESSING_QUEUE_NAME",
        "insyt-processing-jobs",
    )

    queue_client = QueueClient.from_connection_string(
        conn_str=conn,
        queue_name=queue_name,
    )

    try:
        queue_client.create_queue()
    except ResourceExistsError:
        pass

    return queue_client

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
    review_service = get_review_blob_service_client()
    review_container = review_service.get_container_client(container_name)

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
                workspace,
                payload.client,
                payload.project_id,
                file_name,
            )

            final_text = final_text_path(
                workspace,
                payload.client,
                payload.project_id,
                doc_id,
            )

            copy_blob(container, progress_path, processed_native)
            copy_blob_between_containers(
                container,
                review_container,
                progress_path,
                final_native,
            )

            container.get_blob_client(processed_text).upload_blob(
                extracted_text,
                overwrite=True,
            )

            review_container.get_blob_client(final_text).upload_blob(
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
    
@router.post("/jobs/start")
def start_processing_job(
    workspace: str,
    payload: StartProcessingJobPayload,
):
    try:
        container_name = get_container_name(workspace)
        service = get_blob_service_client()
        container = service.get_container_client(container_name)

        job_id = str(uuid.uuid4())
        now = now_iso()

        base = processing_base_path(payload.client, payload.project_id)
        uploads_prefix = f"{base}/uploads/"

        upload_files = []

        for blob in container.list_blobs(name_starts_with=uploads_prefix):
            file_name = blob.name.split("/")[-1]

            if file_name:
                upload_files.append(
                    {
                        "file_name": file_name,
                        "upload_path": blob.name,
                        "status": "Queued",
                    }
                )
                
        if not upload_files:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "No uploaded files are waiting for background processing.",
                    "uploads_prefix": uploads_prefix,
                    "client": payload.client,
                    "project_id": payload.project_id,
                },
            )

        job = {
            "job_id": job_id,
            "workspace": workspace,
            "client": payload.client,
            "project_id": payload.project_id,
            "job_type": payload.job_type or "processing",
            "status": "Queued",
            "requested_by": payload.requested_by or "",
            "total_files": len(upload_files),
            "queued_files": len(upload_files),
            "processed_files": 0,
            "error_files": 0,
            "created_at": now,
            "started_at": "",
            "completed_at": "",
            "last_updated_at": now,
            "files": upload_files,
            "message": "Processing job queued.",
        }

        job_blob_path = processing_job_path(
            payload.client,
            payload.project_id,
            job_id,
        )

        write_json_blob(container, job_blob_path, job)

        queue_client = get_processing_queue_client()

        queue_message = {
            "job_id": job_id,
            "workspace": workspace,
            "client": payload.client,
            "project_id": payload.project_id,
            "job_blob_path": job_blob_path,
            "job_type": payload.job_type or "processing",
        }

        queue_client.send_message(json.dumps(queue_message))

        return {
            "ok": True,
            "job_id": job_id,
            "status": "Queued",
            "total_files": len(upload_files),
            "job_blob_path": job_blob_path,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to start processing job.",
                "workspace": workspace,
                "client": payload.client,
                "project_id": payload.project_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    
@router.get("/jobs")
def list_processing_jobs(
    workspace: str,
    client: str,
    project_id: str,
):
    try:
        container_name = get_container_name(workspace)
        service = get_blob_service_client()
        container = service.get_container_client(container_name)

        jobs_prefix = processing_jobs_base_path(
            client,
            project_id,
        ) + "/"

        jobs = []

        for blob in container.list_blobs(name_starts_with=jobs_prefix):
            if not blob.name.endswith(".json"):
                continue

            try:
                job = read_json_blob(
                    container,
                    blob.name,
                    None,
                )

                if job:
                    job_files = job.get("files", []) or []

                    file_names = [
                        str(item.get("file_name", ""))
                        for item in job_files
                        if str(item.get("file_name", "")).strip()
                    ]

                    latest_file_name = file_names[0] if file_names else ""

                    jobs.append(
                        {
                            "job_id": job.get("job_id", ""),
                            "workspace": job.get("workspace", workspace),
                            "client": job.get("client", client),
                            "project_id": job.get("project_id", project_id),
                            "job_type": job.get("job_type", ""),
                            "status": job.get("status", ""),
                            "requested_by": job.get("requested_by", ""),
                            "total_files": job.get("total_files", 0),
                            "queued_files": job.get("queued_files", 0),
                            "processed_files": job.get("processed_files", 0),
                            "error_files": job.get("error_files", 0),
                            "created_at": job.get("created_at", ""),
                            "started_at": job.get("started_at", ""),
                            "completed_at": job.get("completed_at", ""),
                            "last_updated_at": job.get("last_updated_at", ""),
                            "message": job.get("message", ""),
                            "job_blob_path": blob.name,
                            "latest_file_name": latest_file_name,
                            "file_names": file_names,
                            "files": job_files,
                        }
                    )

            except Exception:
                continue

        jobs.sort(
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

        return {
            "workspace": workspace,
            "client": client,
            "project_id": project_id,
            "jobs": jobs,
            "job_count": len(jobs),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to list processing jobs.",
                "workspace": workspace,
                "client": client,
                "project_id": project_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )

@router.post("/jobs/{job_id}/promote")
def promote_processing_job(
    workspace: str,
    job_id: str,
    payload: PromoteProcessingJobPayload,
):
    try:
        container_name = get_container_name(workspace)

        processing_service = get_blob_service_client()
        processing_container = processing_service.get_container_client(
            container_name
        )

        review_service = get_review_blob_service_client()
        review_container = review_service.get_container_client(
            container_name
        )

        job_blob_path = processing_job_path(
            payload.client,
            payload.project_id,
            job_id,
        )

        job = read_json_blob(
            processing_container,
            job_blob_path,
            None,
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Processing job not found.",
                    "job_id": job_id,
                    "job_blob_path": job_blob_path,
                },
            )

        requested_doc_ids = {
            str(doc_id).strip()
            for doc_id in payload.doc_ids or []
            if str(doc_id).strip()
        }

        files = job.get("files", []) or []

        promoted = []
        skipped = []
        errors = []

        selected_count = 0
        now = now_iso()

        for item in files:
            file_name = str(item.get("file_name", "")).strip()

            if not file_name:
                continue

            doc_id = str(
                item.get("doc_id")
                or get_doc_id(file_name)
            ).strip()

            should_promote = (
                payload.promote_all
                or doc_id in requested_doc_ids
                or file_name in requested_doc_ids
            )

            if not should_promote:
                continue

            selected_count += 1

            source_native = (
                item.get("processed_native_path")
                or processed_native_path(
                    payload.client,
                    payload.project_id,
                    file_name,
                )
            )

            source_text = (
                item.get("processed_text_path")
                or processed_text_path(
                    payload.client,
                    payload.project_id,
                    doc_id,
                )
            )

            native_destination = final_native_path(
                workspace,
                payload.client,
                payload.project_id,
                file_name,
            )

            text_destination = final_text_path(
                workspace,
                payload.client,
                payload.project_id,
                doc_id,
            )

            native_destination_blob = review_container.get_blob_client(
                native_destination
            )

            text_destination_blob = review_container.get_blob_client(
                text_destination
            )

            native_destination_exists = native_destination_blob.exists()
            text_destination_exists = text_destination_blob.exists()

            try:
                if native_destination_exists and text_destination_exists:
                    item.update(
                        {
                            "doc_id": doc_id,
                            "promotion_status": "Promoted",
                            "promotion_result": "already_promoted",
                            "promoted_at": item.get("promoted_at") or now,
                            "native_destination_exists": True,
                            "text_destination_exists": True,
                            "native_destination": native_destination,
                            "text_destination": text_destination,
                        }
                    )

                    update_manifest_item(
                        processing_container,
                        payload.client,
                        payload.project_id,
                        file_name,
                        {
                            "doc_id": doc_id,
                            "status": "Promoted",
                            "promotion_status": "Promoted",
                            "promotion_result": "already_promoted",
                            "promoted_at": item.get("promoted_at") or now,
                            "final_native_path": native_destination,
                            "final_text_path": text_destination,
                            "native_destination_exists": True,
                            "text_destination_exists": True,
                            "error": "",
                        },
                    )

                    skipped.append(
                        {
                            "doc_id": doc_id,
                            "file_name": file_name,
                            "status": "already_promoted",
                            "native_destination_exists": True,
                            "text_destination_exists": True,
                            "native_destination": native_destination,
                            "text_destination": text_destination,
                        }
                    )

                    continue

                if not native_destination_exists:
                    copy_blob_between_containers(
                        processing_container,
                        review_container,
                        source_native,
                        native_destination,
                    )

                if not text_destination_exists:
                    copy_blob_between_containers(
                        processing_container,
                        review_container,
                        source_text,
                        text_destination,
                    )

                item.update(
                    {
                        "doc_id": doc_id,
                        "promotion_status": "Promoted",
                        "promotion_result": "promoted",
                        "promoted_at": now,
                        "native_destination_exists": True,
                        "text_destination_exists": True,
                        "native_destination": native_destination,
                        "text_destination": text_destination,
                    }
                )

                update_manifest_item(
                    processing_container,
                    payload.client,
                    payload.project_id,
                    file_name,
                    {
                        "doc_id": doc_id,
                        "status": "Promoted",
                        "promotion_status": "Promoted",
                        "promotion_result": "promoted",
                        "promoted_at": now,
                        "final_native_path": native_destination,
                        "final_text_path": text_destination,
                        "native_destination_exists": True,
                        "text_destination_exists": True,
                        "error": "",
                    },
                )

                promoted.append(
                    {
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "status": "promoted",
                        "native_destination": native_destination,
                        "text_destination": text_destination,
                    }
                )

            except Exception as exc:
                message = str(exc)

                item.update(
                    {
                        "doc_id": doc_id,
                        "promotion_status": "Error",
                        "promotion_result": "error",
                        "promotion_error": message,
                        "promotion_error_at": now_iso(),
                    }
                )

                errors.append(
                    {
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "status": "error",
                        "error": message,
                    }
                )

        if selected_count == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "No matching documents were selected for promotion.",
                    "requested_doc_ids": list(requested_doc_ids),
                    "promote_all": payload.promote_all,
                },
            )

        promoted_or_done_count = len(promoted) + len(skipped)

        job["files"] = files
        job["last_updated_at"] = now_iso()
        job["last_promoted_at"] = now_iso()
        job["promoted_files"] = sum(
            1
            for item in files
            if item.get("promotion_status") == "Promoted"
        )
        job["promotion_error_files"] = sum(
            1
            for item in files
            if item.get("promotion_status") == "Error"
        )

        if promoted_or_done_count > 0 and not errors:
            job["promotion_status"] = "Promoted"
            job["message"] = "Selected review-ready files have been promoted."
        elif promoted_or_done_count > 0 and errors:
            job["promotion_status"] = "Partially Promoted"
            job["message"] = "Some files promoted; some files had errors."
        else:
            job["promotion_status"] = "Promotion Error"
            job["message"] = "Promotion failed."

        write_json_blob(
            processing_container,
            job_blob_path,
            job,
        )

        return {
            "ok": len(errors) == 0,
            "workspace": workspace,
            "client": payload.client,
            "project_id": payload.project_id,
            "job_id": job_id,
            "promote_all": payload.promote_all,
            "requested_doc_ids": list(requested_doc_ids),
            "selected_count": selected_count,
            "promoted_count": len(promoted),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "promoted": promoted,
            "skipped": skipped,
            "errors": errors,
            "promotion_status": job.get("promotion_status", ""),
            "message": job.get("message", ""),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to promote processing job results.",
                "job_id": job_id,
                "client": payload.client,
                "project_id": payload.project_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    
@router.get("/jobs/{job_id}")
def get_processing_job(
    workspace: str,
    job_id: str,
    client: str,
    project_id: str,
):
    try:
        container_name = get_container_name(workspace)
        service = get_blob_service_client()
        container = service.get_container_client(container_name)

        job_blob_path = processing_job_path(
            client,
            project_id,
            job_id,
        )

        blob_client = container.get_blob_client(job_blob_path)

        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Processing job not found.",
                    "job_id": job_id,
                    "job_blob_path": job_blob_path,
                    "client": client,
                    "project_id": project_id,
                },
            )

        raw = (
            blob_client.download_blob()
            .readall()
            .decode("utf-8")
        )

        return json.loads(raw)

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to load processing job.",
                "job_id": job_id,
                "client": client,
                "project_id": project_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )