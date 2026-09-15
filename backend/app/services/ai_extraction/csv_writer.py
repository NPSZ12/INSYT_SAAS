from __future__ import annotations

import csv
import io
from typing import Any

from .models import AiExtractionRow


PROVENANCE_COLUMNS = [
    "INSYT_AI_Entity_ID",
    "INSYT_Processing_Set_ID",
    "INSYT_Source_Job_ID",
    "INSYT_Source_File_ID",
    "INSYT_Source_Doc_ID",
    "INSYT_Source_Filename",
    "INSYT_Source_Page",
    "INSYT_Source_Record_ID",
    "INSYT_Source_Field",
    "INSYT_Source_Text",
    "INSYT_Detection_Job_ID",
    "INSYT_Extraction_Confidence",
]


def build_ai_extraction_csv(
    rows: list[AiExtractionRow],
) -> bytes:
    dynamic_columns: list[str] = []
    seen_dynamic: set[str] = set()

    for row in rows:
        for key in row.extracted_values:
            clean_key = str(key or "").strip()

            if (
                not clean_key
                or clean_key in seen_dynamic
            ):
                continue

            seen_dynamic.add(clean_key)
            dynamic_columns.append(clean_key)

    fieldnames = [
        *PROVENANCE_COLUMNS,
        *dynamic_columns,
    ]

    buffer = io.StringIO(
        newline=""
    )

    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
    )

    writer.writeheader()

    for row in rows:
        output: dict[str, Any] = {
            "INSYT_AI_Entity_ID":
                row.ai_entity_id,
            "INSYT_Processing_Set_ID":
                row.processing_set_id,
            "INSYT_Source_Job_ID":
                row.source_job_id,
            "INSYT_Source_File_ID":
                row.source_file_id,
            "INSYT_Source_Doc_ID":
                row.source_doc_id,
            "INSYT_Source_Filename":
                row.source_filename,
            "INSYT_Source_Page":
                row.source_page or "",
            "INSYT_Source_Record_ID":
                row.source_record_id,
            "INSYT_Source_Field":
                row.source_field,
            "INSYT_Source_Text":
                row.source_text,
            "INSYT_Detection_Job_ID":
                row.detection_job_id,
            "INSYT_Extraction_Confidence":
                (
                    row.extraction_confidence
                    if row.extraction_confidence
                    is not None
                    else ""
                ),
        }

        output.update(
            row.extracted_values
        )

        writer.writerow(output)

    return buffer.getvalue().encode(
        "utf-8-sig"
    )