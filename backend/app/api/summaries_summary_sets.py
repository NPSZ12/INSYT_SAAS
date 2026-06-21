import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/summaries/summary-sets",
    tags=["Summaries Summary Sets"],
)


WORKSPACE = "summaries"


class CreateSummarySetsRequest(BaseModel):
    client: str
    project: str
    doc_id: str
    summaries_per_set: int = Field(default=10, ge=1)
    overwrite: bool = False

class CreateSummaryExtractRequest(BaseModel):
    client: str
    project: str
    doc_id: str
    overwrite: bool = False
    max_chars_per_section: int = Field(default=2500, ge=500, le=10000)

class CheckoutSummarySetRequest(BaseModel):
    client: str
    project: str
    batch_summary_set_id: str
    username: str

class SaveQcSummaryRequest(BaseModel):
    client: str
    project: str
    batch_summary_set_id: str
    summary_id: str
    section_id: str | None = None
    title: str | None = ""
    citation: str | None = ""
    original_summary: str | None = ""
    qc_summary: str
    saved_by: str | None = ""

class ReleaseSummarySetRequest(BaseModel):
    client: str
    project: str
    batch_summary_set_id: str
    username: str
    role: str | None = ""

class SummarySetActionRequest(BaseModel):
    client: str
    project: str
    batch_summary_set_id: str
    summary_id: str
    acted_by: str | None = ""


class CompleteSummarySetRequest(BaseModel):
    client: str
    project: str
    batch_summary_set_id: str
    completed_by: str | None = ""
    allow_incomplete: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_segment(value: str | None) -> str:
    return str(value or "").strip().strip("/").replace("\\", "/")


def _project_storage_key(value: str | None) -> str:
    return _clean_segment(value).replace(" ", "_")


def _project_root(client: str, project: str) -> str:
    return f"{_clean_segment(client)}/{WORKSPACE}/{_project_storage_key(project)}"


def _live_source_account() -> str:
    return (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_ACCOUNT")
        or os.getenv("CDS_INTAKE_STORAGE_ACCOUNT")
        or "cdsintakestorage"
    )


def _live_source_container() -> str:
    return (
        os.getenv("INSYT_LIVE_SOURCE_CONTAINER_SUMMARIES")
        or os.getenv("INSYT_LIVE_SOURCE_CONTAINER")
        or os.getenv("CDS_INTAKE_CONTAINER_SUMMARIES")
        or os.getenv("CDS_INTAKE_CONTAINER")
        or "insyt-summaries"
    )


def _blob_service() -> BlobServiceClient:
    connection_string = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_INTAKE_STORAGE_CONNECTION_STRING")
        or ""
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    raise HTTPException(
        status_code=500,
        detail="Missing live source storage connection string.",
    )


def _container():
    return _blob_service().get_container_client(_live_source_container())


def _read_json_blob(blob_path: str) -> dict[str, Any]:
    blob_client = _container().get_blob_client(blob_path)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Blob not found: {blob_path}",
        )

    raw = blob_client.download_blob().readall()
    return json.loads(raw.decode("utf-8"))

def _blob_exists(blob_path: str) -> bool:
    return _container().get_blob_client(blob_path).exists()


def _read_text_blob(blob_path: str) -> str:
    blob_client = _container().get_blob_client(blob_path)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Blob not found: {blob_path}",
        )

    return blob_client.download_blob().readall().decode(
        "utf-8",
        errors="replace",
    )


def _source_text_path(client: str, project: str, doc_id: str) -> str:
    return f"{_project_root(client, project)}/source/text/{doc_id}.txt"


def _source_native_prefix(client: str, project: str) -> str:
    return f"{_project_root(client, project)}/source/native/"


def _find_source_native_path(client: str, project: str, doc_id: str) -> str:
    prefix = _source_native_prefix(client, project)

    exact_candidates = [
        f"{prefix}{doc_id}.pdf",
        f"{prefix}{doc_id}",
    ]

    for path in exact_candidates:
        if _blob_exists(path):
            return path

    matches = [
        path
        for path in _list_blobs(prefix)
        if os.path.basename(path).startswith(doc_id)
    ]

    return matches[0] if matches else ""


