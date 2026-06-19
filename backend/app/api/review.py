import json
import os
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel


from app.services.batch_service import get_container_client
from app.services.protocol_service import load_protocol_fields
from app.services.project_store import CAPTURED_ENTITIES
from app.services.batch_service import get_container_client
from app.services.summary_outline_service import parse_summary_outline
from app.services.pdf_text_service import get_text_blob_path
from app.services.storage_paths import build_project_base_path, build_project_path


from datetime import datetime, timedelta, timezone
from uuid import uuid4

from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions,
)


router = APIRouter(prefix="/api", tags=["Review"])


VALID_WORKSPACES = ["capture", "summaries", "discovery"]

def get_source_container_name(workspace: str) -> str:
    workspace_clean = str(workspace or "").lower().strip()

    if workspace_clean == "capture":
        return os.getenv("AZURE_CAPTURE_CONTAINER", "insyt-capture")

    if workspace_clean == "summaries":
        return os.getenv("AZURE_SUMMARIES_CONTAINER", "insyt-summaries")

    if workspace_clean == "discovery":
        return os.getenv("AZURE_DISCOVERY_CONTAINER", "insyt-discovery")

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported workspace: {workspace}",
    )


def get_source_container_client(workspace: str):
    workspace_clean = str(workspace or "").lower().strip()

    if workspace_clean not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    connection_string = (
        os.getenv("INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING")
        or os.getenv("CDS_STORAGE_CONNECTION_STRING")
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail=(
                "Live source storage is not configured. Set "
                "INSYT_LIVE_SOURCE_STORAGE_CONNECTION_STRING, "
                "CDS_STORAGE_CONNECTION_STRING, or "
                "AZURE_STORAGE_CONNECTION_STRING."
            ),
        )

    service = BlobServiceClient.from_connection_string(connection_string)

    return service.get_container_client(
        get_source_container_name(workspace_clean)
    )


def get_source_blob_url(
    workspace: str,
    blob_path: str,
):
    if not blob_path:
        return ""

    container = get_source_container_client(workspace)

    blob_client = container.get_blob_client(blob_path)

    account_name = container.account_name

    account_key = (
        container.credential.account_key
        if hasattr(container.credential, "account_key")
        else container.credential
    )

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container.container_name,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=4),
    )

    return f"{blob_client.url}?{sas_token}"

def list_workspace_project_files(
    workspace: str,
    project_id: str,
    client_id: str = "",
):
    container = get_source_container_client(workspace)

    clean_project_id = project_id.strip("/")
    clean_client_id = client_id.strip("/")

    if clean_client_id:
        prefix = f"{build_project_base_path(workspace, clean_client_id, clean_project_id)}/"
    else:
        prefix = f"{workspace.strip('/')}/{clean_project_id}/"

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        name = blob.name.split("/")[-1]

        if not name:
            continue

        files.append(
            {
                "name": name,
                "path": blob.name,
                "size": getattr(blob, "size", 0),
            }
        )

    return files


def read_workspace_blob_text(workspace: str, blob_path: str):
    container = get_container_client(workspace)
    blob_client = container.get_blob_client(blob_path)

    return blob_client.download_blob().readall().decode(
        "utf-8",
        errors="replace",
    )


from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions,
)


def get_workspace_blob_url(
    workspace: str,
    blob_path: str,
):
    if not blob_path:
        return ""

    container = get_container_client(workspace)

    blob_client = container.get_blob_client(blob_path)

    account_name = container.account_name

    account_key = (
        container.credential.account_key
        if hasattr(container.credential, "account_key")
        else container.credential
    )

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container.container_name,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc)
        + timedelta(hours=4),
    )

    return f"{blob_client.url}?{sas_token}"

SUPPORTED_REVIEW_EXTENSIONS = (
    ".pdf",
    ".txt",
    ".docx",
    ".doc",
    ".rtf",
    ".odt",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".csv",
    ".dat",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
    ".ppt",
    ".pptx",
    ".msg",
    ".eml",
)


