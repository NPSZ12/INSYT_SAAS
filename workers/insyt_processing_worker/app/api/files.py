from fastapi import APIRouter

from app.services.azure_blob_service import list_project_files

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.get("/")
def list_files(project: str):
    files = list_project_files(project)

    rows = []

    for file in files:
        blob_name = file["name"]
        file_name = blob_name.split("/")[-1]

        if not file_name:
            continue

        doc_id = file_name.rsplit(".", 1)[0]
        extension = file_name.rsplit(".", 1)[-1] if "." in file_name else ""

        rows.append({
            "doc_id": doc_id,
            "file_name": file_name,
            "extension": extension,
            "blob_path": blob_name,
            "size": str(file.get("size", "")),
            "last_modified": file.get("last_modified", ""),
        })

    return rows