def _split_text_into_summary_sections(
    *,
    text: str,
    doc_id: str,
    max_chars_per_section: int,
) -> list[dict[str, Any]]:
    clean_text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    marker = "Record Summaries"
    marker_index = clean_text.lower().find(marker.lower())

    if marker_index < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                "The text does not contain the required 'Record Summaries' marker."
            ),
        )

    summaries_text = clean_text[marker_index + len(marker):].strip()

    entry_matches = list(
        re.finditer(
            r"(?m)^\s*(\d+)\s*:\s*",
            summaries_text,
        )
    )

    if not entry_matches:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                "No numbered Record Summaries were found after the 'Record Summaries' marker."
            ),
        )

    sections: list[dict[str, Any]] = []

    for match_index, match in enumerate(entry_matches):
        start = match.start()
        end = (
            entry_matches[match_index + 1].start()
            if match_index + 1 < len(entry_matches)
            else len(summaries_text)
        )

        block = summaries_text[start:end].strip()

        if not block:
            continue

        lines = [
            line.strip()
            for line in block.split("\n")
            if line.strip()
        ]

        if not lines:
            continue

        first_line = lines[0]

        date_match = re.search(
            r"\d{4}/\d{2}/\d{2}",
            first_line,
        )

        title = ""
        citation = ""
        summary_lines: list[str] = []

        if date_match:
            title = first_line[: date_match.start()].strip()
            citation = first_line[date_match.start():].strip()
            summary_lines = lines[1:]
        else:
            title = first_line.strip()

            citation_index = None

            for line_index, line in enumerate(lines[1:], start=1):
                if re.match(r"^\d{4}/\d{2}/\d{2}", line):
                    citation_index = line_index
                    break

            if citation_index is not None:
                citation = lines[citation_index].strip()
                summary_lines = lines[citation_index + 1:]
            else:
                citation = ""
                summary_lines = lines[1:]

        title = re.sub(r"\s+", " ", title).strip()
        citation = re.sub(r"\s+", " ", citation).strip()
        original_summary = " ".join(
            line.strip()
            for line in summary_lines
            if line.strip()
        )

        original_summary = re.sub(r"\s+", " ", original_summary).strip()

        if not title and not original_summary:
            continue

        summary_number = len(sections) + 1

        page_match = re.search(
            r"\bp\.\s*(\d+)",
            citation,
            flags=re.IGNORECASE,
        )

        parsed_page = int(page_match.group(1)) if page_match else None

        sections.append(
            {
                "summary_id": f"{doc_id}-SUMMARY{summary_number:09d}",
                "section_id": f"{doc_id}-SUMSEC{summary_number:09d}",
                "section_index": summary_number,
                "title": title,
                "citation": citation,
                "original_summary": original_summary,
                "qc_summary": original_summary,
                "page": parsed_page,
                "page_start": parsed_page,
                "page_end": parsed_page,
                "pdf_page": parsed_page,
                "summary_pdf_page": parsed_page,
                "status": "available",
            }
        )

    if not sections:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                "Record Summaries were found, but no usable Title / Citation / Summary sections could be parsed."
            ),
        )

    return sections


def _build_summary_extract_payload(
    *,
    client: str,
    project: str,
    doc_id: str,
    max_chars_per_section: int,
) -> dict[str, Any]:
    text_path = _source_text_path(client, project, doc_id)

    if not _blob_exists(text_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                f"Missing promoted source text at {text_path}. "
                f"Confirm the PDF was promoted and text extraction completed."
            ),
        )

    source_text = _read_text_blob(text_path)

    if not source_text.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                f"The promoted text file exists but is empty. "
                f"Run OCR or regenerate extracted text."
            ),
        )

    native_path = _find_source_native_path(client, project, doc_id)

    sections = _split_text_into_summary_sections(
        text=source_text,
        doc_id=doc_id,
        max_chars_per_section=max_chars_per_section,
    )

    if not sections:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot create Summary Extract for {doc_id}. "
                f"No usable summary sections could be generated from source text."
            ),
        )

    return {
        "workspace": WORKSPACE,
        "client": client,
        "project": project,
        "doc_id": doc_id,
        "source_pdf_name": os.path.basename(native_path) if native_path else "",
        "native_pdf_path": native_path,
        "text_path": text_path,
        "summary_extract_path": _summary_extract_path(client, project, doc_id),
        "extraction_method": "promoted_source_text_sectioned",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "text_char_count": len(source_text),
        "section_count": len(sections),
        "max_chars_per_section": max_chars_per_section,
        "sections": sections,
        "warnings": [],
    }


