from __future__ import annotations

from ..config import Settings
from ..db import LedgerDB


def run_live_ocr_placeholder(db: LedgerDB, settings: Settings, job_id: str, matter_id: str) -> None:
    """Placeholder for the real Azure Document Intelligence OCR worker.

    The live worker should:
    - require an explicit --enable-live-ocr flag and APC_ENABLE_LIVE_OCR=true
    - submit only requires_ocr=1 files
    - persist Azure operation IDs
    - record retries, throttles, pages submitted, pages succeeded, pages failed
    - write output text/searchable PDFs to Blob Storage
    - emit one cost_event per file or per operation
    """
    raise NotImplementedError(
        "Live OCR is intentionally not implemented in v0.2. Use ocr_dry_run until credentials, approvals, and cost controls are in place."
    )
