import io
import json
import uuid
from datetime import datetime

import pandas as pd

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Body
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.models import CapturedEntity


router = APIRouter(
    prefix="/api/tools",
    tags=["merge-dedupe"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    filename = (file.filename or "").lower()
    content = file.file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded file is empty: {file.filename}",
        )

    buffer = io.BytesIO(content)

    try:
        if filename.endswith(".csv"):
            return pd.read_csv(buffer, dtype=str).fillna("")

        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            return pd.read_excel(buffer, dtype=str).fillna("")

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read {file.filename}: {type(e).__name__}: {e}",
        )

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {file.filename}. Upload CSV, XLSX, or XLS.",
    )


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [
        str(col)
        .strip()
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        for col in df.columns
    ]

    return df


def normalize_key(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace(".", "")
    )


def find_doc_id_column(df: pd.DataFrame) -> str:
    possible_names = [
        "Doc ID",
        "DocID",
        "Document ID",
        "DocumentID",
        "Control Number",
        "ControlNumber",
        "BegDoc",
        "Begin Doc",
        "BeginDoc",
        "Beginning Doc",
        "Document Number",
        "DocumentNumber",
        "Doc Number",
        "DocNumber",
    ]

    normalized_columns = {
        normalize_key(col): col
        for col in df.columns
    }

    for name in possible_names:
        key = normalize_key(name)

        if key in normalized_columns:
            return normalized_columns[key]

    raise HTTPException(
        status_code=400,
        detail=(
            "No Doc ID column found. Include one column named Doc ID, "
            "Document ID, Control Number, BegDoc, Begin Doc, or Document Number."
        ),
    )


def clean_cell(value) -> str:
    if value is None:
        return ""

    value = str(value)

    if value.lower() == "nan":
        return ""

    return value.strip()

def parse_values_json(raw_values: str) -> dict:
    if not raw_values:
        return {}

    try:
        parsed = json.loads(raw_values)

        if isinstance(parsed, dict):
            return parsed

        return {}

    except Exception:
        return {}


def concat_unique(values: list[str]) -> str:
    cleaned = []

    for value in values:
        value = clean_cell(value)

        if not value:
            continue

        parts = [
            part.strip()
            for part in value.replace("\n", ";").split(";")
            if part.strip()
        ]

        for part in parts:
            if part not in cleaned:
                cleaned.append(part)

    return "; ".join(cleaned)


