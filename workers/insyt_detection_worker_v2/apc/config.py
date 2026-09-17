from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("APC_DB_PATH", "./apc.local.db")
    azure_region: str = os.getenv("APC_AZURE_REGION", "eastus")

    fallback_ocr_read_price_per_1000_pages: float = _float_env(
        "APC_FALLBACK_OCR_READ_PRICE_PER_1000_PAGES", 1.50
    )
    fallback_containerapps_vcpu_second_price: float = _float_env(
        "APC_FALLBACK_CONTAINERAPPS_VCPU_SECOND_PRICE", 0.000024
    )
    fallback_containerapps_memory_gib_second_price: float = _float_env(
        "APC_FALLBACK_CONTAINERAPPS_MEMORY_GIB_SECOND_PRICE", 0.000003
    )
    fallback_blob_write_10k_price: float = _float_env(
        "APC_FALLBACK_BLOB_WRITE_10K_PRICE", 0.055
    )
    fallback_blob_read_10k_price: float = _float_env(
        "APC_FALLBACK_BLOB_READ_10K_PRICE", 0.0044
    )

    worker_vcpu: float = _float_env("APC_WORKER_VCPU", 1.0)
    worker_memory_gib: float = _float_env("APC_WORKER_MEMORY_GIB", 2.0)

    ocr_low_text_bytes_threshold: int = int(_float_env("APC_OCR_LOW_TEXT_BYTES_THRESHOLD", 64))
    ocr_estimated_scanned_pdf_bytes_per_page: int = int(
        _float_env("APC_OCR_ESTIMATED_SCANNED_PDF_BYTES_PER_PAGE", 100000)
    )

    enable_live_ocr: bool = (
        _bool_env("APC_ENABLE_LIVE_OCR", False)
        or _bool_env("APC_API_ALLOW_LIVE_OCR", False)
    )
    document_intelligence_endpoint: str = os.getenv("APC_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    document_intelligence_key: str = os.getenv("APC_DOCUMENT_INTELLIGENCE_KEY", "")


DEFAULT_SETTINGS = Settings()
