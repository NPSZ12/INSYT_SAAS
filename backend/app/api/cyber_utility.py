import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import shutil
import tempfile

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.workspace_files import build_prefix, clean_folder, get_workspace_container


router = APIRouter(
    prefix="/api/cyber-utility",
    tags=["cyber-utility"],
)

VALID_WORKSPACES = {"capture", "summaries", "discovery"}
SPREADSHEET_EXTENSIONS = {"xlsx", "xls", "xlsm", "csv"}

UTILITY_JOBS: dict[str, dict] = {}


class UtilityJobRequest(BaseModel):
    workspace: str
    project_id: str
    tool_name: str
    client: str | None = None
    input_path: str | None = None
    output_path: str | None = None
    options: dict = Field(default_factory=dict)

class ApplyHeaderMapRequest(BaseModel):
    workspace: str = "capture"
    project_id: str
    client: str | None = None
    job_id: str
    header_map: dict[str, str] = Field(default_factory=dict)
    delimiter: str = ","
    
class MergeSelectedCsvsRequest(BaseModel):
    workspace: str = "capture"
    project_id: str
    client: str | None = None
    selected_csv_blobs: list[str] = Field(default_factory=list)
    header_map: dict[str, str] = Field(default_factory=dict)
    delimiter: str = ","
    output_name: str | None = None

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_job_status(job_id: str, **updates):
    job = UTILITY_JOBS.get(job_id)

    if not job:
        return

    job.update(updates)
    job["updated_at"] = now_utc()


def get_blob_file_name(blob_path: str) -> str:
    return blob_path.rstrip("/").split("/")[-1]


def get_extension(file_name: str) -> str:
    if "." not in file_name:
        return ""

    return file_name.rsplit(".", 1)[-1].lower()


def safe_sheet_name(sheet_name: str) -> str:
    value = sheet_name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return value or "Sheet"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    return df


def collapse_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    collapsed = {}

    for column in dict.fromkeys(df.columns):
        matching = df.loc[:, df.columns == column]

        if isinstance(matching, pd.Series):
            collapsed[column] = matching
        else:
            collapsed[column] = matching.bfill(axis=1).iloc[:, 0]

    return pd.DataFrame(collapsed)


def upload_text(container, blob_path: str, content: str):
    container.upload_blob(
        name=blob_path,
        data=content.encode("utf-8"),
        overwrite=True,
    )


def upload_file(container, blob_path: str, local_path: Path):
    with local_path.open("rb") as file:
        container.upload_blob(
            name=blob_path,
            data=file,
            overwrite=True,
        )


def download_blob_to_file(container, blob_path: str, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)

    data = container.download_blob(blob_path).readall()

    with local_path.open("wb") as file:
        file.write(data)

    return data

def build_canonical_project_prefix(
    workspace: str,
    project: str,
    client: str | None,
    folder: str,
) -> str:
    """
    Canonical INSYT path:
      {client}/{workspace}/{project}/{folder}/

    Example:
      Baker/capture/Project_Timber/source/native/
    """
    clean_workspace = clean_folder(workspace)
    clean_project = clean_folder(project)
    clean_client = clean_folder(client) if client else ""

    folder = folder.strip("/")

    if clean_client:
        return f"{clean_client}/{clean_workspace}/{clean_project}/{folder}/"

    return f"{clean_workspace}/{clean_project}/{folder}/"


def build_legacy_project_prefixes(
    project: str,
    client: str | None,
    folder: str,
) -> list[str]:
    """
    Legacy fallbacks only. Canonical path should always be checked first.
    """
    prefixes = []

    try:
        legacy_prefix = build_prefix(
            project=project,
            client=client,
            folder=folder,
        )
        prefixes.append(legacy_prefix)
    except Exception:
        pass

    clean_project = clean_folder(project)
    clean_client = clean_folder(client) if client else ""
    clean_target_folder = folder.strip("/")

    if clean_client:
        prefixes.append(f"{clean_client}/{clean_project}/{clean_target_folder}/")
        prefixes.append(f"{clean_client}/{clean_target_folder}/{clean_project}/")

    prefixes.append(f"{clean_project}/{clean_target_folder}/")

    return list(dict.fromkeys(prefixes))


