import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from azure.storage.blob import BlobServiceClient

from app.services.azure_blob_service import get_container_client

router = APIRouter(
    prefix="/api/summaries/processing-center",
    tags=["summaries-processing-center"],
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return (
        value.replace("\\", "_")
        .replace("/", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
    )


def get_summaries_container():
    try:
        return get_container_client()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to resolve Summaries storage container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

def get_summaries_review_container():
    connection_string = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING")

    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail="Missing INSYT_REVIEW_STORAGE_CONNECTION_STRING.",
        )

    if "AccountName=insytreviewstorage" not in connection_string:
        raise HTTPException(
            status_code=500,
            detail=(
                "INSYT_REVIEW_STORAGE_CONNECTION_STRING is not pointing to "
                "insytreviewstorage."
            ),
        )

    try:
        service_client = BlobServiceClient.from_connection_string(
            connection_string
        )

        return service_client.get_container_client("insyt-summaries")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to resolve Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

def get_summaries_review_container():
    connection_string = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING")

    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail="Missing INSYT_REVIEW_STORAGE_CONNECTION_STRING.",
        )

    if "AccountName=insytreviewstorage" not in connection_string:
        raise HTTPException(
            status_code=500,
            detail=(
                "INSYT_REVIEW_STORAGE_CONNECTION_STRING is not pointing to "
                "insytreviewstorage."
            ),
        )

    try:
        service_client = BlobServiceClient.from_connection_string(
            connection_string
        )

        return service_client.get_container_client("insyt-summaries")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to resolve Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

def get_project_base(client: str, project_id: str) -> str:
    return f"{client}/summaries/{project_id}"


def guess_doc_id_from_blob(blob_name: str) -> str:
    name = os.path.basename(blob_name)
    stem = os.path.splitext(name)[0]

    if stem.upper().startswith("INSYT"):
        return stem.split("_")[0].split("-")[0]

    return stem


def normalize_pdf_name(blob_name: str) -> str:
    return os.path.basename(blob_name)


def find_matching_text_blob(
    text_blobs: list[str],
    native_blob_name: str,
    doc_id: str,
) -> str | None:
    native_stem = os.path.splitext(os.path.basename(native_blob_name))[0].lower()
    doc_id_lower = doc_id.lower()

    for text_blob in text_blobs:
        text_stem = os.path.splitext(os.path.basename(text_blob))[0].lower()

        if text_stem == native_stem:
            return text_blob

        if doc_id_lower and doc_id_lower in text_stem:
            return text_blob

    return None


def read_blob_text(container, blob_name: str) -> str:
    blob = container.get_blob_client(blob_name)

    if not blob.exists():
        return ""

    data = blob.download_blob().readall()
    return data.decode("utf-8", errors="ignore")


def upload_json_blob(container, blob_name: str, payload: dict[str, Any]) -> None:
    container.upload_blob(
        name=blob_name,
        data=json.dumps(payload, indent=2, ensure_ascii=False),
        overwrite=True,
        content_settings=None,
    )

def read_json_blob(container, blob_name: str) -> dict[str, Any]:
    text = read_blob_text(container, blob_name)

    if not text.strip():
        return {}

    return json.loads(text)


def copy_blob_within_container(
    container,
    source_blob_name: str,
    destination_blob_name: str,
    overwrite: bool = True,
) -> None:
    source_blob = container.get_blob_client(source_blob_name)
    destination_blob = container.get_blob_client(destination_blob_name)

    if not source_blob.exists():
        raise FileNotFoundError(f"Source blob not found: {source_blob_name}")

    if destination_blob.exists() and not overwrite:
        return

    data = source_blob.download_blob().readall()
    destination_blob.upload_blob(data, overwrite=overwrite)

def load_staged_job_detail(
    container,
    client: str,
    project_id: str,
    job_id: str,
) -> dict[str, Any]:
    base = get_project_base(client, project_id)

    report_candidates = [
        f"{base}/processing_center/staged/{job_id}/reports/job_detail.json",
        f"{base}/processing_center/staged/{job_id}/report/job_detail.json",
        f"{base}/processing_center/staged/{job_id}/job_detail.json",
        f"{base}/processing_center/jobs/{job_id}/job_detail.json",
        f"{base}/processing_center/jobs/{job_id}/status.json",
    ]

    for report_blob in report_candidates:
        blob = container.get_blob_client(report_blob)

        if blob.exists():
            try:
                detail = read_json_blob(container, report_blob)
                detail["_detail_blob"] = report_blob
                return detail
            except Exception:
                continue

    return {}

