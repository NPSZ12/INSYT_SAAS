from __future__ import annotations

from pathlib import Path

from ..base import AdapterContext, AdapterResult
from ...pdf_utils import (
    count_pdf_pages,
    estimate_pdf_native_text_bytes,
    pdf_is_encrypted,
)


class PdfAdapter:
    """
    Read-only PDF preparation and classification.

    Does not modify the PDF, create child documents,
    perform OCR, assign Doc IDs, or write to APC tables.

    PDF remains a normal reviewable leaf document.
    """

    name = "pdf"
    extensions = (".pdf",)

    def process(
        self,
        context: AdapterContext,
    ) -> AdapterResult:

        source = Path(context.source_path)

        if not source.is_file():
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error="PDF_SOURCE_MISSING",
            )

        try:
            source_bytes = source.stat().st_size

            if source_bytes == 0:
                return AdapterResult(
                    adapter_name=self.name,
                    handled=True,
                    status="failed",
                    source_file_id=context.file_id,
                    error="PDF_EMPTY_FILE",
                )

            with source.open("rb") as stream:
                signature = stream.read(1024)

            if b"%PDF-" not in signature:
                return AdapterResult(
                    adapter_name=self.name,
                    handled=True,
                    status="failed",
                    source_file_id=context.file_id,
                    error="PDF_INVALID_SIGNATURE",
                )

            # PDF_BOUNDED_STRUCTURAL_PROBE_V1
            # Parsing occurs outside the main processing worker.
            import json
            import os
            import subprocess
            import sys

            structural_status = "parser_unavailable"
            structural_pages = None
            parser_encrypted = False
            structural_warning = None

            probe_path = Path(__file__).with_name(
                "pdf_structural_probe.py"
            )

            timeout_seconds = max(
                1.0,
                min(
                    120.0,
                    float(os.getenv(
                        "INSYT_PDF_PROBE_TIMEOUT_SECONDS", "20"
                    )),
                ),
            )

            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(probe_path),
                        str(source),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )

                if completed.returncode != 0:
                    raise RuntimeError(
                        "PDF_PROBE_PROCESS_FAILED"
                    )

                probe_result = json.loads(
                    completed.stdout
                )

                if not isinstance(probe_result, dict):
                    raise ValueError(
                        "PDF_PROBE_INVALID_RESULT"
                    )

                structural_status = str(
                    probe_result.get("status") or ""
                )

                if structural_status == "parser_unavailable":
                    structural_warning = (
                        "PDF_PARSER_UNAVAILABLE"
                    )

                elif structural_status == "encrypted":
                    parser_encrypted = True

                elif structural_status == "validated":
                    structural_pages = int(
                        probe_result["pages"]
                    )

                    if structural_pages <= 0:
                        raise ValueError(
                            "PDF_PROBE_INVALID_PAGE_COUNT"
                        )

                elif structural_status == "failed":
                    return AdapterResult(
                        adapter_name=self.name,
                        handled=True,
                        status="failed",
                        source_file_id=context.file_id,
                        error=(
                            "PDF_STRUCTURAL_VALIDATION_FAILED:"
                            + str(
                                probe_result.get("error_type")
                                or "Unknown"
                            )
                        ),
                        metadata={
                            "remediation_reason":
                                "PDF_STRUCTURAL_VALIDATION_FAILED",
                            "pdf_remains_reviewable_leaf": True,
                        },
                    )

                else:
                    raise ValueError(
                        "PDF_PROBE_UNKNOWN_STATUS"
                    )

            except subprocess.TimeoutExpired:
                return AdapterResult(
                    adapter_name=self.name,
                    handled=True,
                    status="failed",
                    source_file_id=context.file_id,
                    error="PDF_STRUCTURAL_INSPECTION_TIMEOUT",
                    metadata={
                        "remediation_reason":
                            "PDF_STRUCTURAL_INSPECTION_TIMEOUT",
                        "pdf_remains_reviewable_leaf": True,
                    },
                )

            except Exception as exc:
                return AdapterResult(
                    adapter_name=self.name,
                    handled=True,
                    status="failed",
                    source_file_id=context.file_id,
                    error=(
                        "PDF_STRUCTURAL_PROBE_FAILED:"
                        f"{type(exc).__name__}"
                    ),
                    metadata={
                        "remediation_reason":
                            "PDF_STRUCTURAL_PROBE_FAILED",
                        "pdf_remains_reviewable_leaf": True,
                    },
                )

            page_count, page_confidence = (
                count_pdf_pages(source)
            )

            text_bytes, text_signal = (
                estimate_pdf_native_text_bytes(source)
            )

            encrypted_signal = (
                parser_encrypted or pdf_is_encrypted(source)
            )

            inspection_uncertain = (
                structural_status == "parser_unavailable"
                or structural_warning is not None
                or
                page_confidence in {
                    "low", "timeout", "failed", "not_pdf"
                }
                or text_signal in {
                    "failed", "inspection_timeout"
                }
            )

            metadata = {
                "source_bytes": source_bytes,
                "structural_status": structural_status,
                "structural_page_count": structural_pages,
                "structural_warning": structural_warning,
                "page_count_estimate": page_count,
                "page_count_confidence": page_confidence,
                "native_text_bytes_estimate": text_bytes,
                "native_text_signal": text_signal,
                "encryption_marker_detected": encrypted_signal,
                "encryption_check_authoritative": (
                    structural_status != "parser_unavailable"
                ),
                "inspection_uncertain": inspection_uncertain,
                "pdf_original_preserved": True,
                "pdf_remains_reviewable_leaf": True,
            }

            if encrypted_signal:
                metadata["remediation_reason"] = (
                    "PDF_ENCRYPTION_REVIEW_REQUIRED"
                )

                return AdapterResult(
                    adapter_name=self.name,
                    handled=True,
                    status="completed_with_warnings",
                    source_file_id=context.file_id,
                    metadata=metadata,
                    requires_ocr=None,
                    resume_stage="post_expansion",
                )

            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status=(
                    "completed_with_warnings"
                    if inspection_uncertain
                    else "completed"
                ),
                source_file_id=context.file_id,
                requires_ocr=None,
                resume_stage="post_expansion",
                metadata=metadata,
            )

        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error=(
                    "PDF_INSPECTION_FAILED:"
                    f"{type(exc).__name__}"
                ),
            )


PDF_ADAPTER = PdfAdapter()
