from __future__ import annotations
from ..util import json_dumps
from ..telemetry import StageRunner

import io
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

def _prepare_image_for_ocr(
    content: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    """
    Prepare oversized raster images for Azure Document Intelligence OCR.

    The original source file is never modified. Any resizing/compression is
    performed entirely in memory and is used only for the OCR request.
    """

    max_ocr_bytes = 3_500_000

    if len(content) <= max_ocr_bytes:
        return content, content_type

    normalized_type = (content_type or "").lower()

    if normalized_type not in {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/bmp",
        "image/webp",
    }:
        return content, content_type

    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            "Oversized OCR image requires Pillow for automatic image "
            "compression, but Pillow is not installed."
        ) from exc

    with Image.open(io.BytesIO(content)) as image:
        image.load()

        # Azure OCR does not need the full resolution of extremely large
        # raster images. Reduce oversized dimensions while maintaining the
        # original aspect ratio.
        max_dimension = 8000

        width, height = image.size
        largest_dimension = max(width, height)

        if largest_dimension > max_dimension:
            scale = max_dimension / float(largest_dimension)
            new_size = (
                max(1, int(width * scale)),
                max(1, int(height * scale)),
            )

            image = image.resize(
                new_size,
                Image.Resampling.LANCZOS,
            )

        # JPEG is substantially smaller than large PNG/BMP/TIFF images and is
        # well suited to the temporary working copy used for OCR.
        if image.mode not in ("RGB", "L"):
            if "A" in image.getbands():
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image, mask=alpha)
                image = background
            else:
                image = image.convert("RGB")

        if image.mode == "L":
            image = image.convert("RGB")

        for quality in (90, 85, 80, 75, 70, 65, 60):
            buffer = io.BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
            )

            prepared = buffer.getvalue()

            if len(prepared) <= max_ocr_bytes:
                return prepared, "image/jpeg"

        # If JPEG quality reduction alone is insufficient, progressively
        # reduce the dimensions until the working copy falls below the OCR
        # request threshold.
        working_image = image

        while len(prepared) > max_ocr_bytes:
            width, height = working_image.size

            if width <= 1000 or height <= 1000:
                break

            working_image = working_image.resize(
                (
                    max(1, int(width * 0.8)),
                    max(1, int(height * 0.8)),
                ),
                Image.Resampling.LANCZOS,
            )

            buffer = io.BytesIO()
            working_image.save(
                buffer,
                format="JPEG",
                quality=75,
                optimize=True,
            )

            prepared = buffer.getvalue()

        if len(prepared) > max_ocr_bytes:
            raise RuntimeError(
                "Unable to reduce OCR image below the Azure request size "
                f"threshold. Prepared size: {len(prepared)} bytes."
            )

        return prepared, "image/jpeg"

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
        
    if "stage_status_json" in columns:
        assignments.append(
            "stage_status_json=json_patch("
            "coalesce(stage_status_json, '{}'), ?)"
        )
        params.append(
            json_dumps(
                {
                    "ocr_live": {
                        "status": "completed",
                        "text_path": output_text_path,
                        "page_count": page_count,
                        "engine": "azure_document_intelligence_read",
                    }
                }
            )
        )

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

    Processes OCR-required documents through Azure Document Intelligence
    prebuilt-read, stores the resulting OCR text, updates document metrics,
    and records actual OCR page usage against current Azure retail pricing.
    """

    stage_name = "ocr_live"

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
    actual_ocr_pages = 0
    warnings: list[str] = []

    with StageRunner(
        db,
        settings,
        job_id,
        matter_id,
        stage_name,
        "azure-document-intelligence-prebuilt-read",
    ) as stage:

        stage.metrics.files_in = len(rows)
        stage.metrics.documents_in = len(rows)

        for row in rows:
            doc_id = _find_doc_id(row)
            source_path = _find_source_path(row)
            metric_id = _row_get(row, "id")
            file_id = _row_get(row, "file_id")

            if not source_path:
                exception_count += 1
                warnings.append(
                    f"{doc_id}: no source path found for OCR."
                )
                continue

            if not Path(source_path).exists():
                exception_count += 1
                warnings.append(
                    f"{doc_id}: source file does not exist: {source_path}"
                )
                continue

            try:
                content = Path(source_path).read_bytes()
                content_type = _guess_content_type(source_path)

                content, content_type = _prepare_image_for_ocr(
                    content,
                    content_type,
                )

                text, page_count = _ocr_bytes(
                    content,
                    content_type,
                )

                if not (text or "").strip():
                    raise RuntimeError(
                        "Azure Document Intelligence completed the OCR request "
                        "but returned no recognized text."
                    )

                output_text_path = _write_ocr_text(
                    row,
                    source_path,
                    doc_id,
                    text,
                )

                _update_metric_after_ocr(
                    db=db,
                    row=row,
                    metric_id=metric_id,
                    doc_id=doc_id,
                    output_text_path=output_text_path,
                    page_count=page_count,
                )

                #
                # Ledger the ACTUAL pages returned by Azure Document
                # Intelligence. PricingEngine resolves the current regional
                # standard Read rate from the Azure Retail Prices API.
                #
                if page_count > 0:
                    stage.quote_cost(
                        azure_service="Azure Document Intelligence",
                        meter_name="Read Pages",
                        quantity=float(page_count),
                        unit="pages",
                        file_id=str(file_id) if file_id else None,
                        confidence_note=(
                            "Actual pages returned by Azure Document "
                            "Intelligence prebuilt-read; rate resolved from "
                            "current Azure retail pricing when available."
                        ),
                        cost_type="estimated",
                    )

                actual_ocr_pages += int(page_count or 0)
                processed_count += 1

            except Exception as exc:
                exception_count += 1
                warnings.append(
                    f"{doc_id}: live OCR failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        stage.metrics.files_out = processed_count
        stage.metrics.documents_out = processed_count
        stage.metrics.pages_out = actual_ocr_pages
        stage.metrics.exceptions = exception_count

        stage.metrics.extra.update(
            {
                "ocr_engine": "azure_document_intelligence_read",
                "model_id": "prebuilt-read",
                "processed_count": processed_count,
                "actual_ocr_pages": actual_ocr_pages,
                "exception_count": exception_count,
                "warnings": warnings[:50],
                "pricing_basis": "actual_ocr_pages",
            }
        )

    return {
        "stage": stage_name,
        "status": (
            "completed"
            if exception_count == 0
            else "completed_with_exceptions"
        ),
        "processed_count": processed_count,
        "page_count": actual_ocr_pages,
        "exception_count": exception_count,
        "warnings": warnings,
    }