def list_staged_docs_from_paths(
    container,
    client: str,
    project_id: str,
    job_id: str,
) -> list[dict[str, Any]]:
    base = get_project_base(client, project_id)

    native_prefix = f"{base}/processing_center/staged/{job_id}/native/"
    text_prefix = f"{base}/processing_center/staged/{job_id}/text/"

    native_blobs = [
        blob.name
        for blob in container.list_blobs(name_starts_with=native_prefix)
        if not blob.name.endswith("/")
    ]

    text_blobs = [
        blob.name
        for blob in container.list_blobs(name_starts_with=text_prefix)
        if not blob.name.endswith("/")
    ]

    docs: list[dict[str, Any]] = []

    for native_blob in native_blobs:
        doc_id = guess_doc_id_from_blob(native_blob)
        text_blob = find_matching_text_blob(text_blobs, native_blob, doc_id)

        docs.append(
            {
                "doc_id": doc_id,
                "original_filename": os.path.basename(native_blob),
                "native_staged_blob_path": native_blob,
                "text_staged_blob_path": text_blob,
                "ready_to_promote": bool(native_blob and text_blob),
            }
        )

    return docs

def find_staged_blob_by_doc_id(
    container,
    client: str,
    project_id: str,
    job_id: str,
    doc_id: str,
    kind: str,
) -> str | None:
    base = get_project_base(client, project_id)

    kind_folder = "native" if kind == "native" else "text"

    candidate_prefixes = [
        f"{base}/processing_center/staged/{job_id}/{kind_folder}/",
        f"{base}/processing_center/jobs/{job_id}/{kind_folder}/",
        f"{base}/processing_center/staged/{job_id}/",
        f"{base}/processing_center/jobs/{job_id}/",
    ]

    doc_id_lower = str(doc_id or "").lower()

    for prefix in candidate_prefixes:
        try:
            for blob in container.list_blobs(name_starts_with=prefix):
                blob_name = blob.name

                if blob_name.endswith("/"):
                    continue

                filename = os.path.basename(blob_name).lower()

                if doc_id_lower and doc_id_lower in filename:
                    return blob_name
        except Exception:
            continue

    return None

def list_summary_extraction_files(
    container,
    client: str,
    project_id: str,
    stage: str,
) -> list[dict[str, Any]]:
    base = get_project_base(client, project_id)

    native_prefix = f"{base}/summary_extraction/{stage}/native/"
    text_prefix = f"{base}/summary_extraction/{stage}/text/"
    outline_prefix = f"{base}/summary_extraction/{stage}/outlines/"

    native_blobs = [
        blob.name
        for blob in container.list_blobs(name_starts_with=native_prefix)
        if not blob.name.endswith("/")
    ]

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

    outline_by_doc_id: dict[str, str] = {}

    for outline_blob in outline_blobs:
        doc_id = os.path.splitext(os.path.basename(outline_blob))[0]
        outline_by_doc_id[doc_id] = outline_blob

    files: list[dict[str, Any]] = []

    for native_blob in native_blobs:
        doc_id = guess_doc_id_from_blob(native_blob)
        text_blob = find_matching_text_blob(text_blobs, native_blob, doc_id)

        files.append(
            {
                "doc_id": doc_id,
                "pdf_name": normalize_pdf_name(native_blob),
                "native_blob": native_blob,
                "text_blob": text_blob,
                "outline_blob": outline_by_doc_id.get(doc_id),
                "status": "ready" if text_blob else "missing_text",
            }
        )

    return files