def get_extension(file_name: str) -> str:
    if "." not in str(file_name or ""):
        return ""

    return "." + str(file_name).rsplit(".", 1)[-1].lower().strip()


def determine_viewer_type(file_name: str, text_exists: bool = False) -> str:
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
        ".dat",
    ]:
        return "text"

    if extension in [
        ".doc",
        ".docx",
        ".rtf",
        ".odt",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".ppt",
        ".pptx",
    ]:
        return "needs_preview_conversion"

    if extension in [".msg", ".eml"]:
        return "email"

    if text_exists:
        return "text"

    return "unsupported"


def source_preview_pdf_path(native_blob: str, doc_id: str) -> str:
    if "/source/native/" in native_blob:
        base = native_blob.split("/source/native/")[0]
        return f"{base}/source/preview/{doc_id}.pdf"

    return ""


def source_preview_html_path(native_blob: str, doc_id: str) -> str:
    if "/source/native/" in native_blob:
        base = native_blob.split("/source/native/")[0]
        return f"{base}/source/preview/{doc_id}.html"

    return ""


def normalize_doc_id(value: str) -> str:
    name = str(value or "").strip().split("/")[-1]

    if "." in name:
        name = name.rsplit(".", 1)[0]

    return name.strip().lower()


def get_batch_blob_name(
    workspace: str,
    client: str,
    project_id: str,
    batch: str,
) -> str:
    if client:
        return build_project_path(
            workspace,
            client,
            project_id,
            "Batches",
            f"{batch}.json",
        )

    return build_project_path(
        workspace,
        "",
        project_id,
        "Batches",
        f"{batch}.json",
    )


def load_batch_payload(
    workspace: str,
    client: str,
    project_id: str,
    batch: str,
):
    container = get_container_client(workspace)

    batch_blob_name = get_batch_blob_name(
        workspace=workspace,
        client=client,
        project_id=project_id,
        batch=batch,
    )

    blob_client = container.get_blob_client(batch_blob_name)

    if not blob_client.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Batch not found: {batch_blob_name}",
        )

    payload = json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )

    doc_ids = [
        str(doc_id).strip()
        for doc_id in payload.get("doc_ids", [])
        if str(doc_id).strip()
    ]

    if not doc_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Batch {batch} has no assigned documents.",
        )

    return payload, doc_ids


def get_project_files_for_review(
    workspace: str,
    project_id: str,
    client: str,
):
    try:
        return list_workspace_project_files(
            workspace,
            project_id,
            client,
        )
    except TypeError:
        return list_workspace_project_files(
            workspace,
            project_id,
        )


def find_native_file_for_doc(
    files: list[dict],
    doc_id: str,
):
    requested = normalize_doc_id(doc_id)

    native_files = [
        file for file in files
        if "/source/native/" in f"/{str(file.get('path', '')).lower()}"
        and str(file.get("name", "")).lower().endswith(
            SUPPORTED_REVIEW_EXTENSIONS
        )
    ]

    for file in native_files:
        file_name = str(file.get("name", "")).split("/")[-1]
        file_base = normalize_doc_id(file_name)
        blob_base = normalize_doc_id(str(file.get("path", "")))

        if file_base == requested or blob_base == requested:
            return file

    return None


def resolve_text_blob_path(native_blob: str) -> str:
    if native_blob.lower().endswith(".txt"):
        return native_blob

    try:
        return get_text_blob_path(native_blob)
    except Exception:
        base_path, file_name = native_blob.rsplit("/", 1)
        doc_id = file_name.rsplit(".", 1)[0]

        if "/source/native" in base_path:
            text_base = base_path.replace("/source/native", "/source/text")
            return f"{text_base}/{doc_id}.txt"

        return f"{base_path}/{doc_id}.txt"

def normalize_doc_lookup(value: str) -> str:
    clean = str(value or "").strip()
    clean = clean.split("/")[-1]
    clean = clean.rsplit(".", 1)[0]
    return clean.replace("_", " ").lower()


def project_base_path(
    workspace: str,
    client: str,
    project: str,
) -> str:
    client = str(client or "").strip().strip("/")
    project = str(project or "").strip().strip("/")
    workspace = str(workspace or "").strip().strip("/")

    if client:
        return build_project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )

    return f"{workspace}/{project}"

