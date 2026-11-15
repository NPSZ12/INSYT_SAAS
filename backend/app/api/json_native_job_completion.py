"""Fail-closed APC-to-tracked-job completion resolver.

Pure validation. The API caller must obtain history from the
existing workspace/client/project-scoped Azure history reader.
"""

import re


class JsonSourceJobNotComplete(ValueError):
    pass



def require_completed_json_source_job_from_history(
    *,
    apc_job_id,
    history,
    normalize_job,
):
    """Apply INSYT's existing job-history normalizer before validation."""
    if not isinstance(history, dict):
        raise JsonSourceJobNotComplete(
            "Authoritative job history unavailable."
        )

    raw_jobs = history.get("jobs")
    if not isinstance(raw_jobs, list):
        raise JsonSourceJobNotComplete(
            "Authoritative job list unavailable."
        )

    if history.get("errors"):
        raise JsonSourceJobNotComplete(
            "Job history has unresolved read errors."
        )

    normalized = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            raise JsonSourceJobNotComplete(
                "Invalid job-history record."
            )
        try:
            converted = normalize_job(job)
        except Exception as exc:
            raise JsonSourceJobNotComplete(
                "Job-history normalization failed."
            ) from exc

        if not isinstance(converted, dict):
            raise JsonSourceJobNotComplete(
                "Invalid normalized job record."
            )
        normalized.append(converted)

    return require_completed_json_source_job(
        apc_job_id=apc_job_id,
        history={"jobs": normalized},
    )

def require_completed_json_source_job(
    *,
    apc_job_id,
    history,
):
    if (
        not isinstance(apc_job_id, str)
        or not re.fullmatch(
            r"[A-Za-z0-9_-]+", apc_job_id
        )
    ):
        raise JsonSourceJobNotComplete(
            "Invalid APC source job ID."
        )

    if not isinstance(history, dict):
        raise JsonSourceJobNotComplete(
            "Authoritative job history unavailable."
        )

    jobs = history.get("jobs")

    if not isinstance(jobs, list):
        raise JsonSourceJobNotComplete(
            "Authoritative job list unavailable."
        )

    matches = [
        row for row in jobs
        if isinstance(row, dict)
        and str(row.get("apc_job_id") or "").strip()
        == apc_job_id
    ]

    if len(matches) != 1:
        raise JsonSourceJobNotComplete(
            "APC job does not resolve to exactly one tracked job."
        )

    job = matches[0]
    status = str(job.get("status") or "").strip().lower()

    if status not in {
        "completed",
        "completed_with_exceptions",
    }:
        raise JsonSourceJobNotComplete(
            "APC source ingestion has not completed successfully."
        )

    tracked_job_id = str(
        job.get("job_id") or ""
    ).strip()

    if not re.fullmatch(
        r"[A-Za-z0-9_-]+", tracked_job_id
    ):
        raise JsonSourceJobNotComplete(
            "Tracked job identity missing or invalid."
        )

    return {
        "apc_job_id": apc_job_id,
        "tracked_job_id": tracked_job_id,
        "status": status,
        "completed": True,
    }