def list_summary_extraction_manifests(
    container,
    client: str,
    project_id: str,
    stage: str,
) -> list[dict[str, Any]]:
    base = get_project_base(client, project_id)
    manifest_prefix = f"{base}/summary_extraction/{stage}/manifest/"

    manifests: list[dict[str, Any]] = []

    for blob in container.list_blobs(name_starts_with=manifest_prefix):
        if blob.name.endswith("/"):
            continue

        manifest_data: dict[str, Any] = {}

        try:
            manifest_data = read_json_blob(container, blob.name)
        except Exception as exc:
            manifest_data = {
                "status": "read_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

        manifests.append(
            {
                "manifest_blob": blob.name,
                "manifest": manifest_data,
            }
        )

    return manifests


def build_summary_extraction_result_payload(
    client: str,
    project_id: str,
    doc_id: str,
    pdf_name: str,
    native_blob: str,
    text_blob: str | None,
    result_native_blob: str,
    result_text_blob: str,
    outline_blob: str,
    text: str,
) -> dict[str, Any]:
    items = build_starter_outline_items(text)

    return {
        "status": "extracted",
        "client": client,
        "project_id": project_id,
        "doc_id": doc_id,
        "pdf_name": pdf_name,
        "source_native_blob": native_blob,
        "source_text_blob": text_blob,
        "result_native_blob": result_native_blob,
        "result_text_blob": result_text_blob,
        "outline_blob": outline_blob,
        "item_count": len(items),
        "items": items,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "source": "summary_extraction",
        "version": 1,
    }

def build_starter_outline_items(text: str) -> list[dict[str, Any]]:
    cleaned = (text or "").strip()

    if not cleaned:
        return [
            {
                "summary_key": "summary-001",
                "title": "Document Summary",
                "start_page": None,
                "end_page": None,
                "status": "available",
                "source": "starter_outline",
            }
        ]

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    candidates: list[dict[str, Any]] = []

    for index, line in enumerate(lines[:500]):
        lowered = line.lower()

        looks_like_heading = (
            lowered.startswith("summary")
            or lowered.startswith("medical")
            or lowered.startswith("records")
            or lowered.startswith("deposition")
            or lowered.startswith("claim")
            or lowered.startswith("incident")
            or lowered.startswith("section")
            or lowered.startswith("exhibit")
        )

        if looks_like_heading and len(line) <= 140:
            candidates.append(
                {
                    "summary_key": f"summary-{len(candidates) + 1:03d}",
                    "title": line[:140],
                    "start_page": None,
                    "end_page": None,
                    "status": "available",
                    "source": "detected_heading",
                    "line_index": index,
                }
            )

        if len(candidates) >= 50:
            break

    if not candidates:
        candidates.append(
            {
                "summary_key": "summary-001",
                "title": "Document Summary",
                "start_page": None,
                "end_page": None,
                "status": "available",
                "source": "starter_outline",
            }
        )

    return candidates


@router.get("/summaries-ready")
def get_summaries_ready_files(
    client: str = Query(...),
    project: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    resolved_project_id = project_id or project

    if not resolved_project_id:
        raise HTTPException(status_code=400, detail="project or project_id is required")

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to initialize Summaries review/staging container: {type(exc).__name__}: {exc}",
        )

    base = get_project_base(client, resolved_project_id)

    native_prefix = f"{base}/source/native/"
    text_prefix = f"{base}/source/text/"
    outline_prefix = f"{base}/review/summary-outlines/"

    try:
        native_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=native_prefix)
            if not blob.name.endswith("/")
        ]

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
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summaries source files: {type(exc).__name__}: {exc}",
        )

    outline_by_doc_id: dict[str, str] = {}
    outline_summary_counts: dict[str, int] = {}

    for outline_blob in outline_blobs:
        doc_id = os.path.splitext(os.path.basename(outline_blob))[0]
        outline_by_doc_id[doc_id] = outline_blob

        try:
            outline_text = read_blob_text(container, outline_blob)
            outline_json = json.loads(outline_text or "{}")
            outline_summary_counts[doc_id] = len(outline_json.get("items") or [])
        except Exception:
            outline_summary_counts[doc_id] = 0

    files: list[dict[str, Any]] = []

    for native_blob in native_blobs:
        doc_id = guess_doc_id_from_blob(native_blob)
        matching_text_blob = find_matching_text_blob(text_blobs, native_blob, doc_id)

        outline_blob = outline_by_doc_id.get(doc_id)

        files.append(
            {
                "doc_id": doc_id,
                "pdf_name": normalize_pdf_name(native_blob),
                "native_blob": native_blob,
                "text_blob": matching_text_blob,
                "outline_blob": outline_blob,
                "summary_count": outline_summary_counts.get(doc_id, 0),
                "status": "outlined" if outline_blob else "ready",
            }
        )

    return {
        "status": "ok",
        "client": client,
        "project_id": resolved_project_id,
        "files": files,
        "native_count": len(native_blobs),
        "text_count": len(text_blobs),
        "outline_count": len(outline_blobs),
    }

@router.get("/available-summaries")
def get_available_summaries(
    client: str = Query(...),
    project: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    resolved_project_id = project_id or project

    if not resolved_project_id:
        raise HTTPException(status_code=400, detail="project or project_id is required")

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to initialize Summaries review/staging container: {type(exc).__name__}: {exc}",
        )

    base = get_project_base(client, resolved_project_id)

    outline_prefix = f"{base}/review/summary-outlines/"

    try:
        outline_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=outline_prefix)
            if not blob.name.endswith("/")
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summaries outlines: {type(exc).__name__}: {exc}",
        )

    items: list[dict[str, Any]] = []
    outline_count = 0
    failed_outlines: list[dict[str, Any]] = []

    for outline_blob in outline_blobs:
        try:
            outline = read_json_blob(container, outline_blob)
        except Exception as exc:
            failed_outlines.append(
                {
                    "outline_blob": outline_blob,
                    "reason": f"read_failed: {type(exc).__name__}: {exc}",
                }
            )
            continue

        outline_count += 1

        doc_id = outline.get("doc_id") or os.path.splitext(
            os.path.basename(outline_blob)
        )[0]

        pdf_name = outline.get("pdf_name") or ""
        native_blob = outline.get("native_blob") or ""
        text_blob = outline.get("text_blob") or ""

        outline_items = outline.get("items") or []

        for index, item in enumerate(outline_items):
            summary_key = (
                item.get("summary_key")
                or item.get("id")
                or f"summary-{index + 1:03d}"
            )

            summary_status = str(item.get("status") or "available").lower()

            if summary_status not in ["available", "ready", "unassigned"]:
                continue

            items.append(
                {
                    "id": f"{doc_id}:{summary_key}",
                    "doc_id": doc_id,
                    "summary_key": summary_key,
                    "title": item.get("title") or f"Summary {index + 1}",
                    "pdf_name": pdf_name,
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "outline_blob": outline_blob,
                    "status": "available",
                    "source": item.get("source") or outline.get("source") or "outline",
                    "start_page": item.get("start_page") or item.get("page_start"),
                    "end_page": item.get("end_page") or item.get("page_end"),
                    "page": item.get("page"),
                    "line_index": item.get("line_index"),
                }
            )

    return {
        "status": "ok",
        "client": client,
        "project_id": resolved_project_id,
        "outline_count": outline_count,
        "available_count": len(items),
        "items": items,
        "failed_outlines": failed_outlines,
    }

