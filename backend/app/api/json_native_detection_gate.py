"""Fail-closed native JSON Detection completion gate.

Validation only; does not modify Detection V2 or source files.
"""


class JsonDetectionNotComplete(ValueError):
    pass


def require_completed_json_detection(
    *,
    doc_id,
    source_job_id,
    detection_job_id,
    document_index,
    detection_status,
):
    if not isinstance(document_index, dict):
        raise JsonDetectionNotComplete(
            "Canonical document index unavailable."
        )

    if not isinstance(detection_status, dict):
        raise JsonDetectionNotComplete(
            "Detection job status unavailable."
        )

    if str(document_index.get("doc_id") or "") != doc_id:
        raise JsonDetectionNotComplete(
            "Detection Doc ID mismatch."
        )

    if str(
        document_index.get("source_job_id") or ""
    ) != source_job_id:
        raise JsonDetectionNotComplete(
            "Detection source job mismatch."
        )

    if str(
        document_index.get("latest_detection_job_id") or ""
    ) != detection_job_id:
        raise JsonDetectionNotComplete(
            "Detection job is not the current document run."
        )

    if str(
        document_index.get("classification") or ""
    ).strip().upper() != "HIT":
        raise JsonDetectionNotComplete(
            "Current document is not classified HIT."
        )

    status_id = detection_status.get("detection_job_id")

    if status_id and str(status_id) != detection_job_id:
        raise JsonDetectionNotComplete(
            "Detection status identity mismatch."
        )

    status = str(
        detection_status.get("status") or ""
    ).strip().lower()

    if status != "completed":
        raise JsonDetectionNotComplete(
            "Detection job has not completed successfully."
        )

    return {
        "doc_id": doc_id,
        "source_job_id": source_job_id,
        "detection_job_id": detection_job_id,
        "classification": "HIT",
        "status": status,
        "verified": True,
    }