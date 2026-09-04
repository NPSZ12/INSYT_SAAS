import json
import sys
import traceback

sys.path.insert(0, r"C:\INSYT_SAAS\backend")

result = {}

def safe(name, fn):
    try:
        result[name] = fn()
    except Exception as exc:
        result[name] = {
            "error": type(exc).__name__ + ": " + str(exc),
            "traceback": traceback.format_exc(),
        }

def probe_azure_layout():
    from apc.azure_layout import AzureRoutingConfig

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        r = AzureRoutingConfig.from_args(
            workspace="capture",
            client="Client1",
            project=project,
            azure_write=True,
        )

        out[project] = {
            "prefix": r.prefix,
            "uploads": r.processing_paths().get("uploads"),
            "jobs": r.processing_paths().get("jobs"),
            "native": r.review_paths().get("native"),
            "text": r.review_paths().get("text"),
            "reports": r.review_paths().get("reports"),
        }

    return out

def probe_processing_center_azure():
    from app.api.processing_center_azure import _project_base_path, _storage_project_key

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        out[project] = {
            "storage_project_key": _storage_project_key(project),
            "project_base_path": _project_base_path(
                workspace="capture",
                client="Client1",
                project=project,
            ),
        }

    return out

def probe_storage_paths():
    from app.services.storage_paths import build_project_base_path

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        out[project] = build_project_base_path(
            workspace="capture",
            client="Client1",
            project=project,
        )

    return out

safe("apc.azure_layout.AzureRoutingConfig", probe_azure_layout)
safe("app.api.processing_center_azure._project_base_path", probe_processing_center_azure)
safe("app.services.storage_paths.build_project_base_path", probe_storage_paths)

print(json.dumps(result, indent=2))