@router.get("/extraction-pending")
def get_summary_extraction_pending(
    client: str = Query(...),
    project: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    resolved_project_id = project_id or project

    if not resolved_project_id:
        raise HTTPException(status_code=400, detail="project or project_id is required")

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to initialize Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    try:
        files = list_summary_extraction_files(
            container,
            client,
            resolved_project_id,
            "pending",
        )

        manifests = list_summary_extraction_manifests(
            container,
            client,
            resolved_project_id,
            "pending",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summary Extraction pending files: {type(exc).__name__}: {exc}",
        )

    return {
        "status": "ok",
        "client": client,
        "project_id": resolved_project_id,
        "storage_account": getattr(container, "account_name", ""),
        "container": getattr(container, "container_name", ""),
        "pending_count": len(files),
        "files": files,
        "manifest_count": len(manifests),
        "manifests": manifests,
    }


@router.get("/extraction-results")
def get_summary_extraction_results(
    client: str = Query(...),
    project: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    resolved_project_id = project_id or project

    if not resolved_project_id:
        raise HTTPException(status_code=400, detail="project or project_id is required")

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to initialize Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    try:
        files = list_summary_extraction_files(
            container,
            client,
            resolved_project_id,
            "results",
        )

        manifests = list_summary_extraction_manifests(
            container,
            client,
            resolved_project_id,
            "results",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summary Extraction result files: {type(exc).__name__}: {exc}",
        )

    return {
        "status": "ok",
        "client": client,
        "project_id": resolved_project_id,
        "storage_account": getattr(container, "account_name", ""),
        "container": getattr(container, "container_name", ""),
        "result_count": len(files),
        "files": files,
        "manifest_count": len(manifests),
        "manifests": manifests,
    }

@router.post("/upload-to-summary-extraction")
def upload_to_summary_extraction(payload: dict[str, Any]):
    client = payload.get("client")
    project_id = payload.get("project_id") or payload.get("project")
    job_id = payload.get("job_id")
    upload_all = bool(payload.get("upload_all", False))
    requested_doc_ids = payload.get("doc_ids") or []

    if not client or not project_id or not job_id:
        raise HTTPException(
            status_code=400,
            detail="client, project_id, and job_id are required",
        )

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to initialize Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    requested_doc_id_set = {
        str(doc_id)
        for doc_id in requested_doc_ids
        if str(doc_id).strip()
    }

    docs = payload.get("docs") or []

    if not docs:
        detail = load_staged_job_detail(container, client, project_id, job_id)
        docs = detail.get("docs") or detail.get("documents") or []

    if not docs:
        try:
            docs = list_staged_docs_from_paths(container, client, project_id, job_id)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Unable to list staged Summary Extraction candidates: {type(exc).__name__}: {exc}",
            )

    if not docs:
        return {
            "status": "ok",
            "message": "No staged documents were found to upload to Summary Extraction.",
            "client": client,
            "project_id": project_id,
            "job_id": job_id,
            "manifest_blob": "",
            "uploaded_count": 0,
            "skipped_count": 1,
            "error_count": 0,
            "uploaded": [],
            "skipped": [
                {
                    "doc_id": "",
                    "status": "skipped",
                    "message": "no_staged_docs_found",
                }
            ],
            "errors": [],
        }

    uploaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    base = get_project_base(client, project_id)

    pending_native_prefix = f"{base}/summary_extraction/pending/native/"
    pending_text_prefix = f"{base}/summary_extraction/pending/text/"
    manifest_prefix = f"{base}/summary_extraction/pending/manifest/"
    container_name = getattr(container, "container_name", "")
    account_name = getattr(container, "account_name", "")

    selected_docs = []

    for doc in docs:
        doc_id = str(doc.get("doc_id") or "").strip()

        if not doc_id:
            skipped.append(
                {
                    "doc_id": "",
                    "status": "skipped",
                    "message": "missing_doc_id",
                }
            )
            continue

        if not upload_all and doc_id not in requested_doc_id_set:
            continue

        native_blob = (
            doc.get("native_staged_blob_path")
            or doc.get("native_blob_path")
            or doc.get("native_blob")
        )

        text_blob = (
            doc.get("text_staged_blob_path")
            or doc.get("text_blob_path")
            or doc.get("text_blob")
        )

        if not native_blob or not text_blob:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": "skipped",
                    "message": "missing_native_or_text_staged_blob",
                }
            )
            continue

        selected_docs.append(
            {
                "doc_id": doc_id,
                "original_filename": doc.get("original_filename") or "",
                "native_staged_blob_path": native_blob,
                "text_staged_blob_path": text_blob,
            }
        )

    if not selected_docs:
        skipped.append(
            {
                "doc_id": "",
                "status": "skipped",
                "message": (
                    "no_matching_docs_selected"
                    if not upload_all
                    else "no_ready_docs_found"
                ),
            }
        )
    
    for doc in selected_docs:
        doc_id = doc["doc_id"]
        original_filename = doc.get("original_filename") or f"{doc_id}.pdf"

        native_staged_blob_path = str(doc.get("native_staged_blob_path") or "")
        text_staged_blob_path = str(doc.get("text_staged_blob_path") or "")

        native_ext = os.path.splitext(native_staged_blob_path)[1] or ".pdf"
        text_ext = os.path.splitext(text_staged_blob_path)[1] or ".txt"

        native_destination = f"{pending_native_prefix}{safe_name(doc_id)}{native_ext}"
        text_destination = f"{pending_text_prefix}{safe_name(doc_id)}{text_ext}"

        native_source = native_staged_blob_path
        text_source = text_staged_blob_path

        if not container.get_blob_client(native_source).exists():
            resolved_native_source = find_staged_blob_by_doc_id(
                container,
                client,
                project_id,
                job_id,
                doc_id,
                "native",
            )

            if resolved_native_source:
                native_source = resolved_native_source

        if not container.get_blob_client(text_source).exists():
            resolved_text_source = find_staged_blob_by_doc_id(
                container,
                client,
                project_id,
                job_id,
                doc_id,
                "text",
            )

            if resolved_text_source:
                text_source = resolved_text_source

        try:
            copy_blob_within_container(
                container,
                native_source,
                native_destination,
                overwrite=True,
            )

            copy_blob_within_container(
                container,
                text_source,
                text_destination,
                overwrite=True,
            )
        except Exception as exc:
            errors.append(
                {
                    "doc_id": doc_id,
                    "status": "error",
                    "message": (
                        f"copy_failed: {type(exc).__name__}: {exc}; "
                        f"native_source={native_source}; "
                        f"text_source={text_source}"
                    ),
                }
            )
            continue

        uploaded.append(
            {
                "doc_id": doc_id,
                "status": "uploaded_to_summary_extraction",
                "original_filename": original_filename,
                "native_source": native_source,
                "text_source": text_source,
                "native_destination": native_destination,
                "text_destination": text_destination,
            }
        )

    manifest = {
        "status": "pending_summary_extraction",
        "client": client,
        "project_id": project_id,
        "job_id": job_id,
        "upload_all": upload_all,
        "requested_doc_ids": list(requested_doc_id_set),
        "uploaded_count": len(uploaded),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "uploaded": uploaded,
        "skipped": skipped,
        "errors": errors,
        "created_at": utc_now_iso(),
        "source": "summaries_processing_center",
        "version": 1,
    }

    manifest_blob = f"{manifest_prefix}{safe_name(job_id)}.json"

    try:
        upload_json_blob(container, manifest_blob, manifest)
    except Exception as exc:
        errors.append(
            {
                "doc_id": "",
                "status": "error",
                "message": f"manifest_upload_failed: {type(exc).__name__}: {exc}",
            }
        )

    return {
        "status": "ok",
        "message": f"Uploaded {len(uploaded)} doc(s) to Summary Extraction.",
        "client": client,
        "project_id": project_id,
        "job_id": job_id,
        "storage_account": account_name,
        "container": container_name,
        "manifest_blob": manifest_blob,
        "uploaded_count": len(uploaded),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "uploaded": uploaded,
        "skipped": skipped,
        "errors": errors,
    }

