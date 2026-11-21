"""Classify native JSON bytes only at the explicit manual C2 promotion gate.

No filename hints, source writes, schema changes, or CSV generation. JSONL and
NDJSON are sampled incrementally to avoid decoding the entire input.
"""
import io
import json
from pathlib import Path

from .json_detector import detect_json_profile

EXTENSIONS = {".json", ".jsonl", ".ndjson"}
MAX_SAMPLE_RECORDS = 64
MAX_SAMPLE_BYTES = 2 * 1024 * 1024


def classify_promoted_json(source_bytes: bytes, original_filename: str, source_extension: str) -> str:
    extension = str(source_extension or "").strip().lower()
    if extension and not extension.startswith("."):
        extension = "." + extension
    if extension not in EXTENSIONS:
        raise ValueError("Unsupported native JSON extension.")
    if not source_bytes:
        raise ValueError("Empty native JSON source.")
    # original_filename deliberately unused: source extension chooses parser only.
    del original_filename
    try:
        if extension == ".json":
            payload = json.loads(source_bytes.decode("utf-8-sig"))
            return detect_json_profile(source_path=Path("source.json"), payload=payload)
        sampled_records = 0
        sampled_bytes = 0
        generic_plain = False
        # BytesIO does not allocate a decoded copy of the entire native source.
        for line in io.BytesIO(source_bytes):
            if not line.strip():
                continue
            if sampled_records >= MAX_SAMPLE_RECORDS or sampled_bytes >= MAX_SAMPLE_BYTES:
                break
            sampled_bytes += len(line)
            sampled_records += 1
            payload = json.loads(line.decode("utf-8-sig"))
            profile = detect_json_profile(source_path=Path("source.json"), payload=payload)
            if profile in {"slack", "salesforce", "teams", "google"}:
                return profile  # decisive evidence: never scan subsequent records
            if profile == "plain":
                generic_plain = True
        if not sampled_records:
            raise ValueError("No JSON records.")
        return "plain" if generic_plain else "custom_api"
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid native JSON.") from exc
