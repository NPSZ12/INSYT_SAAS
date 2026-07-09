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


def build_master_csv(
    csv_paths: list[Path],
    output_dir: Path,
    delimiter: str,
    header_map: dict[str, str] | None = None,
):
    frames = []

    for csv_path in csv_paths:
        df = pd.read_csv(csv_path, sep=delimiter, dtype=str)
        df = clean_dataframe(df)

        if header_map:
            df.rename(columns=header_map, inplace=True)

        frames.append(df)

    if not frames:
        return None

    final_df = pd.concat(frames, ignore_index=True, sort=False)
    final_df = collapse_duplicate_columns(final_df)
    final_df = clean_dataframe(final_df)
    final_df = final_df.reindex(sorted(final_df.columns), axis=1)

    final_out = output_dir / "FINAL_MERGED_OUTPUT.csv"
    final_df.to_csv(final_out, index=False, sep=delimiter, encoding="utf-8")

    return final_out


def run_xl_processing_job(job_id: str, payload: UtilityJobRequest):
    temp_root = Path(tempfile.mkdtemp(prefix=f"xl_processing_{job_id}_"))

    try:
        workspace = payload.workspace
        project = payload.project_id
        client = payload.client

        if workspace not in VALID_WORKSPACES:
            raise ValueError("workspace must be capture, summaries, or discovery")

        container = get_workspace_container(workspace)

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

        set_job_status(
            job_id,
            status="running",
            message="XL Processing started.",
            total_files=len(selected_files),
            processed_files=0,
        )

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

        if extract_headers and merged_headers:
            headers_path = output_dir / "Merged_Headers.csv"
            pd.DataFrame(
                sorted(merged_headers),
                columns=["Header"],
            ).to_csv(headers_path, index=False, encoding="utf-8")
            output_files.append(headers_path)

        if build_master:
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
            "selected_files": selected_files,
            "processed_files": processed,
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

        set_job_status(
            job_id,
            status="completed" if not errors else "completed_with_errors",
            message="XL Processing completed.",
            output_files=uploaded_outputs,
            log_blob=log_blob,
            errors=errors,
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