def _write_json_blob(
    blob_path: str,
    payload: dict[str, Any],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    data = json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode(
        "utf-8"
    )

    _container().upload_blob(
        name=blob_path,
        data=data,
        overwrite=overwrite,
        content_settings=ContentSettings(content_type="application/json"),
    )

    return {
        "storage_account": _live_source_account(),
        "container": _live_source_container(),
        "blob_path": blob_path,
        "bytes": len(data),
        "status": "uploaded",
    }


def _append_jsonl_blob(blob_path: str, event: dict[str, Any]) -> None:
    container = _container()
    blob_client = container.get_blob_client(blob_path)

    existing = ""

    if blob_client.exists():
        existing = blob_client.download_blob().readall().decode(
            "utf-8",
            errors="replace",
        )

    line = json.dumps(event, ensure_ascii=False, default=str)

    blob_client.upload_blob(
        data=(existing + line + "\n").encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/jsonl"),
    )


def _summary_extract_path(client: str, project: str, doc_id: str) -> str:
    return f"{_project_root(client, project)}/source/summary_extracts/{doc_id}.json"


def _summary_set_path(client: str, project: str, batch_summary_set_id: str) -> str:
    return (
        f"{_project_root(client, project)}/Batches/summary_sets/"
        f"{batch_summary_set_id}.json"
    )


def _summary_set_qc_path(client: str, project: str, batch_summary_set_id: str) -> str:
    return (
        f"{_project_root(client, project)}/QC/summary_sets/"
        f"{batch_summary_set_id}.json"
    )


def _summary_set_audit_path(client: str, project: str, batch_summary_set_id: str) -> str:
    return (
        f"{_project_root(client, project)}/Audit/summary_sets/"
        f"{batch_summary_set_id}.jsonl"
    )


def _new_summary_set_id(doc_id: str, index: int) -> str:
    clean_doc_id = _clean_segment(doc_id).replace("/", "_")
    return f"{clean_doc_id}-SUMSET{index:09d}"


def _normalize_summary_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    summary_id = (
        item.get("summary_id")
        or item.get("summaryId")
        or item.get("id")
        or f"summary-{index}"
    )

    section_id = (
        item.get("section_id")
        or item.get("sectionId")
        or f"SUMSEC{index:09d}"
    )

    original_summary = (
        item.get("original_summary")
        or item.get("originalSummary")
        or ""
    )

    qc_summary = (
        item.get("qc_summary")
        or item.get("qcSummary")
        or original_summary
        or ""
    )

    return {
        "summary_id": summary_id,
        "section_id": section_id,
        "section_index": item.get("section_index")
        or item.get("sectionIndex")
        or index,
        "title": item.get("title") or "",
        "citation": item.get("citation") or "",
        "original_summary": original_summary,
        "qc_summary": qc_summary,
        "page": item.get("page"),
        "page_start": item.get("page_start") or item.get("pageStart"),
        "page_end": item.get("page_end") or item.get("pageEnd"),
        "pdf_page": (
            item.get("pdf_page")
            or item.get("pdfPage")
            or item.get("summary_pdf_page")
            or item.get("summaryPdfPage")
        ),
        "status": "available",
    }


def _list_blobs(prefix: str) -> list[str]:
    return [
        blob.name
        for blob in _container().list_blobs(name_starts_with=prefix)
        if not str(blob.name).endswith("/")
        and not str(blob.name).endswith("/.keep")
    ]

@router.post("/extracts/create")
def create_summary_extract(request: CreateSummaryExtractRequest):
    extract_path = _summary_extract_path(
        request.client,
        request.project,
        request.doc_id,
    )

    if _blob_exists(extract_path) and not request.overwrite:
        existing = _read_json_blob(extract_path)

        return {
            "status": "exists",
            "workspace": WORKSPACE,
            "client": request.client,
            "project": request.project,
            "doc_id": request.doc_id,
            "summary_extract_path": extract_path,
            "section_count": len(existing.get("sections") or []),
            "text_char_count": existing.get("text_char_count"),
            "message": "Summary Extract already exists. Use overwrite=true to regenerate it.",
        }

    extract_payload = _build_summary_extract_payload(
        client=request.client,
        project=request.project,
        doc_id=request.doc_id,
        max_chars_per_section=request.max_chars_per_section,
    )

    upload = _write_json_blob(
        extract_path,
        extract_payload,
        overwrite=True,
    )

    return {
        "status": "created",
        "workspace": WORKSPACE,
        "client": request.client,
        "project": request.project,
        "doc_id": request.doc_id,
        "summary_extract_path": extract_path,
        "section_count": len(extract_payload.get("sections") or []),
        "text_char_count": extract_payload.get("text_char_count"),
        "upload": upload,
    }

@router.post("/create")
def create_summary_sets(request: CreateSummarySetsRequest):
    extract_path = _summary_extract_path(
        request.client,
        request.project,
        request.doc_id,
    )

    created_extract = False

    if not _blob_exists(extract_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Summary Extract does not exist for {request.doc_id}. "
                f"Create Summary Extracts first, then create Summary Sets. "
                f"Expected path: {extract_path}"
            ),
        )

    extract_payload = _read_json_blob(extract_path)

    raw_sections = extract_payload.get("sections") or []

    if not raw_sections:
        raise HTTPException(
            status_code=400,
            detail="No summary sections found in summary extract.",
        )

    sections = [
        _normalize_summary_item(item, index)
        for index, item in enumerate(raw_sections, start=1)
        if isinstance(item, dict)
    ]

    if not sections:
        raise HTTPException(
            status_code=400,
            detail="No valid summary sections found.",
        )

    created = []
    summaries_per_set = int(request.summaries_per_set or 10)

    for zero_index in range(0, len(sections), summaries_per_set):
        set_index = (zero_index // summaries_per_set) + 1
        batch_summary_set_id = _new_summary_set_id(request.doc_id, set_index)

        set_items = sections[zero_index: zero_index + summaries_per_set]

        set_path = _summary_set_path(
            request.client,
            request.project,
            batch_summary_set_id,
        )

        set_payload = {
            "batch_summary_set_id": batch_summary_set_id,
            "workspace": WORKSPACE,
            "client": request.client,
            "project": request.project,
            "source_doc_id": request.doc_id,
            "source_pdf_name": extract_payload.get("source_pdf_name") or "",
            "source_pdf_path": extract_payload.get("native_pdf_path") or "",
            "text_path": extract_payload.get("text_path") or "",
            "summary_start_index": zero_index + 1,
            "summary_end_index": zero_index + len(set_items),
            "summary_count": len(set_items),
            "status": "available",
            "checked_out_by": None,
            "checked_out_at": None,
            "completed_by": None,
            "completed_at": None,
            "created_at": _utc_now(),
            "items": set_items,
        }

        upload = _write_json_blob(
            set_path,
            set_payload,
            overwrite=request.overwrite,
        )

        qc_path = _summary_set_qc_path(
            request.client,
            request.project,
            batch_summary_set_id,
        )

        qc_payload = {
            "batch_summary_set_id": batch_summary_set_id,
            "workspace": WORKSPACE,
            "client": request.client,
            "project": request.project,
            "source_doc_id": request.doc_id,
            "source_pdf_name": extract_payload.get("source_pdf_name") or "",
            "source_pdf_path": extract_payload.get("native_pdf_path") or "",
            "status": "available",
            "saved_summaries": [],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }

        qc_upload = _write_json_blob(
            qc_path,
            qc_payload,
            overwrite=request.overwrite,
        )

        created.append(
            {
                "batch_summary_set_id": batch_summary_set_id,
                "summary_count": len(set_items),
                "summary_start_index": zero_index + 1,
                "summary_end_index": zero_index + len(set_items),
                "batch_path": set_path,
                "qc_path": qc_path,
                "batch_upload": upload,
                "qc_upload": qc_upload,
            }
        )

    return {
        "status": "created",
        "workspace": WORKSPACE,
        "client": request.client,
        "project": request.project,
        "doc_id": request.doc_id,
        "source_extract": extract_path,
        "created_source_extract": created_extract,
        "summaries_per_set": summaries_per_set,
        "summary_count": len(sections),
        "summary_set_count": len(created),
        "created": created,
    }


@router.get("/")
def list_summary_sets(client: str, project: str):
    prefix = f"{_project_root(client, project)}/Batches/summary_sets/"

    sets = []

    for blob_path in _list_blobs(prefix):
        try:
            payload = _read_json_blob(blob_path)
            qc_payload = {}

            try:
                qc_payload = _read_json_blob(
                    _summary_set_qc_path(
                        payload.get("client") or client,
                        payload.get("project") or project,
                        payload.get("batch_summary_set_id"),
                    )
                )
            except Exception:
                qc_payload = {}

            saved_summaries = [
                item
                for item in qc_payload.get("saved_summaries") or []
                if isinstance(item, dict) and item.get("linked", True)
            ]

            summary_count = int(payload.get("summary_count") or 0)
            saved_count = len(saved_summaries)
            pending_count = max(summary_count - saved_count, 0)

            sets.append(
                {
                    "batch_summary_set_id": payload.get("batch_summary_set_id"),
                    "source_doc_id": payload.get("source_doc_id"),
                    "source_pdf_name": payload.get("source_pdf_name"),
                    "summary_start_index": payload.get("summary_start_index"),
                    "summary_end_index": payload.get("summary_end_index"),
                    "summary_count": summary_count,
                    "saved_count": saved_count,
                    "pending_count": pending_count,
                    "available_summary_count": pending_count,
                    "status": payload.get("status"),
                    "checked_out_by": payload.get("checked_out_by"),
                    "checked_out_at": payload.get("checked_out_at"),
                    "completed_by": payload.get("completed_by"),
                    "completed_at": payload.get("completed_at"),
                    "blob_path": blob_path,
                }
            )
        except Exception:
            continue

    sets.sort(key=lambda item: item.get("batch_summary_set_id") or "")

    return {
        "status": "success",
        "workspace": WORKSPACE,
        "client": client,
        "project": project,
        "summary_sets": sets,
        "count": len(sets),
    }

@router.get("/checked-out")
def get_checked_out_summary_set(
    client: str,
    project: str,
    username: str,
):
    prefix = f"{_project_root(client, project)}/Batches/summary_sets/"

    checked_out_sets = []

    requested_user = str(username or "").strip().lower()

    for blob_path in _list_blobs(prefix):
        try:
            payload = _read_json_blob(blob_path)
        except Exception:
            continue

        status = (
            str(payload.get("status") or "")
            .lower()
            .replace("_", " ")
            .strip()
        )

        checked_out_by = str(payload.get("checked_out_by") or "").strip()
        checked_out_by_clean = checked_out_by.lower()

        if checked_out_by_clean != requested_user:
            continue

        if status not in {"checked out", "in progress"}:
            continue

        checked_out_sets.append(
            {
                "batch_summary_set_id": payload.get("batch_summary_set_id"),
                "source_doc_id": payload.get("source_doc_id"),
                "source_pdf_name": payload.get("source_pdf_name"),
                "source_pdf_path": payload.get("source_pdf_path"),
                "text_path": payload.get("text_path"),
                "summary_start_index": payload.get("summary_start_index"),
                "summary_end_index": payload.get("summary_end_index"),
                "summary_count": payload.get("summary_count"),
                "status": payload.get("status"),
                "checked_out_by": payload.get("checked_out_by"),
                "checked_out_at": payload.get("checked_out_at"),
                "completed_by": payload.get("completed_by"),
                "completed_at": payload.get("completed_at"),
                "items": payload.get("items") or [],
                "blob_path": blob_path,
            }
        )

    checked_out_sets.sort(
        key=lambda item: item.get("checked_out_at") or "",
        reverse=True,
    )

    return {
        "status": "success",
        "workspace": WORKSPACE,
        "client": client,
        "project": project,
        "username": username,
        "summary_sets": checked_out_sets,
        "count": len(checked_out_sets),
        "active_summary_set": checked_out_sets[0] if checked_out_sets else None,
    }


@router.get("/review/{batch_summary_set_id}")
def get_summary_set_for_review(
    batch_summary_set_id: str,
    client: str,
    project: str,
):
    set_payload = _read_json_blob(
        _summary_set_path(client, project, batch_summary_set_id)
    )

    qc_path = _summary_set_qc_path(client, project, batch_summary_set_id)

    try:
        qc_payload = _read_json_blob(qc_path)
    except HTTPException:
        qc_payload = {
            "batch_summary_set_id": batch_summary_set_id,
            "saved_summaries": [],
        }

    saved_by_summary_id = {
        item.get("summary_id"): item
        for item in qc_payload.get("saved_summaries") or []
        if isinstance(item, dict)
    }

    items = []

    for item in set_payload.get("items") or []:
        summary_id = item.get("summary_id")
        saved = saved_by_summary_id.get(summary_id)

        items.append(
            {
                **item,
                "saved": bool(saved and saved.get("linked", True)),
                "saved_row": saved,
            }
        )

    return {
        "status": "success",
        "batch": {
            "batch_id": batch_summary_set_id,
            "batch_name": batch_summary_set_id,
            "batch_summary_set_id": batch_summary_set_id,
            "workspace": WORKSPACE,
            "client": client,
            "project": project,
            "source_doc_id": set_payload.get("source_doc_id"),
            "source_pdf_name": set_payload.get("source_pdf_name"),
            "source_pdf_path": set_payload.get("source_pdf_path"),
            "text_path": set_payload.get("text_path"),
            "summary_start_index": set_payload.get("summary_start_index"),
            "summary_end_index": set_payload.get("summary_end_index"),
            "summary_count": set_payload.get("summary_count"),
            "status": set_payload.get("status"),
            "checked_out_by": set_payload.get("checked_out_by"),
            "checked_out_at": set_payload.get("checked_out_at"),
            "items": items,
        },
        "summary_set": {
            **set_payload,
            "items": items,
        },
        "qc": qc_payload,
    }
    

@router.get("/{batch_summary_set_id}")
def get_summary_set(
    batch_summary_set_id: str,
    client: str,
    project: str,
):
    set_payload = _read_json_blob(
        _summary_set_path(client, project, batch_summary_set_id)
    )

    qc_path = _summary_set_qc_path(client, project, batch_summary_set_id)

    try:
        qc_payload = _read_json_blob(qc_path)
    except HTTPException:
        qc_payload = {
            "batch_summary_set_id": batch_summary_set_id,
            "saved_summaries": [],
        }

    saved_by_summary_id = {
        item.get("summary_id"): item
        for item in qc_payload.get("saved_summaries") or []
        if isinstance(item, dict)
    }

    merged_items = []

    for item in set_payload.get("items") or []:
        summary_id = item.get("summary_id")
        saved = saved_by_summary_id.get(summary_id)

        merged_items.append(
            {
                **item,
                "saved": bool(saved and saved.get("linked", True)),
                "saved_row": saved,
            }
        )

    return {
        "status": "success",
        "summary_set": {
            **set_payload,
            "items": merged_items,
        },
        "qc": qc_payload,
    }


@router.post("/save")
def save_qc_summary(request: SaveQcSummaryRequest):
    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    set_path = _summary_set_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    set_payload = _read_json_blob(set_path)

    try:
        qc_payload = _read_json_blob(qc_path)
    except HTTPException:
        qc_payload = {
            "batch_summary_set_id": request.batch_summary_set_id,
            "workspace": WORKSPACE,
            "client": request.client,
            "project": request.project,
            "source_doc_id": set_payload.get("source_doc_id"),
            "source_pdf_name": set_payload.get("source_pdf_name"),
            "source_pdf_path": set_payload.get("source_pdf_path"),
            "status": "in_progress",
            "saved_summaries": [],
            "created_at": _utc_now(),
        }

    saved_summaries = qc_payload.get("saved_summaries") or []

    now = _utc_now()

    saved_row = {
        "link_id": f"SUMLINK-{uuid.uuid4().hex[:12].upper()}",
        "batch_summary_set_id": request.batch_summary_set_id,
        "source_doc_id": set_payload.get("source_doc_id"),
        "summary_id": request.summary_id,
        "section_id": request.section_id or "",
        "title": request.title or "",
        "citation": request.citation or "",
        "original_summary": request.original_summary or "",
        "qc_summary": request.qc_summary,
        "linked": True,
        "status": "saved",
        "saved_by": request.saved_by or "",
        "saved_at": now,
        "updated_at": now,
    }

    replaced = False

    for index, item in enumerate(saved_summaries):
        if (
            item.get("summary_id") == request.summary_id
            and item.get("batch_summary_set_id") == request.batch_summary_set_id
        ):
            saved_row["link_id"] = item.get("link_id") or saved_row["link_id"]
            saved_row["created_at"] = item.get("created_at") or item.get("saved_at")
            saved_summaries[index] = saved_row
            replaced = True
            break

    if not replaced:
        saved_row["created_at"] = now
        saved_summaries.append(saved_row)

    qc_payload["saved_summaries"] = saved_summaries
    qc_payload["status"] = "in_progress"
    qc_payload["updated_at"] = now

    upload = _write_json_blob(qc_path, qc_payload, overwrite=True)

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": "save_qc_summary",
            "at": now,
            "batch_summary_set_id": request.batch_summary_set_id,
            "summary_id": request.summary_id,
            "section_id": request.section_id,
            "saved_by": request.saved_by,
        },
    )

    return {
        "status": "saved",
        "saved_row": saved_row,
        "qc_path": qc_path,
        "upload": upload,
    }