def build_project_prefixes(
    workspace: str,
    project: str,
    client: str | None,
    folder: str,
) -> list[str]:
    canonical = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder=folder,
    )

    return list(
        dict.fromkeys(
            [
                canonical,
                *build_legacy_project_prefixes(
                    project=project,
                    client=client,
                    folder=folder,
                ),
            ]
        )
    )

def list_spreadsheet_blobs(
    workspace: str,
    project: str,
    client: str | None,
    folder: str = "source/native",
):
    container = get_workspace_container(workspace)

    prefixes = build_project_prefixes(
        workspace=workspace,
        project=project,
        client=client,
        folder=folder,
    )

    files = []
    checked_prefixes = []

    for prefix in prefixes:
        checked_prefixes.append(prefix)

        for blob in container.list_blobs(name_starts_with=prefix):
            blob_path = blob.name
            file_name = get_blob_file_name(blob_path)

            if not file_name or file_name.startswith("."):
                continue

            extension = get_extension(file_name)

            if extension not in SPREADSHEET_EXTENSIONS:
                continue

            files.append(
                {
                    "doc_id": file_name.rsplit(".", 1)[0],
                    "file_name": file_name,
                    "extension": extension,
                    "blob_path": blob_path,
                    "size": str(blob.size or ""),
                    "last_modified": (
                        blob.last_modified.isoformat()
                        if blob.last_modified
                        else ""
                    ),
                    "workspace": workspace,
                    "client": clean_folder(client) if client else "",
                    "project": clean_folder(project),
                    "folder": clean_folder(folder),
                    "status": "Ready",
                    "matched_prefix": prefix,
                    "checked_prefixes": checked_prefixes,
                }
            )

        # Canonical path wins. Only fall back to legacy paths if nothing is found.
        if files:
            break

    return files

def list_output_csv_blobs(
    workspace: str,
    project: str,
    client: str | None,
):
    container = get_workspace_container(workspace)

    output_prefix = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/spreadsheets/Output",
    )

    excluded = {
        "Merged_Headers.csv",
        "header_merge_map.csv",
        "FINAL_MERGED_OUTPUT.csv",
    }

    files = []

    for blob in container.list_blobs(name_starts_with=output_prefix):
        blob_path = blob.name
        file_name = get_blob_file_name(blob_path)

        if not file_name:
            continue

        if file_name in excluded:
            continue

        if file_name.lower().startswith("final_merged_output"):
            continue

        if get_extension(file_name) != "csv":
            continue

        files.append(
            {
                "file_name": file_name,
                "blob_path": blob_path,
                "size": str(blob.size or ""),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if blob.last_modified
                    else ""
                ),
            }
        )

    return files

def list_merged_output_blobs(
    workspace: str,
    project: str,
    client: str | None,
):
    container = get_workspace_container(workspace)

    output_prefix = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/spreadsheets/Output",
    )

    files = []

    for blob in container.list_blobs(name_starts_with=output_prefix):
        blob_path = blob.name
        file_name = get_blob_file_name(blob_path)

        if not file_name:
            continue

        lower_name = file_name.lower()

        if not lower_name.startswith("final_merged_output"):
            continue

        if get_extension(file_name) != "csv":
            continue

        files.append(
            {
                "file_name": file_name,
                "blob_path": blob_path,
                "size": str(blob.size or ""),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if blob.last_modified
                    else ""
                ),
            }
        )

    return files

def list_needs_header_review_blobs(
    workspace: str,
    project: str,
    client: str | None,
):
    container = get_workspace_container(workspace)

    review_prefix = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/spreadsheets/Needs_Header_Review",
    )

    files = []

    for blob in container.list_blobs(name_starts_with=review_prefix):
        blob_path = blob.name
        file_name = get_blob_file_name(blob_path)

        if not file_name:
            continue

        files.append(
            {
                "file_name": file_name,
                "blob_path": blob_path,
                "size": str(blob.size or ""),
                "last_modified": (
                    blob.last_modified.isoformat()
                    if blob.last_modified
                    else ""
                ),
            }
        )

    return files

def list_xl_processing_jobs(
    workspace: str,
    project: str,
    client: str | None,
):
    clean_workspace = clean_folder(workspace)
    clean_project = clean_folder(project)
    clean_client = clean_folder(client) if client else ""

    jobs = []

    for job in UTILITY_JOBS.values():
        if job.get("tool_name") != "XL Processing":
            continue

        if clean_folder(job.get("workspace") or "") != clean_workspace:
            continue

        if clean_folder(job.get("project_id") or "") != clean_project:
            continue

        if clean_folder(job.get("client") or "") != clean_client:
            continue

        jobs.append(job)

    return sorted(
        jobs,
        key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        reverse=True,
    )