@router.post("/run-summary-extraction")
def run_summary_extraction(payload: dict[str, Any]):
    client = payload.get("client")
    project_id = payload.get("project_id") or payload.get("project")
    run_all = bool(payload.get("run_all", False))
    requested_doc_ids = payload.get("doc_ids") or []
    overwrite = bool(payload.get("overwrite", True))

    if not client or not project_id:
        raise HTTPException(
            status_code=400,
            detail="client and project_id are required",
        )

    requested_doc_id_set = {
        str(doc_id)
        for doc_id in requested_doc_ids
        if str(doc_id).strip()
    }

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to initialize Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    try:
        pending_files = list_summary_extraction_files(
            container,
            client,
            project_id,
            "pending",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list pending Summary Extraction files: {type(exc).__name__}: {exc}",
        )

    selected_files: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for file_item in pending_files:
        doc_id = str(file_item.get("doc_id") or "").strip()

        if not doc_id:
            skipped.append(
                {
                    "doc_id": "",
                    "status": "skipped",
                    "message": "missing_doc_id",
                }
            )
            continue

        if not run_all and doc_id not in requested_doc_id_set:
            continue

        if not file_item.get("native_blob") or not file_item.get("text_blob"):
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": "skipped",
                    "message": "missing_pending_native_or_text_blob",
                    "native_blob": file_item.get("native_blob"),
                    "text_blob": file_item.get("text_blob"),
                }
            )
            continue

        selected_files.append(file_item)

    if not selected_files:
        skipped.append(
            {
                "doc_id": "",
                "status": "skipped",
                "message": (
                    "no_matching_pending_docs_selected"
                    if not run_all
                    else "no_pending_docs_ready"
                ),
            }
        )

    base = get_project_base(client, project_id)

    result_native_prefix = f"{base}/summary_extraction/results/native/"
    result_text_prefix = f"{base}/summary_extraction/results/text/"
    result_outline_prefix = f"{base}/summary_extraction/results/outlines/"
    result_manifest_prefix = f"{base}/summary_extraction/results/manifest/"

    run_id = f"RUN-{uuid.uuid4().hex[:16].upper()}"

    for file_item in selected_files:
        doc_id = str(file_item["doc_id"])
        native_blob = str(file_item["native_blob"])
        text_blob = str(file_item["text_blob"])
        pdf_name = file_item.get("pdf_name") or f"{doc_id}.pdf"

        native_ext = os.path.splitext(native_blob)[1] or ".pdf"
        text_ext = os.path.splitext(text_blob)[1] or ".txt"

        result_native_blob = f"{result_native_prefix}{safe_name(doc_id)}{native_ext}"
        result_text_blob = f"{result_text_prefix}{safe_name(doc_id)}{text_ext}"
        result_outline_blob = f"{result_outline_prefix}{safe_name(doc_id)}.json"

        try:
            if (
                not overwrite
                and container.get_blob_client(result_native_blob).exists()
                and container.get_blob_client(result_text_blob).exists()
                and container.get_blob_client(result_outline_blob).exists()
            ):
                skipped.append(
                    {
                        "doc_id": doc_id,
                        "status": "skipped",
                        "message": "result_exists",
                        "native_result": result_native_blob,
                        "text_result": result_text_blob,
                        "outline_result": result_outline_blob,
                    }
                )
                continue

            text = read_blob_text(container, text_blob)

            copy_blob_within_container(
                container,
                native_blob,
                result_native_blob,
                overwrite=True,
            )

            container.upload_blob(
                name=result_text_blob,
                data=text,
                overwrite=True,
            )

            outline_payload = build_summary_extraction_result_payload(
                client=client,
                project_id=project_id,
                doc_id=doc_id,
                pdf_name=pdf_name,
                native_blob=native_blob,
                text_blob=text_blob,
                result_native_blob=result_native_blob,
                result_text_blob=result_text_blob,
                outline_blob=result_outline_blob,
                text=text,
            )

            upload_json_blob(container, result_outline_blob, outline_payload)

            processed.append(
                {
                    "doc_id": doc_id,
                    "status": "extracted",
                    "pdf_name": pdf_name,
                    "pending_native_blob": native_blob,
                    "pending_text_blob": text_blob,
                    "result_native_blob": result_native_blob,
                    "result_text_blob": result_text_blob,
                    "result_outline_blob": result_outline_blob,
                    "summary_count": len(outline_payload.get("items") or []),
                }
            )

        except Exception as exc:
            errors.append(
                {
                    "doc_id": doc_id,
                    "status": "error",
                    "message": f"summary_extraction_failed: {type(exc).__name__}: {exc}",
                    "pending_native_blob": native_blob,
                    "pending_text_blob": text_blob,
                }
            )

    manifest = {
        "status": "completed" if not errors else "completed_with_errors",
        "client": client,
        "project_id": project_id,
        "run_id": run_id,
        "run_all": run_all,
        "requested_doc_ids": list(requested_doc_id_set),
        "processed_count": len(processed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "created_at": utc_now_iso(),
        "source": "summary_extraction_runner",
        "version": 1,
    }

    manifest_blob = f"{result_manifest_prefix}{safe_name(run_id)}.json"

    try:
        upload_json_blob(container, manifest_blob, manifest)
    except Exception as exc:
        errors.append(
            {
                "doc_id": "",
                "status": "error",
                "message": f"result_manifest_upload_failed: {type(exc).__name__}: {exc}",
            }
        )

    return {
        "status": "ok",
        "message": f"Ran Summary Extraction for {len(processed)} doc(s).",
        "client": client,
        "project_id": project_id,
        "run_id": run_id,
        "storage_account": getattr(container, "account_name", ""),
        "container": getattr(container, "container_name", ""),
        "manifest_blob": manifest_blob,
        "processed_count": len(processed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }

@router.post("/promote-extraction-results")
def promote_summary_extraction_results(payload: dict[str, Any]):
    client = payload.get("client")
    project_id = payload.get("project_id") or payload.get("project")
    promote_all = bool(payload.get("promote_all", False))
    requested_doc_ids = payload.get("doc_ids") or []
    overwrite = bool(payload.get("overwrite", True))

    if not client or not project_id:
        raise HTTPException(
            status_code=400,
            detail="client and project_id are required",
        )

    requested_doc_id_set = {
        str(doc_id)
        for doc_id in requested_doc_ids
        if str(doc_id).strip()
    }

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to initialize Summaries review/staging container: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    try:
        result_files = list_summary_extraction_files(
            container,
            client,
            project_id,
            "results",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summary Extraction results: {type(exc).__name__}: {exc}",
        )

    selected_files: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for file_item in result_files:
        doc_id = str(file_item.get("doc_id") or "").strip()

        if not doc_id:
            skipped.append(
                {
                    "doc_id": "",
                    "status": "skipped",
                    "message": "missing_doc_id",
                }
            )
            continue

        if not promote_all and doc_id not in requested_doc_id_set:
            continue

        native_blob = file_item.get("native_blob")
        text_blob = file_item.get("text_blob")
        outline_blob = file_item.get("outline_blob")

        if not native_blob or not text_blob or not outline_blob:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "status": "skipped",
                    "message": "missing_result_native_text_or_outline_blob",
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "outline_blob": outline_blob,
                }
            )
            continue

        selected_files.append(file_item)

    if not selected_files:
        skipped.append(
            {
                "doc_id": "",
                "status": "skipped",
                "message": (
                    "no_matching_extraction_results_selected"
                    if not promote_all
                    else "no_extraction_results_ready"
                ),
            }
        )

    base = get_project_base(client, project_id)

    source_native_prefix = f"{base}/source/native/"
    source_text_prefix = f"{base}/source/text/"
    review_outline_prefix = f"{base}/review/summary-outlines/"
    promotion_manifest_prefix = f"{base}/summary_extraction/promoted/manifest/"

    promotion_id = f"PROMOTE-{uuid.uuid4().hex[:16].upper()}"

    for file_item in selected_files:
        doc_id = str(file_item["doc_id"])
        result_native_blob = str(file_item["native_blob"])
        result_text_blob = str(file_item["text_blob"])
        result_outline_blob = str(file_item["outline_blob"])
        pdf_name = file_item.get("pdf_name") or f"{doc_id}.pdf"

        native_ext = os.path.splitext(result_native_blob)[1] or ".pdf"
        text_ext = os.path.splitext(result_text_blob)[1] or ".txt"

        source_native_blob = f"{source_native_prefix}{safe_name(doc_id)}{native_ext}"
        source_text_blob = f"{source_text_prefix}{safe_name(doc_id)}{text_ext}"
        review_outline_blob = f"{review_outline_prefix}{safe_name(doc_id)}.json"

        try:
            if not overwrite:
                existing_paths = [
                    source_native_blob,
                    source_text_blob,
                    review_outline_blob,
                ]

                if any(
                    container.get_blob_client(path).exists()
                    for path in existing_paths
                ):
                    skipped.append(
                        {
                            "doc_id": doc_id,
                            "status": "skipped",
                            "message": "destination_exists",
                            "source_native_blob": source_native_blob,
                            "source_text_blob": source_text_blob,
                            "review_outline_blob": review_outline_blob,
                        }
                    )
                    continue

            copy_blob_within_container(
                container,
                result_native_blob,
                source_native_blob,
                overwrite=True,
            )

            copy_blob_within_container(
                container,
                result_text_blob,
                source_text_blob,
                overwrite=True,
            )

            outline_payload = read_json_blob(container, result_outline_blob)

            if outline_payload:
                outline_payload["status"] = "ready"
                outline_payload["native_blob"] = source_native_blob
                outline_payload["text_blob"] = source_text_blob
                outline_payload["outline_blob"] = review_outline_blob
                outline_payload["promoted_from_native_blob"] = result_native_blob
                outline_payload["promoted_from_text_blob"] = result_text_blob
                outline_payload["promoted_from_outline_blob"] = result_outline_blob
                outline_payload["promoted_at"] = utc_now_iso()
                outline_payload["updated_at"] = utc_now_iso()

                upload_json_blob(
                    container,
                    review_outline_blob,
                    outline_payload,
                )
            else:
                copy_blob_within_container(
                    container,
                    result_outline_blob,
                    review_outline_blob,
                    overwrite=True,
                )

            promoted.append(
                {
                    "doc_id": doc_id,
                    "status": "promoted_to_summaries_review",
                    "pdf_name": pdf_name,
                    "result_native_blob": result_native_blob,
                    "result_text_blob": result_text_blob,
                    "result_outline_blob": result_outline_blob,
                    "source_native_blob": source_native_blob,
                    "source_text_blob": source_text_blob,
                    "review_outline_blob": review_outline_blob,
                }
            )

        except Exception as exc:
            errors.append(
                {
                    "doc_id": doc_id,
                    "status": "error",
                    "message": f"promotion_failed: {type(exc).__name__}: {exc}",
                    "result_native_blob": result_native_blob,
                    "result_text_blob": result_text_blob,
                    "result_outline_blob": result_outline_blob,
                }
            )

    manifest = {
        "status": "completed" if not errors else "completed_with_errors",
        "client": client,
        "project_id": project_id,
        "promotion_id": promotion_id,
        "promote_all": promote_all,
        "requested_doc_ids": list(requested_doc_id_set),
        "promoted_count": len(promoted),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "promoted": promoted,
        "skipped": skipped,
        "errors": errors,
        "created_at": utc_now_iso(),
        "source": "summary_extraction_promotion",
        "version": 1,
    }

    manifest_blob = f"{promotion_manifest_prefix}{safe_name(promotion_id)}.json"

    try:
        upload_json_blob(container, manifest_blob, manifest)
    except Exception as exc:
        errors.append(
            {
                "doc_id": "",
                "status": "error",
                "message": f"promotion_manifest_upload_failed: {type(exc).__name__}: {exc}",
            }
        )

    return {
        "status": "ok",
        "message": f"Promoted {len(promoted)} Summary Extraction result(s) to Summaries review.",
        "client": client,
        "project_id": project_id,
        "promotion_id": promotion_id,
        "storage_account": getattr(container, "account_name", ""),
        "container": getattr(container, "container_name", ""),
        "manifest_blob": manifest_blob,
        "promoted_count": len(promoted),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "promoted": promoted,
        "skipped": skipped,
        "errors": errors,
    }

