import re
from fastapi import APIRouter, Header
from pydantic import BaseModel
import re
from app.services.azure_blob_service import list_project_files, read_blob_text
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
    folder_name: str
    search_type: str  # "text" or "regex"
    search_terms: list[str]


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

    files = list_project_files(payload.project_id)

    text_files = [
        file for file in files
        if file["name"].lower().endswith(".txt")
    ]

    unique_hit_docs = {}

    for file in text_files:
        blob_name = file["name"]
        file_name = blob_name.split("/")[-1]
        doc_id = file_name.rsplit(".", 1)[0]

        text = read_blob_text(blob_name)

        for term in payload.search_terms:
            if not term.strip():
                continue

            if payload.search_type == "regex":
                matched = re.search(term, text, flags=re.IGNORECASE) is not None

            elif payload.search_type == "boolean":
                matched = evaluate_boolean_query(term, text)

            else:
                matched = term.lower() in text.lower()

            if matched:
                SEARCH_HITS.append({
                    "folder_id": folder_id,
                    "project_id": payload.project_id,
                    "doc_id": doc_id,
                    "file_name": file_name,
                    "blob_name": blob_name,
                    "term": term,
                    "search_type": payload.search_type,
                    "tag": payload.folder_name,
                })

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