def build_master_csv(
    csv_paths: list[Path],
    output_dir: Path,
    delimiter: str,
    header_map: dict[str, str] | None = None,
    canonical_headers: list[str] | None = None,
):
    frames = []

    for csv_path in csv_paths:
        df = pd.read_csv(
            csv_path,
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
        ).fillna("")

        df = clean_dataframe(df)

        # Always preserve source file as Column A.
        if "Source File" in df.columns:
            df["Source File"] = csv_path.name
        else:
            df.insert(0, "Source File", csv_path.name)

        df.columns = [str(c).strip() for c in df.columns]

        if header_map:
            clean_map = {
                str(source).strip(): str(target).strip()
                for source, target in header_map.items()
                if str(source).strip() and str(target).strip()
            }
            df.rename(columns=clean_map, inplace=True)

        df = collapse_duplicate_columns(df)
        df = clean_dataframe(df)

        frames.append(df)

    if not frames:
        return None

    final_df = pd.concat(frames, ignore_index=True, sort=False)
    final_df = collapse_duplicate_columns(final_df)
    final_df = clean_dataframe(final_df)

    if canonical_headers:
        ordered_headers = [
            str(header).strip()
            for header in canonical_headers
            if str(header).strip()
        ]

        # Force Source File first.
        ordered_headers = ["Source File"] + [
            header
            for header in ordered_headers
            if normalize_text(header) != normalize_text("Source File")
        ]

        existing_extras = [
            column
            for column in final_df.columns
            if column not in ordered_headers
        ]

        final_columns = ordered_headers + existing_extras

        for column in final_columns:
            if column not in final_df.columns:
                final_df[column] = ""

        final_df = final_df[final_columns]
    else:
        final_columns = ["Source File"] + [
            column
            for column in sorted(final_df.columns)
            if normalize_text(column) != normalize_text("Source File")
        ]
        final_df = final_df[final_columns]

    final_out = output_dir / "FINAL_MERGED_OUTPUT.csv"
    final_df.to_csv(
        final_out,
        index=False,
        sep=delimiter,
        encoding="utf-8-sig",
    )

    return final_out

def rebuild_master_csv_from_outputs(
    workspace: str,
    project: str,
    client: str | None,
    header_map: dict[str, str],
    delimiter: str = ",",
):
    container = get_workspace_container(workspace)

    output_prefix = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/spreadsheets/Output",
    )

    output_blobs = list_output_csv_blobs(
        workspace=workspace,
        project=project,
        client=client,
    )

    if not output_blobs:
        raise ValueError("No generated CSV outputs found to merge.")

    temp_root = Path(tempfile.mkdtemp(prefix="xl_final_merge_"))

    try:
        input_dir = temp_root / "input"
        output_dir = temp_root / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        local_csv_paths = []

        for item in output_blobs:
            local_path = input_dir / item["file_name"]

            download_blob_to_file(
                container=container,
                blob_path=item["blob_path"],
                local_path=local_path,
            )

            local_csv_paths.append(local_path)

        canonical_headers = []

        if header_map:
            for target in header_map.values():
                clean_target = str(target or "").strip()

                if clean_target and clean_target not in canonical_headers:
                    canonical_headers.append(clean_target)

        master_path = build_master_csv(
            csv_paths=local_csv_paths,
            output_dir=output_dir,
            delimiter=delimiter,
            header_map=header_map,
            canonical_headers=canonical_headers,
        )

        if not master_path:
            raise ValueError("Final master CSV could not be created.")

        final_blob = f"{output_prefix}FINAL_MERGED_OUTPUT.csv"

        upload_file(
            container=container,
            blob_path=final_blob,
            local_path=master_path,
        )

        map_blob = f"{output_prefix}header_merge_map.csv"
        map_path = output_dir / "header_merge_map.csv"

        pd.DataFrame(
            [
                {
                    "Original_Header": source,
                    "Merged_Header": target,
                }
                for source, target in header_map.items()
            ]
        ).to_csv(
            map_path,
            index=False,
            encoding="utf-8-sig",
        )

        upload_file(
            container=container,
            blob_path=map_blob,
            local_path=map_path,
        )

        return {
            "final_output_blob": final_blob,
            "header_map_blob": map_blob,
            "merged_input_files": [item["blob_path"] for item in output_blobs],
        }

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