@router.post("/unlink")
def unlink_qc_summary(request: SummarySetActionRequest):
    return _update_saved_summary_link_state(
        request=request,
        linked=False,
        status="unlinked",
        event_name="unlink_qc_summary",
    )


@router.post("/delete")
def delete_qc_summary(request: SummarySetActionRequest):
    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    qc_payload = _read_json_blob(qc_path)

    before = len(qc_payload.get("saved_summaries") or [])

    qc_payload["saved_summaries"] = [
        item
        for item in qc_payload.get("saved_summaries") or []
        if item.get("summary_id") != request.summary_id
    ]

    after = len(qc_payload.get("saved_summaries") or [])
    qc_payload["updated_at"] = _utc_now()

    upload = _write_json_blob(qc_path, qc_payload, overwrite=True)

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": "delete_qc_summary",
            "at": _utc_now(),
            "batch_summary_set_id": request.batch_summary_set_id,
            "summary_id": request.summary_id,
            "acted_by": request.acted_by,
            "deleted_count": before - after,
        },
    )

    return {
        "status": "deleted",
        "deleted_count": before - after,
        "qc_path": qc_path,
        "upload": upload,
    }


def _update_saved_summary_link_state(
    *,
    request: SummarySetActionRequest,
    linked: bool,
    status: str,
    event_name: str,
):
    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    qc_payload = _read_json_blob(qc_path)

    updated = None

    for item in qc_payload.get("saved_summaries") or []:
        if item.get("summary_id") == request.summary_id:
            item["linked"] = linked
            item["status"] = status
            item["updated_at"] = _utc_now()
            item["acted_by"] = request.acted_by or ""
            updated = item
            break

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Saved summary row not found.",
        )

    qc_payload["updated_at"] = _utc_now()

    upload = _write_json_blob(qc_path, qc_payload, overwrite=True)

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": event_name,
            "at": _utc_now(),
            "batch_summary_set_id": request.batch_summary_set_id,
            "summary_id": request.summary_id,
            "acted_by": request.acted_by,
        },
    )

    return {
        "status": status,
        "saved_row": updated,
        "qc_path": qc_path,
        "upload": upload,
    }

