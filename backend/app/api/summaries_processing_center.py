import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

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
    return get_container_client("summaries")


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

    container = get_summaries_container()
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

    container = get_summaries_container()
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

    container = get_summaries_container()
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