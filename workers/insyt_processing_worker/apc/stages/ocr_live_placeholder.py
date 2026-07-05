from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any


def _get_document_intelligence_client():
    endpoint = (
        os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        or os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
        or ""
    ).strip()

    key = (
        os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        or os.getenv("AZURE_FORM_RECOGNIZER_KEY")
        or ""
    ).strip()

    if not endpoint or not key:
        raise RuntimeError(
            "Live OCR requested but Azure Document Intelligence credentials are missing. "
            "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
    except Exception as exc:
        raise RuntimeError(
            "Live OCR requested but azure-ai-documentintelligence is not installed."
        ) from exc

    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )


def _row_get(row: Any, *names: str):
    for name in names:
        try:
            value = row[name]
        except Exception:
            value = getattr(row, name, None)

        if value not in (None, ""):
            return value

    return None


def _table_columns(db, table_name: str) -> set[str]:
    try:
        rows = db.query(f"PRAGMA table_info({table_name})")
        return {str(row["name"]) for row in rows}
    except Exception:
        return set()


def _find_source_path(row: Any) -> str | None:
    value = _row_get(
        row,
        "local_path",
        "source_path",
        "file_path",
        "path",
        "expanded_path",
        "native_path",
        "original_path",
        "download_path",
    )

    return str(value) if value else None


def _find_doc_id(row: Any) -> str:
    value = _row_get(row, "doc_id", "assigned_doc_id", "document_id", "file_id", "id")
    return str(value or "UNKNOWN_DOC")


def _guess_content_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _ocr_bytes(content: bytes, content_type: str) -> tuple[str, int]:
    client = _get_document_intelligence_client()

    poller = client.begin_analyze_document(
        model_id="prebuilt-read",
        body=content,
        content_type=content_type,
    )

    result = poller.result()

    text = getattr(result, "content", "") or ""
    pages = getattr(result, "pages", []) or []

    if text:
        return text, len(pages)

    page_texts: list[str] = []
    for page in pages:
        lines = []
        for line in getattr(page, "lines", []) or []:
            line_text = getattr(line, "content", "") or ""
            if line_text:
                lines.append(line_text)

        if lines:
            page_texts.append("\n".join(lines))

    return "\n\n".join(page_texts), len(pages)


def _write_ocr_text(row: Any, source_path: str, doc_id: str, text: str) -> str:
    existing_text_path = _row_get(
        row,
        "text_path",
        "extracted_text_path",
        "ocr_text_path",
        "review_text_path",
        "output_text_path",
    )

    if existing_text_path:
        output_path = Path(str(existing_text_path))
    else:
        source = Path(source_path)
        output_dir = source.parent.parent / "text"
        output_path = output_dir / f"{doc_id}.txt"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text or "", encoding="utf-8")

    return str(output_path)


def _record_stage_start(db, job_id: str, stage_name: str):
    try:
        db.execute(
            """
            INSERT INTO processing_stage_run
                (job_id, stage_name, started_at, status, exceptions)
            VALUES (?, ?, datetime('now'), ?, ?)
            """,
            (job_id, stage_name, "running", 0),
        )
    except Exception:
        pass


def _record_stage_complete(
    db,
    job_id: str,
    stage_name: str,
    processed_count: int,
    exception_count: int,
):
    try:
        db.execute(
            """
            INSERT INTO processing_stage_run
                (job_id, stage_name, completed_at, status, processed_count, exceptions)
            VALUES (?, ?, datetime('now'), ?, ?, ?)
            """,
            (
                job_id,
                stage_name,
                "completed" if exception_count == 0 else "completed_with_exceptions",
                processed_count,
                exception_count,
            ),
        )
    except Exception:
        pass