def get_document_review_blob_name(
    workspace: str,
    client: str,
    project_id: str,
    doc_id: str,
) -> str:
    base_path = project_base_path(
        workspace,
        client,
        project_id,
    )
    clean_doc_id = str(doc_id or "").strip().split("/")[-1]

    if "." in clean_doc_id:
        clean_doc_id = clean_doc_id.rsplit(".", 1)[0]

    return f"{base_path}/Review/documents/{clean_doc_id}.json"


def load_document_review_state(
    workspace: str,
    client: str,
    project_id: str,
    doc_id: str,
) -> dict:
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
        workspace,
        client,
        project_id,
        doc_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if not blob_client.exists():
        return {}

    return json.loads(
        blob_client.download_blob()
        .readall()
        .decode("utf-8")
    )


def save_document_review_state(
    workspace: str,
    client: str,
    project_id: str,
    batch_id: str,
    doc_id: str,
    document_coding: str,
    further_review_reason: str,
    qc_coding: str = "",
    qc_questions: str = "",
    values: dict = {},
    reviewed_by: str = "",
    action: str = "save",
) -> dict:
    container = get_container_client(workspace)

    blob_name = get_document_review_blob_name(
        workspace,
        client,
        project_id,
        doc_id,
    )

    blob_client = container.get_blob_client(blob_name)

    if blob_client.exists():
        state = json.loads(
            blob_client.download_blob()
            .readall()
            .decode("utf-8")
        )
    else:
        state = {
            "workspace": workspace,
            "client_id": client,
            "project_id": project_id,
            "doc_id": doc_id,
            "review_history": [],
            "linked_entities": [],
        }

    now = datetime.now(timezone.utc).isoformat()

    if document_coding:
        state["document_coding"] = document_coding

    state["further_review_reason"] = further_review_reason or ""
    state["qc_coding"] = qc_coding or ""
    state["qc_questions"] = qc_questions or ""
    state["last_batch_id"] = batch_id or ""
    state["last_reviewed_by"] = reviewed_by
    state["last_reviewed_at"] = now

    has_values = any(
        value is not None and str(value).strip() != ""
        for value in values.values()
    )

    if has_values:
        state["values"] = values

        state.setdefault("linked_entities", []).append(
            {
                "ucid": f"UCID-{uuid4().hex}",
                "batch_id": batch_id or "",
                "linked_by": reviewed_by,
                "linked_at": now,
                "source": "manual_review",
                "values": values,
            }
        )

    state.setdefault("review_history", []).append(
        {
            "batch_id": batch_id or "",
            "reviewed_by": reviewed_by,
            "reviewed_at": now,
            "action": action,
            "document_coding": document_coding,
            "further_review_reason": further_review_reason or "",
            "qc_coding": qc_coding or "",
            "qc_questions": qc_questions or "",
        }
    )

    blob_client.upload_blob(
        json.dumps(state, indent=2),
        overwrite=True,
    )

    return state

