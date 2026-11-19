"""Native JSON promotion eligibility and path contract.

Pure validation only. No Azure reads, writes, or promotion.
Existing workbook/CSV promotion behavior is not modified.
"""

import re


class JsonPromotionNotEligible(ValueError):
    pass


def prepare_json_native_promotion(
    *,
    row,
    base_path,
    source_job_status,
):
    if not isinstance(row, dict):
        raise JsonPromotionNotEligible("Missing document record.")

    if source_job_status not in {
        "completed",
        "completed_with_exceptions",
    }:
        raise JsonPromotionNotEligible(
            "Source ingestion is not complete."
        )

    if str(row.get("classification") or "").upper() != "HIT":
        raise JsonPromotionNotEligible(
            "Document requires a completed HIT classification."
        )

    if str(row.get("destination") or "") != "json_cyber2":
        raise JsonPromotionNotEligible(
            "Document is not routed to Cyber2."
        )

    if row.get("cyber2_sent"):
        raise JsonPromotionNotEligible(
            "Document is already registered in Cyber2."
        )

    extension = str(
        row.get("extension") or ""
    ).lower().lstrip(".")

    if extension not in {"json", "jsonl", "ndjson"}:
        raise JsonPromotionNotEligible(
            "Not a supported native JSON document."
        )

    source_type = str(row.get("source_type") or "").lower()
    source_format = str(row.get("source_format") or "").lower()

    if (
        source_type != "json_structured"
        and source_format not in {"json", "jsonl", "ndjson"}
    ):
        raise JsonPromotionNotEligible(
            "Missing structured JSON source classification."
        )

    doc_id = str(row.get("doc_id") or "")
    job_id = str(row.get("source_job_id") or "")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", doc_id):
        raise JsonPromotionNotEligible("Invalid Doc ID.")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise JsonPromotionNotEligible("Invalid source job ID.")

    if (
        not isinstance(base_path, str)
        or not base_path
        or base_path.startswith("/")
        or base_path.endswith("/")
        or "\\" in base_path
        or any(
            part in {"", ".", ".."}
            for part in base_path.split("/")
        )
    ):
        raise JsonPromotionNotEligible(
            "Invalid project storage path."
        )

    filename = f"{doc_id}.{extension}"

    expected_staged_path = (
        f"{base_path}/processing_center/staged/"
        f"{job_id}/native/{filename}"
    )

    recorded_staged_path = str(
        row.get("native_staged_blob_path") or ""
    ).strip()

    if recorded_staged_path != expected_staged_path:
        raise JsonPromotionNotEligible(
            "Authoritative native JSON staging path mismatch."
        )

    return {
        "doc_id": doc_id,
        "source_job_id": job_id,
        "extension": extension,
        "staged_native_path": recorded_staged_path,
        "final_native_path": (
            f"{base_path}/source/native/{filename}"
        ),
        "cyber2_intake_path": (
            f"{base_path}/cyber2/intake/documents/"
            f"{doc_id}.json"
        ),
        "source_kind": "native_json",
        "requires_manual_promotion": True,
        "generate_csv": False,
    }