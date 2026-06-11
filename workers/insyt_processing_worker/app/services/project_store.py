import json
from pathlib import Path

DATA_DIR = Path("C:/INSYT_SAAS/backend/data/store")
DATA_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_FOLDERS_FILE = DATA_DIR / "search_folders.json"
SEARCH_HITS_FILE = DATA_DIR / "search_hits.json"


def load_json(path, default):
    if not path.exists():
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


BATCHES = [
    {
        "project_id": "Project_Timber",
        "batch_id": "Batch_001",
        "name": "Batch 001",
        "status": "Available",
        "documents": "20",
        "checked_out_by": "",
    },
    {
        "project_id": "Project_Timber",
        "batch_id": "Batch_002",
        "name": "Batch 002",
        "status": "Checked Out",
        "documents": "20",
        "checked_out_by": "reviewer1",
    },
]

CAPTURED_ENTITIES = []

SEARCH_FOLDERS = load_json(SEARCH_FOLDERS_FILE, [])
SEARCH_HITS = load_json(SEARCH_HITS_FILE, [])


def save_search_folders():
    save_json(SEARCH_FOLDERS_FILE, SEARCH_FOLDERS)


def save_search_hits():
    save_json(SEARCH_HITS_FILE, SEARCH_HITS)

TIME_ENTRIES = []

MESSAGES = [
    {
        "project_id": "Project_Timber",
        "sender": "INSYT Admin",
        "time": "Today at 9:15 AM",
        "message": "Please prioritize Batch 001 and flag any illegible handwriting.",
    }
]