import io
import pandas as pd

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(
    prefix="/api/tools",
    tags=["merge-dedupe"],
)


def read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    filename = file.filename.lower()

    content = file.file.read()
    buffer = io.BytesIO(content)

    if filename.endswith(".csv"):
        return pd.read_csv(buffer, dtype=str).fillna("")

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        return pd.read_excel(buffer, dtype=str).fillna("")

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type: {file.filename}",
    )


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [
        str(col)
        .strip()
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("  ", " ")
        for col in df.columns
    ]

    return df


@router.post("/merge-dedupe")
async def merge_dedupe_files(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    frames = []

    for file in files:
        df = read_uploaded_file(file)
        df = normalize_columns(df)
        df["Source File"] = file.filename
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True, sort=False).fillna("")

    before_count = len(merged)

    deduped = merged.drop_duplicates()

    after_count = len(deduped)
    removed_count = before_count - after_count

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        deduped.to_excel(writer, index=False, sheet_name="Merged Deduped")

        summary = pd.DataFrame(
            [
                {"Metric": "Input Rows", "Value": before_count},
                {"Metric": "Output Rows", "Value": after_count},
                {"Metric": "Duplicates Removed", "Value": removed_count},
                {"Metric": "Files Processed", "Value": len(files)},
            ]
        )

        summary.to_excel(writer, index=False, sheet_name="Summary")

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=INSYT_Merge_Dedupe_Output.xlsx"
        },
    )