def load_review_document_by_doc_id(
    workspace: str,
    client: str,
    project: str,
    doc_id: str,
    native_blob: str = "",
):
    source_container = get_source_container_client(workspace)

    requested = normalize_doc_lookup(doc_id)

    project_variants = []
    for value in [
        project,
        project.replace(" ", "_"),
    ]:
        clean_value = str(value or "").strip()
        if clean_value and clean_value not in project_variants:
            project_variants.append(clean_value)

    base_paths = []

    for project_variant in project_variants:
        if client:
            base_paths.append(
                build_project_base_path(
                    workspace,
                    client,
                    project_variant,
                )
            )
        else:
            base_paths.append(f"{workspace}/{project_variant}")

    native_prefixes = [
        f"{base_path}/source/native/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/natives/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/native_docs/"
        for base_path in base_paths
    ]

    text_prefixes = [
        f"{base_path}/source/text/"
        for base_path in base_paths
    ] + [
        f"{base_path}/source/texts/"
        for base_path in base_paths
    ]

    matched_native = ""
    matched_doc_id = (
        str(doc_id or "")
        .strip()
        .split("/")[-1]
        .rsplit(".", 1)[0]
    )

    clean_native_blob = unquote(
        str(native_blob or "")
        .strip()
        .strip("/")
    )

    # Support accidental full Azure URLs by trimming to the project-relative path
    # when the native blob is passed as a URL instead of a blob name.
    if "/source/native/" in clean_native_blob and "://" in clean_native_blob:
        marker = "/source/native/"
        before, after = clean_native_blob.split(marker, 1)

        path_parts = before.split("/")
        if len(path_parts) >= 3:
            client_part = path_parts[-3]
            workspace_part = path_parts[-2]
            project_part = path_parts[-1]

            clean_native_blob = (
                f"{client_part}/"
                f"{workspace_part}/"
                f"{project_part}"
                f"{marker}"
                f"{after}"
            )

    if clean_native_blob:
        allowed_native_path = any(
            clean_native_blob.startswith(prefix)
            for prefix in native_prefixes
        )

        supported_native_type = clean_native_blob.lower().endswith(
            SUPPORTED_REVIEW_EXTENSIONS
        )

        if allowed_native_path and supported_native_type:
            native_blob_client = source_container.get_blob_client(
                clean_native_blob
            )

            if native_blob_client.exists():
                matched_native = clean_native_blob

    if not matched_native:
        for native_prefix in native_prefixes:
            for blob in source_container.list_blobs(
                name_starts_with=native_prefix
            ):
                filename = blob.name.split("/")[-1]

                if not filename or filename == ".keep":
                    continue

                if not filename.lower().endswith(
                    SUPPORTED_REVIEW_EXTENSIONS
                ):
                    continue

                if normalize_doc_lookup(filename) == requested:
                    matched_native = blob.name
                    matched_doc_id = filename.rsplit(".", 1)[0]
                    break

            if matched_native:
                break

    if not matched_native:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found in source/native: {doc_id}",
        )

    matched_text = ""

    native_file_name = matched_native.split("/")[-1]
    native_stem = native_file_name.rsplit(".", 1)[0]

    candidate_text_paths = []

    try:
        candidate_text_paths.append(
            resolve_text_blob_path(matched_native)
        )
    except Exception:
        pass

    for text_prefix in text_prefixes:
        candidate_text_paths.extend(
            [
                f"{text_prefix}{matched_doc_id}.txt",
                f"{text_prefix}{native_stem}.txt",
                f"{text_prefix}{doc_id}.txt",
            ]
        )

    seen_candidates = set()

    for candidate_text_path in candidate_text_paths:
        clean_candidate = str(candidate_text_path or "").strip()

        if not clean_candidate or clean_candidate in seen_candidates:
            continue

        seen_candidates.add(clean_candidate)

        text_blob_client = source_container.get_blob_client(clean_candidate)

        if text_blob_client.exists():
            matched_text = clean_candidate
            break

    if not matched_text:
        accepted_text_names = {
            requested,
            normalize_doc_lookup(matched_doc_id),
            normalize_doc_lookup(native_stem),
        }

        for text_prefix in text_prefixes:
            for blob in source_container.list_blobs(
                name_starts_with=text_prefix
            ):
                filename = blob.name.split("/")[-1]

                if not filename or filename == ".keep":
                    continue

                if normalize_doc_lookup(filename) in accepted_text_names:
                    matched_text = blob.name
                    break

            if matched_text:
                break

    text = ""
    outline_items = []

    if matched_text:
        text = (
            source_container
            .get_blob_client(matched_text)
            .download_blob()
            .readall()
            .decode("utf-8", errors="replace")
        )

        try:
            outline_items = parse_summary_outline(text)
        except Exception:
            outline_items = []

    native_url = get_source_blob_url(
        workspace,
        matched_native,
    )

    review_state = load_document_review_state(
        workspace=workspace,
        client=client,
        project_id=project,
        doc_id=matched_doc_id,
    )

    return {
        "workspace": workspace,
        "project": project.replace("_", " "),
        "project_id": project,
        "batch": "Direct Open",
        "doc_id": matched_doc_id,
        "document_coding": review_state.get("document_coding", ""),
        "further_review_reason": review_state.get("further_review_reason", ""),
        "review_state": review_state,
        "blob_name": matched_text,
        "text": text[:200000],
        "text_truncated": len(text) > 200000,
        "text_length": len(text),
        "outline_items": outline_items,
        "text_blob": matched_text,
        "text_exists": bool(matched_text),
        "native_url": native_url,
        "native_blob": matched_native,
    }

