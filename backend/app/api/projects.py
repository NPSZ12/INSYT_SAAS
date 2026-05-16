from fastapi import APIRouter

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("")
def list_projects():
    return [
        {
            "name": "Project Timber",
            "client": "Builders FirstSource",
            "status": "Active",
            "docs": "1,189",
            "qc": "87%",
        },
        {
            "name": "Alpine Claims",
            "client": "BFS / Alpine",
            "status": "QC Review",
            "docs": "436",
            "qc": "72%",
        },
        {
            "name": "Medical Summary Demo",
            "client": "INSYT Internal",
            "status": "Ready",
            "docs": "58",
            "qc": "100%",
        },
    ]