@router.post("/checkout")
def checkout_summary_set(request: CheckoutSummarySetRequest):
    set_path = _summary_set_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    set_payload = _read_json_blob(set_path)

    status = str(set_payload.get("status") or "available").lower()
    checked_out_by = set_payload.get("checked_out_by")

    if checked_out_by and checked_out_by != request.username:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUMMARY_SET_ALREADY_CHECKED_OUT",
                "message": (
                    f"Summary Set {request.batch_summary_set_id} is already "
                    f"checked out by {checked_out_by}."
                ),
            },
        )

    if status == "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUMMARY_SET_ALREADY_COMPLETED",
                "message": (
                    f"Summary Set {request.batch_summary_set_id} is already completed."
                ),
            },
        )

    now = _utc_now()

    set_payload["status"] = "checked_out"
    set_payload["checked_out_by"] = request.username
    set_payload["checked_out_at"] = now
    set_payload["updated_at"] = now

    set_upload = _write_json_blob(set_path, set_payload, overwrite=True)

    try:
        qc_payload = _read_json_blob(qc_path)
    except HTTPException:
        qc_payload = {
            "batch_summary_set_id": request.batch_summary_set_id,
            "workspace": WORKSPACE,
            "client": request.client,
            "project": request.project,
            "source_doc_id": set_payload.get("source_doc_id"),
            "source_pdf_name": set_payload.get("source_pdf_name"),
            "source_pdf_path": set_payload.get("source_pdf_path"),
            "status": "checked_out",
            "saved_summaries": [],
            "created_at": now,
        }

    qc_payload["status"] = "checked_out"
    qc_payload["checked_out_by"] = request.username
    qc_payload["checked_out_at"] = now
    qc_payload["updated_at"] = now

    qc_upload = _write_json_blob(qc_path, qc_payload, overwrite=True)

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": "checkout_summary_set",
            "at": now,
            "batch_summary_set_id": request.batch_summary_set_id,
            "checked_out_by": request.username,
        },
    )

    return {
        "status": "checked_out",
        "message": "Summary Set checked out.",
        "batch_summary_set_id": request.batch_summary_set_id,
        "checked_out_by": request.username,
        "checked_out_at": now,
        "set_upload": set_upload,
        "qc_upload": qc_upload,
    }