@router.post("/build-outlines")
def build_summaries_pdf_outlines(payload: dict[str, Any]):
    client = payload.get("client")
    project_id = payload.get("project_id") or payload.get("project")
    overwrite = bool(payload.get("overwrite", True))

    if not client or not project_id:
        raise HTTPException(
            status_code=400,
            detail="client and project_id are required",
        )

    try:
        container = get_summaries_review_container()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to initialize Summaries review/staging container: {type(exc).__name__}: {exc}",
        )

    base = get_project_base(client, project_id)

    native_prefix = f"{base}/source/native/"
    text_prefix = f"{base}/source/text/"
    outline_prefix = f"{base}/review/summary-outlines/"

    try:
        native_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=native_prefix)
            if not blob.name.endswith("/")
        ]

        text_blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=text_prefix)
            if not blob.name.endswith("/")
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to list Summaries files: {type(exc).__name__}: {exc}",
        )

    processed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for native_blob in native_blobs:
        doc_id = guess_doc_id_from_blob(native_blob)
        text_blob = find_matching_text_blob(text_blobs, native_blob, doc_id)

        outline_blob = f"{outline_prefix}{safe_name(doc_id)}.json"
        outline_client = container.get_blob_client(outline_blob)

        if outline_client.exists() and not overwrite:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "outline_blob": outline_blob,
                    "reason": "outline_exists",
                }
            )
            continue

        text = ""

        if text_blob:
            text = read_blob_text(container, text_blob)

        items = build_starter_outline_items(text)

        outline_payload = {
            "status": "ready",
            "client": client,
            "project_id": project_id,
            "doc_id": doc_id,
            "pdf_name": normalize_pdf_name(native_blob),
            "native_blob": native_blob,
            "text_blob": text_blob,
            "outline_blob": outline_blob,
            "item_count": len(items),
            "items": items,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "source": "summaries_processing_center",
            "version": 1,
        }

        try:
            upload_json_blob(container, outline_blob, outline_payload)
        except Exception as exc:
            skipped.append(
                {
                    "doc_id": doc_id,
                    "native_blob": native_blob,
                    "text_blob": text_blob,
                    "outline_blob": outline_blob,
                    "reason": f"upload_failed: {type(exc).__name__}: {exc}",
                }
            )
            continue

        processed.append(
            {
                "doc_id": doc_id,
                "pdf_name": normalize_pdf_name(native_blob),
                "native_blob": native_blob,
                "text_blob": text_blob,
                "outline_blob": outline_blob,
                "summary_count": len(items),
                "status": "outlined",
            }
        )

    return {
        "status": "ok",
        "message": f"Built Summaries outlines for {len(processed)} file(s).",
        "client": client,
        "project_id": project_id,
        "processed_count": len(processed),
        "skipped_count": len(skipped),
        "outlines": processed,
        "skipped": skipped,
    }