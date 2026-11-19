"""Verified, non-mutating native JSON Cyber2 intake contract."""

import hashlib
import re

from .promotion_profile import classify_promoted_json

JSON_EXTENSIONS = {"json", "jsonl", "ndjson"}


def build_native_json_intake_record(
    *,
    workspace,
    client,
    project,
    project_base,
    doc_id,
    native_path,
    native_bytes,
    expected_source_sha256,
    original_filename,
    source_row,
):
    """Build an index only from previously verified Files native bytes."""
    if workspace not in {"capture", "discovery"}:
        raise ValueError("Unsupported workspace.")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(doc_id or "")):
        raise ValueError("Invalid Doc ID.")

    if not isinstance(source_row, dict):
        raise ValueError("Missing source provenance.")

    extension = str(native_path).rsplit(".", 1)[-1].lower()
    if extension not in JSON_EXTENSIONS:
        raise ValueError("Not a native JSON file.")

    expected_path = (
        f"{project_base}/source/native/{doc_id}.{extension}"
    )
    if native_path != expected_path:
        raise ValueError("Native path or Doc ID mismatch.")

    if not isinstance(native_bytes, bytes) or not native_bytes:
        raise ValueError("Missing native bytes.")

    actual_sha = hashlib.sha256(native_bytes).hexdigest()
    if (
        not re.fullmatch(
            r"[0-9a-fA-F]{64}",
            str(expected_source_sha256 or ""),
        )
        or actual_sha != str(expected_source_sha256).lower()
    ):
        raise ValueError("Native source SHA256 mismatch.")

    if str(source_row.get("doc_id") or "") != doc_id:
        raise ValueError("Source row Doc ID mismatch.")

    if str(source_row.get("classification") or "").upper() != "HIT":
        raise ValueError("Document is not a confirmed HIT.")

    if not str(source_row.get("source_job_id") or "").strip():
        raise ValueError("Missing source APC job.")

    if not str(source_row.get("detection_job_id") or "").strip():
        raise ValueError("Missing Detection V2 job.")

    profile = classify_promoted_json(
        source_bytes=native_bytes,
        original_filename=original_filename,
        source_extension=extension,
    )

    return {
        "schema_version": 1,
        "workspace": workspace,
        "client": client,
        "project": project,
        "doc_id": doc_id,
        "file_id": source_row.get("file_id"),
        "status": "ready",
        "destination": "cyber2",
        "source_kind": "native_json",
        "source_type": "json_structured",
        "source_format": extension,
        "source_profile": profile,
        "source_family": source_row.get("source_family"),
        "structured_source": source_row.get("structured_source") or {},
        "original_filename": original_filename,
        "original_json_filename": original_filename,
        "source_job_id": source_row["source_job_id"],
        "detection_job_id": source_row["detection_job_id"],
        "detection_run_id": source_row.get("detection_run_id"),
        "classification": "HIT",
        "source_native_path": native_path,
        "source_sha256": actual_sha,
        "source_bytes": len(native_bytes),
        "source_csv_path": None,
        "csv_generation_status": "not_started",
        "intake_index_path": (
            f"{project_base}/cyber2/intake/documents/{doc_id}.json"
        ),
    }


def verify_existing_native_json_intake(existing, expected):
    """True only when an existing index matches the verified source."""
    if not isinstance(existing, dict):
        raise ValueError("Existing Cyber2 index is invalid.")

    keys = (
        "workspace", "client", "project", "doc_id",
        "source_kind", "source_type", "source_format",
        "source_profile", "source_native_path", "source_sha256",
        "source_bytes", "source_job_id", "detection_job_id",
    )

    for key in keys:
        if existing.get(key) != expected.get(key):
            raise ValueError(f"Conflicting Cyber2 intake field: {key}")

    if existing.get("source_csv_path") not in (None, ""):
        raise ValueError("Existing index contains a CSV path.")

    return True