def rebuild_master_csv_from_selected_outputs(
    workspace: str,
    project: str,
    client: str | None,
    selected_csv_blobs: list[str],
    header_map: dict[str, str],
    delimiter: str = ",",
    output_name: str | None = None,
):
    container = get_workspace_container(workspace)

    output_prefix = build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/spreadsheets/Output",
    )

    excluded = {
        "Merged_Headers.csv",
        "header_merge_map.csv",
        "FINAL_MERGED_OUTPUT.csv",
    }

    temp_root = Path(tempfile.mkdtemp(prefix="xl_selected_merge_"))

    try:
        input_dir = temp_root / "input"
        output_dir = temp_root / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        local_csv_paths = []
        merged_input_files = []

        for blob_path in selected_csv_blobs:
            file_name = get_blob_file_name(blob_path)

            if not file_name:
                continue

            if get_extension(file_name) != "csv":
                continue

            if file_name in excluded:
                continue

            local_path = input_dir / file_name

            download_blob_to_file(
                container=container,
                blob_path=blob_path,
                local_path=local_path,
            )

            local_csv_paths.append(local_path)
            merged_input_files.append(blob_path)

        if not local_csv_paths:
            raise ValueError("No valid CSV files were selected for merge.")

        clean_header_map = {
            str(source).strip(): str(target).strip()
            for source, target in header_map.items()
            if str(source).strip() and str(target).strip()
        }

        canonical_headers = []

        for target in clean_header_map.values():
            clean_target = str(target or "").strip()

            if clean_target and clean_target not in canonical_headers:
                canonical_headers.append(clean_target)

        master_path = build_master_csv(
            csv_paths=local_csv_paths,
            output_dir=output_dir,
            delimiter=delimiter,
            header_map=clean_header_map,
            canonical_headers=canonical_headers,
        )

        if not master_path:
            raise ValueError("Selected merge output could not be created.")

        safe_output_name = str(output_name or "").strip()

        if not safe_output_name:
            safe_output_name = (
                "FINAL_MERGED_OUTPUT_"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            )

        if not safe_output_name.lower().endswith(".csv"):
            safe_output_name = f"{safe_output_name}.csv"

        # Keep blob name safe and predictable.
        safe_output_name = safe_output_name.replace("/", "_").replace("\\", "_")

        final_blob = f"{output_prefix}{safe_output_name}"

        upload_file(
            container=container,
            blob_path=final_blob,
            local_path=master_path,
        )

        return {
            "status": "completed",
            "message": "Selected CSV files merged.",
            "final_output_blob": final_blob,
            "merged_input_files": merged_input_files,
        }

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

def normalize_text(value: str) -> str:
    value = "" if value is None else str(value)
    value = value.strip().lower()
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    return value.strip()


def fuzzy_best_match(value: str, candidates: list[str], cutoff: float = 0.60) -> str:
    if not candidates:
        return value

    normalized_value = normalize_text(value)
    best = None
    best_score = 0.0

    for candidate in candidates:
        score = SequenceMatcher(None, normalized_value, normalize_text(candidate)).ratio()

        if score > best_score:
            best_score = score
            best = candidate

    return best if best is not None and best_score >= cutoff else value


def row_has_meaningful_headers(headers: list[str]) -> bool:
    cleaned = [str(h or "").strip() for h in headers]
    cleaned = [h for h in cleaned if h and not h.lower().startswith("unnamed")]

    if not cleaned:
        return False

    # If headers are just 0, 1, 2, 3 or blank placeholders, treat as no header.
    numeric_like = 0

    for header in cleaned:
        normalized = normalize_text(header)

        if normalized.isdigit():
            numeric_like += 1

    if cleaned and numeric_like / len(cleaned) >= 0.75:
        return False

    return True


def dataframe_has_headers(df: pd.DataFrame) -> bool:
    return row_has_meaningful_headers([str(c) for c in df.columns.tolist()])

def get_protocol_folder_prefix(
    workspace: str,
    project: str,
    client: str | None,
) -> str:
    return build_canonical_project_prefix(
        workspace=workspace,
        project=project,
        client=client,
        folder="source/protocol",
    )