@router.post("/release")
def release_summary_set(request: ReleaseSummarySetRequest):
    set_path = _summary_set_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    set_payload = _read_json_blob(set_path)

    checked_out_by = set_payload.get("checked_out_by")

    leadership_roles = {
        "RM",
        "Admin",
        "CDS Admin",
        "INSYT Admin",
    }

    can_release = (
        not checked_out_by
        or checked_out_by == request.username
        or request.role in leadership_roles
    )

    if not can_release:
        raise HTTPException(
            status_code=403,
            detail="Only the checked-out reviewer or leadership can release this Summary Set.",
        )

    now = _utc_now()

    set_payload["status"] = "available"
    set_payload["checked_out_by"] = None
    set_payload["checked_out_at"] = None
    set_payload["updated_at"] = now

    set_upload = _write_json_blob(set_path, set_payload, overwrite=True)

    try:
        qc_payload = _read_json_blob(qc_path)
        qc_payload["status"] = "available"
        qc_payload["checked_out_by"] = None
        qc_payload["checked_out_at"] = None
        qc_payload["updated_at"] = now
        qc_upload = _write_json_blob(qc_path, qc_payload, overwrite=True)
    except HTTPException:
        qc_upload = None

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": "release_summary_set",
            "at": now,
            "batch_summary_set_id": request.batch_summary_set_id,
            "released_by": request.username,
        },
    )

    return {
        "status": "available",
        "message": "Summary Set released.",
        "batch_summary_set_id": request.batch_summary_set_id,
        "set_upload": set_upload,
        "qc_upload": qc_upload,
    }

