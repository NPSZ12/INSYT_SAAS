from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_service import get_container_client
from app.services.pdf_text_service import (
    get_text_blob_path,
    get_metadata_blob_path,
    extract_pdf_text_from_bytes,
)
from app.services.summary_outline_service import parse_summary_outline


router = APIRouter(
    prefix="/api/summaries/text",
    tags=["summaries-text"],
)


class ExtractTextRequest(BaseModel):
    project_id: str
    source_blob_path: str


@router.get("/status")
def get_text_status(
    source_blob_path: str,
):
    container = get_container_client("summaries")

    text_blob_path = get_text_blob_path(source_blob_path)
    metadata_blob_path = get_metadata_blob_path(text_blob_path)

    text_blob = container.get_blob_client(text_blob_path)
    metadata_blob = container.get_blob_client(metadata_blob_path)

    return {
        "source_blob_path": source_blob_path,
        "text_blob_path": text_blob_path,
        "metadata_blob_path": metadata_blob_path,
        "text_exists": text_blob.exists(),
        "metadata_exists": metadata_blob.exists(),
        "status": "complete" if text_blob.exists() else "missing",
    }


@router.post("/extract")
def extract_text(
    payload: ExtractTextRequest,
):
    container = get_container_client("summaries")

    source_blob_path = payload.source_blob_path.strip("/")
    text_blob_path = get_text_blob_path(source_blob_path)
    metadata_blob_path = get_metadata_blob_path(text_blob_path)

    text_blob = container.get_blob_client(text_blob_path)

    if text_blob.exists():
        return {
            "status": "complete",
            "created": False,
            "source_blob_path": source_blob_path,
            "text_blob_path": text_blob_path,
            "metadata_blob_path": metadata_blob_path,
        }

    source_blob = container.get_blob_client(source_blob_path)

    if not source_blob.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source PDF not found: {source_blob_path}",
        )

    pdf_bytes = source_blob.download_blob().readall()
    text = extract_pdf_text_from_bytes(pdf_bytes)

    text_blob.upload_blob(
        text.encode("utf-8"),
        overwrite=True,
        content_type="text/plain; charset=utf-8",
    )

    metadata_blob = container.get_blob_client(metadata_blob_path)
    metadata_blob.upload_blob(
        (
            "{\n"
            f'  "source_blob_path": "{source_blob_path}",\n'
            f'  "text_blob_path": "{text_blob_path}",\n'
            f'  "metadata_blob_path": "{metadata_blob_path}",\n'
            '  "extraction_method": "pypdf"\n'
            "}\n"
        ).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )

    return {
        "status": "complete",
        "created": True,
        "source_blob_path": source_blob_path,
        "text_blob_path": text_blob_path,
        "metadata_blob_path": metadata_blob_path,
        "text_length": len(text),
    }


@router.get("/content")
def get_text_content(
    source_blob_path: str,
    max_chars: int = 200000,
):
    container = get_container_client("summaries")

    text_blob_path = get_text_blob_path(source_blob_path)
    text_blob = container.get_blob_client(text_blob_path)

    if not text_blob.exists():
        return {
            "status": "missing",
            "source_blob_path": source_blob_path,
            "text_blob_path": text_blob_path,
            "text": "",
            "outline_items": [],
        }

    text = text_blob.download_blob().readall().decode(
        "utf-8",
        errors="replace",
    )

    outline_items = parse_summary_outline(text)

    return {
        "status": "complete",
        "source_blob_path": source_blob_path,
        "text_blob_path": text_blob_path,
        "text": text[:max_chars],
        "text_length": len(text),
        "text_truncated": len(text) > max_chars,
        "outline_items": outline_items,
    }