def get_project_header_library_blob_paths(
    workspace: str,
    project: str,
    client: str | None,
) -> list[str]:
    protocol_prefix = get_protocol_folder_prefix(
        workspace=workspace,
        project=project,
        client=client,
    )

    clean_project = clean_folder(project)

    return [
        f"{protocol_prefix}{clean_project}_Header_Library.csv",
        f"{protocol_prefix}{clean_project}_Header_Library.xlsx",
    ]


def get_project_header_library_blob_path(
    workspace: str,
    project: str,
    client: str | None,
) -> str:
    """
    Primary expected path. CSV is preferred because the header library is now
    maintained as a downloadable/editable CSV.
    """
    return get_project_header_library_blob_paths(
        workspace=workspace,
        project=project,
        client=client,
    )[0]


def load_project_header_library(
    container,
    workspace: str,
    project: str,
    client: str | None,
) -> tuple[dict[str, list[str]], str]:
    """
    Loads project-specific header library from source/protocol.

    Preferred:
      {client}/{workspace}/{project}/source/protocol/{Project}_Header_Library.csv

    Fallback:
      {client}/{workspace}/{project}/source/protocol/{Project}_Header_Library.xlsx

    Format:
      - Each column header is the canonical/final header.
      - Each row value under that column is a synonym/source variation.
    """
    candidate_blob_paths = get_project_header_library_blob_paths(
        workspace=workspace,
        project=project,
        client=client,
    )

    data = None
    matched_blob_path = ""

    for blob_path in candidate_blob_paths:
        try:
            data = container.download_blob(blob_path).readall()
            matched_blob_path = blob_path
            break
        except Exception:
            continue

    if data is None:
        return {}, ""

    temp_root = Path(tempfile.mkdtemp(prefix="header_library_"))

    try:
        extension = get_extension(matched_blob_path)
        local_path = temp_root / f"Header_Library.{extension}"

        with local_path.open("wb") as file:
            file.write(data)

        if extension == "csv":
            df = pd.read_csv(local_path, dtype=str).fillna("")
        else:
            df = pd.read_excel(local_path, dtype=str).fillna("")

        library: dict[str, list[str]] = {}

        for column in df.columns:
            canonical = str(column or "").strip()

            if not canonical:
                continue

            variations = [canonical]

            for value in df[column].tolist():
                variation = str(value or "").strip()

                if variation:
                    variations.append(variation)

            seen = set()
            clean_variations = []

            for variation in variations:
                key = normalize_text(variation)

                if key and key not in seen:
                    seen.add(key)
                    clean_variations.append(variation)

            library[canonical] = clean_variations

        return library, matched_blob_path

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def get_protocol_header_library(
    container,
    workspace: str,
    project: str,
    client: str | None,
    protocol: str | None = None,
) -> tuple[dict[str, list[str]], str]:
    """
    Project-specific header library is source of truth.

    Preferred:
      {client}/{workspace}/{project}/source/protocol/{Project}_Header_Library.csv

    Fallback:
      {client}/{workspace}/{project}/source/protocol/{Project}_Header_Library.xlsx
    """
    return load_project_header_library(
        container=container,
        workspace=workspace,
        project=project,
        client=client,
    )


def build_synonym_lookup(library: dict[str, list[str]]) -> dict[str, str]:
    lookup = {}

    for canonical, variations in library.items():
        canonical_clean = str(canonical or "").strip()

        if not canonical_clean:
            continue

        lookup[normalize_text(canonical_clean)] = canonical_clean

        for variation in variations:
            variation_clean = str(variation or "").strip()

            if not variation_clean:
                continue

            lookup[normalize_text(variation_clean)] = canonical_clean

    return lookup


def get_standard_header_targets(library: dict[str, list[str]]) -> list[str]:
    return [str(header).strip() for header in library.keys() if str(header).strip()]


def suggest_header(header: str, library: dict[str, list[str]]) -> str:
    lookup = build_synonym_lookup(library)
    targets = get_standard_header_targets(library)

    key = normalize_text(header)

    if key in lookup:
        return lookup[key]

    return fuzzy_best_match(header, targets, cutoff=0.60)

def copy_blob_to_review_location(
    container,
    source_blob_path: str,
    review_prefix: str,
    reason: str,
):
    file_name = get_blob_file_name(source_blob_path)
    target_blob_path = f"{review_prefix}{file_name}"

    data = container.download_blob(source_blob_path).readall()

    container.upload_blob(
        name=target_blob_path,
        data=data,
        overwrite=True,
    )

    return {
        "source_blob_path": source_blob_path,
        "review_blob_path": target_blob_path,
        "reason": reason,
    }