@router.post("/captured-entities/merge-selected-headers")
def merge_captured_entities_by_selected_headers(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    project_id = payload.get("project_id")
    merge_headers = payload.get("merge_headers", [])
    captured_by = payload.get("captured_by", "CYBER2_MERGE")
    replace_existing = payload.get("replace_existing", False)

    if not project_id:
        raise HTTPException(
            status_code=400,
            detail="project_id is required.",
        )

    if not merge_headers or not isinstance(merge_headers, list):
        raise HTTPException(
            status_code=400,
            detail="merge_headers must be a non-empty list.",
        )

    entities = (
        db.query(CapturedEntity)
        .filter(CapturedEntity.project_id == project_id)
        .filter(CapturedEntity.linked == "true")
        .all()
    )

    if not entities:
        raise HTTPException(
            status_code=404,
            detail="No captured entities found for this project.",
        )

    grouped = {}

    for entity in entities:
        values = parse_values_json(entity.values)

        key_parts = []

        for header in merge_headers:
            key_parts.append(clean_cell(values.get(header, "")))

        if not any(key_parts):
            continue

        group_key = tuple(key_parts)

        if group_key not in grouped:
            grouped[group_key] = []

        grouped[group_key].append(
            {
                "entity": entity,
                "values": values,
            }
        )

    merge_group = f"CYBER2_MERGE_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    merged_count = 0
    source_rows_used = 0

    for group_key, group_items in grouped.items():
        if len(group_items) < 2:
            continue

        all_headers = set()

        for item in group_items:
            all_headers.update(item["values"].keys())

        merged_values = {}

        for header in sorted(all_headers):
            column_values = [
                item["values"].get(header, "")
                for item in group_items
            ]

            if header in merge_headers:
                merged_values[header] = concat_unique(column_values)
            else:
                merged_values[header] = concat_unique(column_values)

        merged_doc_ids = concat_unique(
            [
                item["entity"].doc_id
                for item in group_items
            ]
        )

        merged_batch_ids = concat_unique(
            [
                item["entity"].batch_id
                for item in group_items
            ]
        )

        source_entity_ids = concat_unique(
            [
                str(item["entity"].id)
                for item in group_items
            ]
        )

        merged_values["Merged Doc IDs"] = merged_doc_ids
        merged_values["Source Entity IDs"] = source_entity_ids
        merged_values["Merge Headers"] = "; ".join(merge_headers)

        new_entity = CapturedEntity(
            project_id=project_id,
            batch_id=merged_batch_ids or "CYBER2_MERGED",
            doc_id=merged_doc_ids,
            captured_by=captured_by,
            linked="true",
            values=json.dumps(merged_values),
            source_type="CYBER2_MERGED",
            source_file="Captured Entities",
            source_row=0,
            import_group=merge_group,
        )

        db.add(new_entity)

        if replace_existing:
            for item in group_items:
                item["entity"].linked = "false"

        merged_count += 1
        source_rows_used += len(group_items)

    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "source_type": "CYBER2_MERGED",
        "merge_group": merge_group,
        "merge_headers": merge_headers,
        "merged_rows_created": merged_count,
        "source_rows_used": source_rows_used,
        "replace_existing": replace_existing,
        "message": f"{merged_count} merged captured entity rows created.",
    }


@router.post("/merge-dedupe/import-captured-entities")
async def import_merge_dedupe_to_captured_entities(
    project_id: str = Form(...),
    batch_id: str = Form("XL_MAPPED"),
    captured_by: str = Form("XL_IMPORT"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files uploaded.",
        )

    frames = []

    for file in files:
        df = read_uploaded_file(file)
        df = normalize_columns(df)

        if df.empty:
            continue

        df["Source File"] = file.filename or ""
        frames.append(df)

    if not frames:
        raise HTTPException(
            status_code=400,
            detail="No usable rows found in uploaded files.",
        )

    merged = pd.concat(frames, ignore_index=True, sort=False).fillna("")

    before_count = len(merged)

    deduped = merged.drop_duplicates().reset_index(drop=True)

    after_count = len(deduped)
    removed_count = before_count - after_count

    doc_id_column = find_doc_id_column(deduped)

    import_group = f"XL_IMPORT_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    imported_count = 0
    skipped_count = 0

    excluded_columns = {
        normalize_key(doc_id_column),
        normalize_key("Source File"),
    }

    for row_index, row in deduped.iterrows():
        doc_id = clean_cell(row.get(doc_id_column, ""))

        if not doc_id:
            skipped_count += 1
            continue

        source_file = clean_cell(row.get("Source File", ""))

        values = {}

        for col in deduped.columns:
            if normalize_key(col) in excluded_columns:
                continue

            cell_value = clean_cell(row.get(col, ""))

            if cell_value:
                values[str(col)] = cell_value

        if not values:
            skipped_count += 1
            continue

        entity = CapturedEntity(
            project_id=project_id,
            batch_id=batch_id,
            doc_id=doc_id,
            captured_by=captured_by,
            linked="true",
            values=json.dumps(values),
            source_type="XL_MAPPED",
            source_file=source_file,
            source_row=int(row_index) + 2,
            import_group=import_group,
        )

        db.add(entity)
        imported_count += 1

    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "batch_id": batch_id,
        "source_type": "XL_MAPPED",
        "import_group": import_group,
        "input_rows": before_count,
        "deduped_rows": after_count,
        "duplicates_removed": removed_count,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "message": f"{imported_count} XL-mapped captured entities imported.",
    }