@router.post("/complete")
def complete_summary_set(request: CompleteSummarySetRequest):
    set_path = _summary_set_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    qc_path = _summary_set_qc_path(
        request.client,
        request.project,
        request.batch_summary_set_id,
    )

    set_payload = _read_json_blob(set_path)
    qc_payload = _read_json_blob(qc_path)

    assigned_summary_ids = {
        item.get("summary_id")
        for item in set_payload.get("items") or []
        if item.get("summary_id")
    }

    saved_summary_ids = {
        item.get("summary_id")
        for item in qc_payload.get("saved_summaries") or []
        if item.get("summary_id") and item.get("linked", True)
    }

    missing = sorted(assigned_summary_ids - saved_summary_ids)

    if missing and not request.allow_incomplete:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Summary Set has unsaved summaries.",
                "missing_summary_ids": missing,
            },
        )

    now = _utc_now()

    set_payload["status"] = "completed"
    set_payload["completed_by"] = request.completed_by or ""
    set_payload["completed_at"] = now

    qc_payload["status"] = "completed"
    qc_payload["completed_by"] = request.completed_by or ""
    qc_payload["completed_at"] = now
    qc_payload["updated_at"] = now

    set_upload = _write_json_blob(set_path, set_payload, overwrite=True)
    qc_upload = _write_json_blob(qc_path, qc_payload, overwrite=True)

    _append_jsonl_blob(
        _summary_set_audit_path(
            request.client,
            request.project,
            request.batch_summary_set_id,
        ),
        {
            "event": "complete_summary_set",
            "at": now,
            "batch_summary_set_id": request.batch_summary_set_id,
            "completed_by": request.completed_by,
            "allow_incomplete": request.allow_incomplete,
            "missing_summary_ids": missing,
        },
    )

    return {
        "status": "completed",
        "batch_summary_set_id": request.batch_summary_set_id,
        "missing_summary_ids": missing,
        "set_upload": set_upload,
        "qc_upload": qc_upload,
    }