def run_xl_processing_job(job_id: str, payload: UtilityJobRequest):
    temp_root = Path(tempfile.mkdtemp(prefix=f"xl_processing_{job_id}_"))

    try:
        workspace = payload.workspace
        project = payload.project_id
        client = payload.client

        if workspace not in VALID_WORKSPACES:
            raise ValueError("workspace must be capture, summaries, or discovery")

        container = get_workspace_container(workspace)

        protocol = payload.options.get("protocol") or payload.options.get("project_protocol")

        header_library, header_library_blob = get_protocol_header_library(
            container=container,
            workspace=workspace,
            project=project,
            client=client,
            protocol=protocol,
        )

        expected_header_library_blob = get_project_header_library_blob_path(
            workspace=workspace,
            project=project,
            client=client,
        )

        header_library_warning = ""

        if not header_library:
            expected_header_library_blobs = get_project_header_library_blob_paths(
                workspace=workspace,
                project=project,
                client=client,
            )

            header_library_warning = (
                "No project header library found. Expected one of: "
                + ", ".join(expected_header_library_blobs)
            )
        
        selected_files = payload.options.get("selected_files") or []
        delimiter = payload.options.get("delimiter") or ","
        build_master = bool(payload.options.get("build_master", True))
        extract_headers = bool(payload.options.get("extract_headers", True))
        header_map = payload.options.get("header_map") or {}

        if not selected_files:
            selected_files = [
                file["blob_path"]
                for file in list_spreadsheet_blobs(
                    workspace=workspace,
                    project=project,
                    client=client,
                )
            ]

        if not selected_files:
            raise ValueError("No spreadsheet files selected for processing.")

        input_dir = temp_root / "input"
        output_dir = temp_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        processing_prefix = build_canonical_project_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/spreadsheets/Processing",
        )
        completed_prefix = build_canonical_project_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/spreadsheets/Completed",
        )
        output_prefix = build_canonical_project_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/spreadsheets/Output",
        )
        logs_prefix = build_canonical_project_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/spreadsheets/Logs",
        )
        needs_review_prefix = build_canonical_project_prefix(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/spreadsheets/Needs_Header_Review",
        )

        set_job_status(
            job_id,
            status="running",
            message="XL Processing started.",
            total_files=len(selected_files),
            processed_files=0,
        )

        files_needing_header_review = []
        merged_headers: set[str] = set()
        generated_csvs: list[Path] = []
        processed = []
        errors = []

        for index, blob_path in enumerate(selected_files, start=1):
            file_name = get_blob_file_name(blob_path)
            extension = get_extension(file_name)
            local_input = input_dir / file_name

            try:
                original_bytes = download_blob_to_file(
                    container=container,
                    blob_path=blob_path,
                    local_path=local_input,
                )

                processing_blob = f"{processing_prefix}{file_name}"
                completed_blob = f"{completed_prefix}{file_name}"

                container.upload_blob(
                    name=processing_blob,
                    data=original_bytes,
                    overwrite=True,
                )

                if extension == "csv":
                    df = pd.read_csv(local_input, sep=delimiter, dtype=str)
                    df = clean_dataframe(df)

                    if not dataframe_has_headers(df):
                        review_item = copy_blob_to_review_location(
                            container=container,
                            source_blob_path=blob_path,
                            review_prefix=needs_review_prefix,
                            reason="CSV appears to have no usable header row.",
                        )
                        files_needing_header_review.append(review_item)
                        processed.append(blob_path)

                        try:
                            container.delete_blob(processing_blob)
                        except Exception:
                            pass

                        continue

                    if extract_headers:
                        merged_headers.update(map(str, df.columns.tolist()))

                    out_path = output_dir / file_name
                    df.to_csv(out_path, index=False, sep=delimiter, encoding="utf-8")
                    generated_csvs.append(out_path)

                else:
                    workbook = pd.ExcelFile(local_input)

                    for sheet in workbook.sheet_names:
                        df = pd.read_excel(
                            workbook,
                            sheet_name=sheet,
                            dtype=str,
                        )
                        df = clean_dataframe(df)

                        if not dataframe_has_headers(df):
                            review_item = copy_blob_to_review_location(
                                container=container,
                                source_blob_path=blob_path,
                                review_prefix=needs_review_prefix,
                                reason=f"Excel sheet '{sheet}' appears to have no usable header row.",
                            )
                            files_needing_header_review.append(review_item)
                            continue

                        if extract_headers:
                            merged_headers.update(map(str, df.columns.tolist()))

                        base = Path(file_name).stem
                        out_file = f"{base}_{safe_sheet_name(sheet)}.csv"
                        out_path = output_dir / out_file

                        df.to_csv(
                            out_path,
                            index=False,
                            sep=delimiter,
                            encoding="utf-8",
                        )
                        generated_csvs.append(out_path)

                container.upload_blob(
                    name=completed_blob,
                    data=original_bytes,
                    overwrite=True,
                )

                try:
                    container.delete_blob(processing_blob)
                except Exception:
                    pass

                processed.append(blob_path)

            except Exception as exc:
                errors.append(
                    {
                        "blob_path": blob_path,
                        "error": str(exc),
                    }
                )

            set_job_status(
                job_id,
                processed_files=index,
                message=f"Processed {index}/{len(selected_files)} files.",
            )

        output_files = []

        header_review_rows = []

        if extract_headers and merged_headers:
            sorted_headers = sorted(merged_headers)

            header_review_rows = [
                {
                    "source_header": header,
                    "suggested_header": suggest_header(header, header_library),
                    "final_header": suggest_header(header, header_library),
                    "protocol": protocol or "",
                    "header_library_blob": header_library_blob,
                    "ai_suggestion": "",
                    "confidence": "",
                }
                for header in sorted_headers
            ]

            headers_path = output_dir / "Merged_Headers.csv"
            pd.DataFrame(header_review_rows).to_csv(
                headers_path,
                index=False,
                encoding="utf-8",
            )
            output_files.append(headers_path)

        if build_master and not extract_headers:
            master_path = build_master_csv(
                csv_paths=generated_csvs,
                output_dir=output_dir,
                delimiter=delimiter,
                header_map=header_map,
            )

            if master_path:
                output_files.append(master_path)

        for csv_path in generated_csvs:
            if csv_path not in output_files:
                output_files.append(csv_path)

        uploaded_outputs = []

        for local_output in output_files:
            output_blob = f"{output_prefix}{local_output.name}"
            upload_file(container, output_blob, local_output)
            uploaded_outputs.append(output_blob)

        log = {
            "job_id": job_id,
            "workspace": workspace,
            "client": client,
            "project": project,
            "protocol": protocol,
            "header_library_blob": header_library_blob,
            "header_library_warning": header_library_warning,
            "selected_files": selected_files,
            "processed_files": processed,
            "files_needing_header_review": files_needing_header_review,
            "errors": errors,
            "outputs": uploaded_outputs,
            "completed_at": now_utc(),
        }

        log_blob = f"{logs_prefix}{job_id}.json"
        upload_text(
            container=container,
            blob_path=log_blob,
            content=json.dumps(log, indent=2),
        )

        final_status = "header_review_required" if header_review_rows else (
            "completed_with_errors" if errors else "completed"
        )

        final_message = (
            "XL/CSV files converted and headers extracted. Header review required."
            if header_review_rows
            else "XL Processing completed."
        )

        set_job_status(
            job_id,
            status=final_status,
            message=final_message,
            output_files=uploaded_outputs,
            log_blob=log_blob,
            errors=errors,
            extracted_headers=header_review_rows,
            files_needing_header_review=files_needing_header_review,
            protocol=protocol,
            header_library_blob=header_library_blob,
            header_library_warning=header_library_warning,
        )

    except Exception as exc:
        set_job_status(
            job_id,
            status="failed",
            message=str(exc),
            errors=[{"error": str(exc)}],
        )

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@router.get("/xl-processing/files")
def get_xl_processing_files(
    workspace: str = Query(default="capture"),
    project: str = Query(...),
    client: str | None = Query(default=None),
    folder: str = Query(default="source/native"),
):
    files = list_spreadsheet_blobs(
        workspace=workspace,
        project=project,
        client=client,
        folder=folder,
    )

    if files:
        return files

    return {
        "files": [],
        "message": "No XL or CSV files found.",
        "checked_prefixes": build_project_prefixes(
            workspace=workspace,
            project=project,
            client=client,
            folder=folder,
        ),
    }