def _update_metric_after_ocr(
    db,
    row: Any,
    metric_id: Any,
    doc_id: str,
    output_text_path: str,
    page_count: int,
):
    columns = _table_columns(db, "file_processing_metrics")

    assignments = []
    params: list[Any] = []

    for column_name in [
        "text_path",
        "extracted_text_path",
        "ocr_text_path",
        "review_text_path",
        "output_text_path",
    ]:
        if column_name in columns:
            assignments.append(f"{column_name}=?")
            params.append(output_text_path)

    if "ocr_page_count" in columns:
        assignments.append("ocr_page_count=?")
        params.append(page_count)

    if "page_count" in columns:
        assignments.append(
            "page_count=CASE WHEN coalesce(page_count,0)=0 THEN ? ELSE page_count END"
        )
        params.append(page_count)

    if "ocr_status" in columns:
        assignments.append("ocr_status=?")
        params.append("completed")

    if "requires_ocr" in columns:
        assignments.append("requires_ocr=?")
        params.append(0)

    if "text_extraction_method" in columns:
        assignments.append("text_extraction_method=?")
        params.append("azure_document_intelligence_read")

    if "ocr_engine" in columns:
        assignments.append("ocr_engine=?")
        params.append("azure_document_intelligence_read")

    if not assignments:
        return

    set_sql = ", ".join(assignments)

    if "id" in columns and metric_id is not None:
        db.execute(
            f"""
            UPDATE file_processing_metrics
            SET {set_sql}
            WHERE id=?
            """,
            tuple(params + [metric_id]),
        )
        return

    if "doc_id" in columns:
        db.execute(
            f"""
            UPDATE file_processing_metrics
            SET {set_sql}
            WHERE job_id=? AND doc_id=?
            """,
            tuple(params + [_row_get(row, "job_id"), doc_id]),
        )
        return

    if "assigned_doc_id" in columns:
        db.execute(
            f"""
            UPDATE file_processing_metrics
            SET {set_sql}
            WHERE job_id=? AND assigned_doc_id=?
            """,
            tuple(params + [_row_get(row, "job_id"), doc_id]),
        )
        return

    original_path = _row_get(row, "original_path", "source_path", "file_path", "path")
    if original_path and "original_path" in columns:
        db.execute(
            f"""
            UPDATE file_processing_metrics
            SET {set_sql}
            WHERE job_id=? AND original_path=?
            """,
            tuple(params + [_row_get(row, "job_id"), original_path]),
        )


def run_live_ocr_placeholder(db, settings, job_id: str, matter_id: str) -> dict:
    """
    Live OCR implementation for APC.

    This preserves the v0.2 function name so orchestrator.py does not need to
    change. It scans OCR-required rows from file_processing_metrics, sends the
    source file bytes to Azure Document Intelligence prebuilt-read, writes a
    .txt file next to the native output area, and updates available metric fields.
    """

    stage_name = "ocr_live"
    _record_stage_start(db, job_id, stage_name)

    columns = _table_columns(db, "file_processing_metrics")

    where_parts = ["job_id=?"]
    params: list[Any] = [job_id]

    if "is_container" in columns:
        where_parts.append("coalesce(is_container,0)=0")

    if "is_denisted" in columns:
        where_parts.append("coalesce(is_denisted,0)=0")

    if "is_duplicate" in columns:
        where_parts.append("coalesce(is_duplicate,0)=0")

    if "requires_ocr" in columns:
        where_parts.append("coalesce(requires_ocr,0)=1")

    rows = db.query(
        f"""
        SELECT *
        FROM file_processing_metrics
        WHERE {" AND ".join(where_parts)}
        """,
        tuple(params),
    )

    processed_count = 0
    exception_count = 0
    warnings: list[str] = []

    for row in rows:
        doc_id = _find_doc_id(row)
        source_path = _find_source_path(row)
        metric_id = _row_get(row, "id")

        if not source_path:
            exception_count += 1
            warnings.append(f"{doc_id}: no source path found for OCR.")
            continue

        if not Path(source_path).exists():
            exception_count += 1
            warnings.append(f"{doc_id}: source file does not exist: {source_path}")
            continue

        try:
            content = Path(source_path).read_bytes()
            content_type = _guess_content_type(source_path)
            text, page_count = _ocr_bytes(content, content_type)
            output_text_path = _write_ocr_text(row, source_path, doc_id, text)

            _update_metric_after_ocr(
                db=db,
                row=row,
                metric_id=metric_id,
                doc_id=doc_id,
                output_text_path=output_text_path,
                page_count=page_count,
            )

            processed_count += 1
        except Exception as exc:
            exception_count += 1
            warnings.append(f"{doc_id}: live OCR failed: {type(exc).__name__}: {exc}")

    _record_stage_complete(
        db=db,
        job_id=job_id,
        stage_name=stage_name,
        processed_count=processed_count,
        exception_count=exception_count,
    )

    return {
        "stage": stage_name,
        "status": "completed" if exception_count == 0 else "completed_with_exceptions",
        "processed_count": processed_count,
        "exception_count": exception_count,
        "warnings": warnings,
    }