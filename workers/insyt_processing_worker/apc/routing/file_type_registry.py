from __future__ import annotations

from pathlib import Path


REGISTRY_VERSION = "1"


#
# These formats are already permitted to remain on the
# hardened shared ingestion spine.
#
CONTINUE_EXTENSIONS = {
    ".pdf",

    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",

    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".md",
    ".log",
    ".rtf",
}


#
# These formats are handled by the existing expansion stage.
#
# Their resulting leaf children are routed independently.
#
EXPANSION_EXTENSIONS = {
    ".zip",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
}


def normalize_extension(
    extension: str | None,
    original_path: str | None = None,
) -> str:
    value = str(extension or "").strip().lower()

    if value:
        if not value.startswith("."):
            value = f".{value}"

        return value

    path_value = str(original_path or "").strip()

    if not path_value:
        return ""

    return Path(path_value).suffix.lower()


def resolve_file_route(
    *,
    extension: str | None,
    original_path: str | None = None,
) -> dict[str, str | None]:
    resolved_extension = normalize_extension(
        extension,
        original_path,
    )

    if resolved_extension in CONTINUE_EXTENSIONS:
        return {
            "status": "continue",
            "extension": resolved_extension,
            "route": "core",
            "adapter": None,
            "reason": "supported_core_file_type",
            "registry_version": REGISTRY_VERSION,
        }

    if resolved_extension in EXPANSION_EXTENSIONS:
        return {
            "status": "continue",
            "extension": resolved_extension,
            "route": "container_expansion",
            "adapter": None,
            "reason": "supported_container_type",
            "registry_version": REGISTRY_VERSION,
        }

    return {
        "status": "train_station",
        "extension": resolved_extension,
        "route": "train_station",
        "adapter": None,
        "reason": "unregistered_file_type",
        "registry_version": REGISTRY_VERSION,
    }