def load_current_review_document(
    workspace: str,
    project: str,
    batch: str,
    client: str = "",
    doc: str = "",
    native_blob: str = "",
):
    if doc and not batch:
        return load_review_document_by_doc_id(
            workspace=workspace,
            client=client,
            project=project,
            doc_id=doc,
            native_blob=native_blob,
        )

    # existing batch-based logic continues below
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    project_id = project

    protocol_fields = load_protocol_fields(project_id)

    batch_payload, batch_doc_ids = load_batch_payload(
        workspace=workspace,
        client=client,
        project_id=project_id,
        batch=batch,
    )

    reviewed_doc_ids = batch_payload.get("reviewed_doc_ids", [])

    if doc:
        target_doc_id = doc.strip()
    else:
        target_doc_id = next(
            (
                doc_id
                for doc_id in batch_doc_ids
                if doc_id not in reviewed_doc_ids
            ),
            batch_doc_ids[0],
        )

    normalized_batch_doc_ids = {
        normalize_doc_id(doc_id): doc_id
        for doc_id in batch_doc_ids
    }

    normalized_target = normalize_doc_id(target_doc_id)

    if normalized_target not in normalized_batch_doc_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested document {target_doc_id} is not assigned "
                f"to batch {batch}."
            ),
        )

    target_doc_id = normalized_batch_doc_ids[normalized_target]

    files = get_project_files_for_review(
        workspace=workspace,
        project_id=project_id,
        client=client,
    )

    native_file = find_native_file_for_doc(
        files=files,
        doc_id=target_doc_id,
    )

    if not native_file:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Native file not found for batch document: {target_doc_id}"
            ),
        )

    native_blob = native_file["path"]
    text_blob_path = resolve_text_blob_path(native_blob)

    source_container = get_source_container_client(workspace)
    text_blob = source_container.get_blob_client(text_blob_path)

    text_exists = text_blob.exists()
    text = ""
    outline_items = []

    if text_exists:
        text = text_blob.download_blob().readall().decode(
            "utf-8",
            errors="replace",
        )

        try:
            outline_items = parse_summary_outline(text)
        except Exception:
            outline_items = []

    current_index = batch_doc_ids.index(target_doc_id)

    previous_doc_id = (
        batch_doc_ids[current_index - 1]
        if current_index > 0
        else ""
    )

    next_doc_id = (
        batch_doc_ids[current_index + 1]
        if current_index < len(batch_doc_ids) - 1
        else ""
    )
    
    review_state = load_document_review_state(
        workspace=workspace,
        client=client,
        project_id=project_id,
        doc_id=target_doc_id,
    )

    return {
        "workspace": workspace,
        "project": project_id.replace("_", " "),
        "project_id": project_id,
        "batch": batch,
        "doc_id": target_doc_id,
        "document_coding": review_state.get("document_coding", ""),
        "further_review_reason": review_state.get("further_review_reason", ""),
        "review_state": review_state,
        "blob_name": text_blob_path,
        "fields": protocol_fields,
        "native_url": get_source_blob_url(workspace, native_blob),
        "native_blob": native_blob,
        "text": text[:200000],
        "text_truncated": len(text) > 200000,
        "text_length": len(text),
        "outline_items": outline_items,
        "text_blob": text_blob_path,
        "text_exists": text_exists,
        "batch_doc_ids": batch_doc_ids,
        "batch_doc_index": current_index,
        "batch_doc_count": len(batch_doc_ids),
        "previous_doc_id": previous_doc_id,
        "next_doc_id": next_doc_id,
        "is_first_doc": current_index == 0,
        "is_last_doc": current_index == len(batch_doc_ids) - 1,
    }


