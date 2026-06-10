import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services.batch_service import get_container_client
from app.services.project_store import (
    SEARCH_FOLDERS,
    SEARCH_HITS,
    BATCHES,
    save_search_folders,
    save_search_hits,
)

router = APIRouter(prefix="/api/search-folders", tags=["Search Folders"])


class SearchFolderRequest(BaseModel):
    project_id: str
    client_id: str = ""
    workspace: str = "capture"
    folder_name: str
    search_type: str
    search_terms: list[str]

def clean_path(value: str | None) -> str:
    return str(value or "").strip().strip("/")


def project_base_path(client: str | None, project: str) -> str:
    client_name = clean_path(client)
    project_name = clean_path(project)

    if client_name:
        return f"{client_name}/{project_name}"

    return project_name


def list_workspace_text_files(
    workspace: str,
    client: str,
    project: str,
):
    container = get_container_client(workspace)
    base_path = project_base_path(client, project)
    prefix = f"{base_path}/source/text/"

    files = []

    for blob in container.list_blobs(name_starts_with=prefix):
        if not blob.name.lower().endswith(".txt"):
            continue

        file_name = blob.name.split("/")[-1]
        doc_id = file_name.rsplit(".", 1)[0]

        files.append(
            {
                "doc_id": doc_id,
                "file_name": file_name,
                "blob_name": blob.name,
            }
        )

    return files


def read_workspace_blob_text(workspace: str, blob_name: str) -> str:
    container = get_container_client(workspace)

    return (
        container
        .get_blob_client(blob_name)
        .download_blob()
        .readall()
        .decode("utf-8", errors="replace")
    )


def list_document_coding_states(
    workspace: str,
    client: str,
    project: str,
):
    container = get_container_client(workspace)
    base_path = project_base_path(client, project)
    prefix = f"{base_path}/Review/documents/"

    states = []

    for blob in container.list_blobs(name_starts_with=prefix):
        if not blob.name.endswith(".json"):
            continue

        state = json.loads(
            container
            .get_blob_client(blob.name)
            .download_blob()
            .readall()
            .decode("utf-8")
        )

        states.append(state)

    return states


def save_search_folder_blob(
    workspace: str,
    client: str,
    project: str,
    folder: dict,
    hits: list[dict],
):
    container = get_container_client(workspace)
    base_path = project_base_path(client, project)

    folder_blob = f"{base_path}/SearchFolders/{folder['folder_id']}.json"
    results_blob = f"{base_path}/SearchFolderResults/{folder['folder_id']}.json"

    container.upload_blob(
        name=folder_blob,
        data=json.dumps(folder, indent=2),
        overwrite=True,
    )

    container.upload_blob(
        name=results_blob,
        data=json.dumps(
            {
                "folder": folder,
                "results": hits,
                "doc_ids": sorted(
                    set(hit["doc_id"] for hit in hits)
                ),
            },
            indent=2,
        ),
        overwrite=True,
    )

    return {
        "folder_blob": folder_blob,
        "results_blob": results_blob,
    }


@router.get("/")
def list_search_folders(project: str):
    return [
        folder for folder in SEARCH_FOLDERS
        if folder["project_id"] == project
    ]

def evaluate_boolean_query(query: str, text: str):
    text_lower = text.lower()
    query_lower = query.lower().strip()

    # proximity example:
    # dan w/3 clarkin

    proximity_match = re.search(
        r"(.+?)\s+w/(\d+)\s+(.+)",
        query_lower,
    )

    if proximity_match:
        left_term = proximity_match.group(1).strip()
        distance = int(proximity_match.group(2))
        right_term = proximity_match.group(3).strip()

        words = re.findall(r"\w+", text_lower)

        left_positions = [
            i for i, word in enumerate(words)
            if left_term in word
        ]

        right_positions = [
            i for i, word in enumerate(words)
            if right_term in word
        ]

        for left in left_positions:
            for right in right_positions:
                if abs(left - right) <= distance:
                    return True

        return False

    # AND
    if " and " in query_lower:
        parts = [p.strip() for p in query_lower.split(" and ")]
        return all(part in text_lower for part in parts)

    # OR
    if " or " in query_lower:
        parts = [p.strip() for p in query_lower.split(" or ")]
        return any(part in text_lower for part in parts)

    # NOT
    if " not " in query_lower:
        left, right = [p.strip() for p in query_lower.split(" not ", 1)]
        return left in text_lower and right not in text_lower

    # exact phrase
    if query_lower.startswith('"') and query_lower.endswith('"'):
        return query_lower.strip('"') in text_lower

    # fallback simple contains
    return query_lower in text_lower