@router.get("/xl-processing/center")
def get_xl_processing_center(
    workspace: str = Query(default="capture"),
    project: str = Query(...),
    client: str | None = Query(default=None),
):
    if workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="workspace must be capture, summaries, or discovery",
        )

    return {
        "workspace": workspace,
        "client": clean_folder(client) if client else "",
        "project": clean_folder(project),
        "source_files": list_spreadsheet_blobs(
            workspace=workspace,
            project=project,
            client=client,
            folder="source/native",
        ),
        "output_csvs": list_output_csv_blobs(
            workspace=workspace,
            project=project,
            client=client,
        ),
        "merged_outputs": list_merged_output_blobs(
            workspace=workspace,
            project=project,
            client=client,
        ),
        "needs_header_review": list_needs_header_review_blobs(
            workspace=workspace,
            project=project,
            client=client,
        ),
        "jobs": list_xl_processing_jobs(
            workspace=workspace,
            project=project,
            client=client,
        ),
    }

@router.post("/xl-processing/apply-headers")
def apply_xl_processing_headers(payload: ApplyHeaderMapRequest):
    job = UTILITY_JOBS.get(payload.job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Utility job not found.",
        )

    if job.get("status") != "header_review_required":
        raise HTTPException(
            status_code=400,
            detail="Job is not waiting for header review.",
        )

    if payload.workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="workspace must be capture, summaries, or discovery",
        )

    clean_header_map = {
        str(source).strip(): str(target).strip()
        for source, target in payload.header_map.items()
        if str(source).strip() and str(target).strip()
    }

    if not clean_header_map:
        raise HTTPException(
            status_code=400,
            detail="No approved header map was provided.",
        )

    set_job_status(
        payload.job_id,
        status="final_merge_running",
        message="Header map approved. Building FINAL_MERGED_OUTPUT.csv.",
        approved_header_map=clean_header_map,
    )

    try:
        result = rebuild_master_csv_from_outputs(
            workspace=payload.workspace,
            project=payload.project_id,
            client=payload.client,
            header_map=clean_header_map,
            delimiter=payload.delimiter,
        )

    except Exception as exc:
        set_job_status(
            payload.job_id,
            status="final_merge_failed",
            message=str(exc),
            final_merge_error=str(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    set_job_status(
        payload.job_id,
        status="completed",
        message="XL Processing completed. FINAL_MERGED_OUTPUT.csv created.",
        approved_header_map=clean_header_map,
        final_output_blob=result["final_output_blob"],
        header_map_blob=result["header_map_blob"],
        merged_input_files=result["merged_input_files"],
    )

    return UTILITY_JOBS[payload.job_id]

@router.post("/xl-processing/merge-selected")
def merge_selected_xl_csvs(payload: MergeSelectedCsvsRequest):
    if payload.workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="workspace must be capture, summaries, or discovery",
        )

    if not payload.selected_csv_blobs:
        raise HTTPException(
            status_code=400,
            detail="No CSV files selected for merge.",
        )

    try:
        result = rebuild_master_csv_from_selected_outputs(
            workspace=payload.workspace,
            project=payload.project_id,
            client=payload.client,
            selected_csv_blobs=payload.selected_csv_blobs,
            header_map=payload.header_map,
            delimiter=payload.delimiter,
            output_name=payload.output_name,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return result

@router.post("/jobs")
def create_utility_job(
    payload: UtilityJobRequest,
    background_tasks: BackgroundTasks,
):
    if payload.workspace not in VALID_WORKSPACES:
        raise HTTPException(
            status_code=400,
            detail="workspace must be capture, summaries, or discovery",
        )

    job_id = str(uuid4())

    job = {
        "job_id": job_id,
        "status": "queued",
        "workspace": payload.workspace,
        "project_id": payload.project_id,
        "client": payload.client,
        "tool_name": payload.tool_name,
        "input_path": payload.input_path,
        "output_path": payload.output_path,
        "options": payload.options,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "message": "Cyber² Utility job queued.",
    }

    UTILITY_JOBS[job_id] = job

    if payload.tool_name == "XL Processing":
        background_tasks.add_task(run_xl_processing_job, job_id, payload)
    else:
        set_job_status(
            job_id,
            status="queued",
            message="Job status persistence will be connected next.",
        )

    return job


@router.get("/jobs/{job_id}")
def get_utility_job(job_id: str):
    job = UTILITY_JOBS.get(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Utility job not found.",
        )

    return job