@router.get("/review/current")
def get_current_review_document_compat(
    project: str,
    batch: str = "",
    client: str = "",
    doc: str = "",
    native_blob: str = "",
    blob_path: str = "",
):
    try:
        return load_current_review_document(
            workspace="capture",
            client=client,
            project=project,
            batch=batch,
            doc=doc,
            native_blob=native_blob or blob_path,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )

@router.get("/{workspace}/review/preview")
def get_workspace_review_preview(
    workspace: str,
    project: str,
    client: str = "",
    doc: str = "",
    native_blob: str = "",
    blob_path: str = "",
):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace.",
        )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not doc:
        raise HTTPException(
            status_code=400,
            detail="Document id is required.",
        )

    document = load_review_document_by_doc_id(
        workspace=workspace,
        client=client,
        project=project,
        doc_id=doc,
        native_blob=native_blob or blob_path,
    )

    native_blob = document.get("native_blob", "")
    text_blob = document.get("blob_name", "")
    doc_id = document.get("doc_id", doc)

    file_name = native_blob.split("/")[-1] if native_blob else doc_id
    extension = get_extension(file_name)

    text_exists = bool(text_blob)
    viewer_type = determine_viewer_type(
        file_name=file_name,
        text_exists=text_exists,
    )

    preview_pdf = source_preview_pdf_path(native_blob, doc_id)
    preview_html = source_preview_html_path(native_blob, doc_id)

    preview_pdf_url = ""
    preview_html_url = ""

    source_container = get_source_container_client(workspace)

    if preview_pdf:
        preview_pdf_blob = source_container.get_blob_client(preview_pdf)

        if preview_pdf_blob.exists():
            preview_pdf_url = get_source_blob_url(
                workspace,
                preview_pdf,
            )

    if preview_html:
        preview_html_blob = source_container.get_blob_client(preview_html)

        if preview_html_blob.exists():
            preview_html_url = get_source_blob_url(
                workspace,
                preview_html,
            )

    native_url = document.get("native_url", "")

    text_url = (
        get_source_blob_url(workspace, text_blob)
        if text_blob
        else ""
    )

    if not text_url and extension in [".txt", ".csv", ".json", ".xml", ".html", ".htm", ".dat"]:
        text_url = native_url

    if preview_pdf_url:
        viewer_type = "pdf"
        viewer_url = preview_pdf_url
        preview_available = True

    elif preview_html_url:
        viewer_type = "html"
        viewer_url = preview_html_url
        preview_available = True

    elif viewer_type == "pdf":
        viewer_url = native_url
        preview_available = bool(native_url)

    elif viewer_type == "image":
        viewer_url = native_url
        preview_available = bool(native_url)

    elif viewer_type == "text":
        viewer_url = text_url or native_url
        preview_available = bool(viewer_url)

    elif viewer_type == "email":
        viewer_url = text_url or native_url
        preview_available = bool(viewer_url)

    elif viewer_type == "needs_preview_conversion":
        viewer_url = text_url or native_url
        preview_available = bool(viewer_url)

    else:
        viewer_url = text_url or native_url
        preview_available = bool(viewer_url)

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        "doc_id": doc_id,
        "file_name": file_name,
        "extension": extension,
        "viewer_type": viewer_type,
        "preview_available": preview_available,
        "viewer_url": viewer_url,
        "native_url": native_url,
        "text_url": text_url,
        "native_path": native_blob,
        "text_path": text_blob,
        "preview_pdf_path": preview_pdf,
        "preview_html_path": preview_html,
        "preview_pdf_url": preview_pdf_url,
        "preview_html_url": preview_html_url,
    }

@router.get("/{workspace}/review/current")
def get_workspace_current_review_document(
    workspace: str,
    project: str,
    batch: str = "",
    client: str = "",
    doc: str = "",
    native_blob: str = "",
    blob_path: str = "",
):
    try:
        return load_current_review_document(
            workspace=workspace,
            client=client,
            project=project,
            batch=batch,
            doc=doc,
            native_blob=native_blob or blob_path,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review load failed: {type(e).__name__}: {e}",
        )