@router.post("/create")
def create_search_folder(payload: SearchFolderRequest, x_username: str = Header(default="")):

    existing_folder = next(
        (
            folder for folder in SEARCH_FOLDERS
            if folder["project_id"] == payload.project_id
            and folder["folder_name"].lower() == payload.folder_name.lower()
        ),
        None,
    )

    if existing_folder:
        return {
            "status": "duplicate_name",
            "message": "A search folder with this name already exists for this project.",
            "folder": existing_folder,
        }

    folder_id = f"{payload.folder_name}_{len(SEARCH_FOLDERS) + 1:05d}"

    folder = {
        "folder_id": folder_id,
        "project_id": payload.project_id,
        "folder_name": payload.folder_name,
        "search_type": payload.search_type,
        "search_terms": payload.search_terms,
        "created_by": x_username,
        "hit_count": 0,
        "document_count": 0,
    }

    unique_hit_docs = {}
    new_hits = []

    if payload.search_type == "coding":
        coding_terms = {
            term.strip().lower()
            for term in payload.search_terms
            if term.strip()
        }

        for state in list_document_coding_states(
            payload.workspace,
            payload.client_id,
            payload.project_id,
        ):
            doc_id = str(state.get("doc_id", "")).strip()
            coding = str(state.get("document_coding", "")).strip()

            if not doc_id or coding.lower() not in coding_terms:
                continue

            hit = {
                "folder_id": folder_id,
                "project_id": payload.project_id,
                "client_id": payload.client_id,
                "workspace": payload.workspace,
                "doc_id": doc_id,
                "file_name": doc_id,
                "blob_name": state.get("native_blob", ""),
                "term": coding,
                "search_type": payload.search_type,
                "tag": payload.folder_name,
            }

            SEARCH_HITS.append(hit)
            new_hits.append(hit)

            unique_hit_docs[doc_id] = {
                "doc_id": doc_id,
                "file_name": doc_id,
                "blob_name": state.get("native_blob", ""),
            }

    else:
        text_files = list_workspace_text_files(
            payload.workspace,
            payload.client_id,
            payload.project_id,
        )

        for file in text_files:
            blob_name = file["blob_name"]
            file_name = file["file_name"]
            doc_id = file["doc_id"]

            text = read_workspace_blob_text(
                payload.workspace,
                blob_name,
            )

            for term in payload.search_terms:
                if not term.strip():
                    continue

                if payload.search_type == "regex":
                    matched = (
                        re.search(
                            term,
                            text,
                            flags=re.IGNORECASE,
                        )
                        is not None
                    )

                elif payload.search_type == "boolean":
                    matched = evaluate_boolean_query(term, text)

                else:
                    matched = term.lower() in text.lower()

                if matched:
                    hit = {
                        "folder_id": folder_id,
                        "project_id": payload.project_id,
                        "client_id": payload.client_id,
                        "workspace": payload.workspace,
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "blob_name": blob_name,
                        "term": term,
                        "search_type": payload.search_type,
                        "tag": payload.folder_name,
                    }

                    SEARCH_HITS.append(hit)
                    new_hits.append(hit)

                    unique_hit_docs[doc_id] = {
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "blob_name": blob_name,
                    }

    folder["hit_count"] = len([
        hit for hit in SEARCH_HITS
        if hit["folder_id"] == folder_id
    ])

    folder["document_count"] = len(unique_hit_docs)

    SEARCH_FOLDERS.append(folder)
    save_search_folders()
    save_search_hits()
    saved_blobs = save_search_folder_blob(
        workspace=payload.workspace,
        client=payload.client_id,
        project=payload.project_id,
        folder=folder,
        hits=new_hits,
    )

    supplemental_batch_id = f"{payload.folder_name}_00001"

    BATCHES.append({
        "project_id": payload.project_id,
        "batch_id": supplemental_batch_id,
        "name": supplemental_batch_id,
        "status": "Available",
        "documents": str(len(unique_hit_docs)),
        "checked_out_by": "",
        "source_folder_id": folder_id,
        "doc_ids": list(unique_hit_docs.keys()),
    })

    return {
        "status": "created",
        "folder": folder,
        "batch_id": supplemental_batch_id,
        "documents": list(unique_hit_docs.values()),
        "saved_blobs": saved_blobs,
    }


@router.get("/{folder_id}/hits")
def list_search_hits(folder_id: str):
    return [
        hit for hit in SEARCH_HITS
        if hit["folder_id"] == folder_id
    ]
    
@router.post("/{folder_id}/delete")
def delete_search_folder(folder_id: str):
    global SEARCH_FOLDERS
    global SEARCH_HITS

    SEARCH_FOLDERS[:] = [
        folder for folder in SEARCH_FOLDERS
        if folder["folder_id"] != folder_id
    ]

    SEARCH_HITS[:] = [
        hit for hit in SEARCH_HITS
        if hit["folder_id"] != folder_id
    ]

    save_search_folders()
    save_search_hits()

    return {
        "status": "deleted",
        "folder_id": folder_id,
    }