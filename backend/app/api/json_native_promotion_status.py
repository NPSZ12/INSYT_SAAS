"""Validate native JSON Cyber2 intake identity for Promotion display.

Metadata validation only. Native byte integrity is verified separately
by the explicit Promotion endpoint. No Azure operations occur here.
"""

import re


PROFILES = {
    "plain",
    "slack",
    "teams",
    "salesforce",
    "google",
    "custom_api",
}

EXTENSIONS = {"json", "jsonl", "ndjson"}


def matches_native_json_intake_identity(
    intake,
    *,
    workspace,
    client,
    project,
    project_base,
    doc_id,
    extension,
    source_job_id,
    detection_job_id,
):
    if not isinstance(intake, dict):
        return False

    extension = str(extension or "").lower().lstrip(".")

    if extension not in EXTENSIONS:
        return False

    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            workspace,
            client,
            project,
            project_base,
            doc_id,
            source_job_id,
            detection_job_id,
        )
    ):
        return False

    expected = {
        "workspace": workspace,
        "client": client,
        "project": project,
        "doc_id": doc_id,
        "source_kind": "native_json",
        "source_type": "json_structured",
        "classification": "HIT",
        "source_job_id": source_job_id,
        "detection_job_id": detection_job_id,
        "source_native_path": (
            f"{project_base}/source/native/{doc_id}.{extension}"
        ),
    }

    if any(
        intake.get(key) != value
        for key, value in expected.items()
    ):
        return False

    if intake.get("source_profile") not in PROFILES:
        return False

    source_hash = str(intake.get("source_sha256") or "")

    if not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
        return False

    source_bytes = intake.get("source_bytes")

    if (
        isinstance(source_bytes, bool)
        or not isinstance(source_bytes, int)
        or source_bytes <= 0
    ):
        return False

    return True