class CaptureSaveRequest(BaseModel):
    workspace: str = "capture"
    client_id: str = ""
    project_id: str
    batch_id: str = ""
    doc_id: str
    values: dict = {}
    document_coding: str = ""
    further_review_reason: str = ""
    qc_coding: str = ""
    qc_questions: str = ""
    discovery_tags: dict = {}
    discovery_notes: dict = {}


@router.post("/review/save")
def save_capture(
    payload: CaptureSaveRequest,
    x_username: str = Header(default=""),
):
    workspace = (
        payload.workspace
        if payload.workspace in VALID_WORKSPACES
        else "capture"
    )

    state = save_document_review_state(
        workspace=workspace,
        client=payload.client_id,
        project_id=payload.project_id,
        batch_id=payload.batch_id,
        doc_id=payload.doc_id,
        document_coding=payload.document_coding,
        further_review_reason=payload.further_review_reason,
        qc_coding=payload.qc_coding,
        qc_questions=payload.qc_questions,
        values=payload.values,
        reviewed_by=x_username,
        action="save",
    )


    if payload.batch_id:
        container = get_container_client(workspace)

        batch_blob = get_batch_blob_name(
            workspace=workspace,
            client=payload.client_id,
            project_id=payload.project_id,
            batch=payload.batch_id,
        )

        blob_client = container.get_blob_client(batch_blob)

        if blob_client.exists():
            batch = json.loads(
                blob_client.download_blob()
                .readall()
                .decode("utf-8")
            )

            reviewed_docs = batch.get("reviewed_doc_ids", [])

            if payload.doc_id not in reviewed_docs:
                reviewed_docs.append(payload.doc_id)

            batch["reviewed_doc_ids"] = reviewed_docs
            batch["completed_count"] = len(reviewed_docs)
            batch["last_reviewed_doc_id"] = payload.doc_id
            batch["last_reviewed_by"] = x_username
            batch["last_reviewed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            batch_history = batch.get("review_history_by_doc", {})
            batch_history[payload.doc_id] = {
                "document_coding": payload.document_coding,
                "further_review_reason": payload.further_review_reason,
                "qc_coding": payload.qc_coding,
                "qc_questions": payload.qc_questions,
                "reviewed_by": x_username,
                "reviewed_at": batch["last_reviewed_at"],
            }
            batch["review_history_by_doc"] = batch_history

            if batch["completed_count"] >= batch.get("document_count", 0):
                batch["status"] = "Completed"

            blob_client.upload_blob(
                json.dumps(batch, indent=2),
                overwrite=True,
            )

    return {
        "status": "saved",
        "doc_id": payload.doc_id,
        "values": payload.values,
        "document_coding": state.get("document_coding", ""),
        "qc_coding": state.get("qc_coding", ""),
        "qc_questions": state.get("qc_questions", ""),
    }


@router.post("/review/save-next")
def save_and_next(
    payload: CaptureSaveRequest,
    x_username: str = Header(default=""),
):
    save_capture(payload, x_username)

    return {
        "status": "saved_next",
        "message": f"Saved {payload.doc_id}. Next document ready.",
    }
    
@router.get("/review/coding-map")
def get_review_coding_map(
    project: str,
    client: str = "",
    workspace: str = "capture",
):
    container = get_container_client(workspace)

    base_path = project_base_path(
        workspace,
        client,
        project,
    )
    document_prefix = f"{base_path}/Review/documents/"

    coding_map = {}

    for blob in container.list_blobs(name_starts_with=document_prefix):
        if not blob.name.endswith(".json"):
            continue

        state = json.loads(
            container
            .get_blob_client(blob.name)
            .download_blob()
            .readall()
            .decode("utf-8")
        )

        doc_id = state.get("doc_id", "")
        coding = state.get("document_coding", "")

        if doc_id and coding:
            coding_map[doc_id] = coding

    return coding_map