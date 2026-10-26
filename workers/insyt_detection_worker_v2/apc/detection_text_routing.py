from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionTextRoute:
    storage_source: str
    container: str
    blob_path: str


def resolve_detection_text_route(
    *,
    workspace: str,
    blob_path: str,
    processing_container: str,
    review_container: str,
    client: str = "",
    project: str = "",
    source_job_id: str = "",
    doc_id: str = "",
) -> DetectionTextRoute:
    """
    Shared Capture/Discovery text routing.

    Review-staged text -> workspace review container.
    Existing processing-specific text -> processing container.

    Never silently retry against a different account.
    """

    workspace = str(workspace or "").strip().lower()
    path = str(blob_path or "").strip().replace("\\\\", "/")

    if workspace not in {"capture", "discovery", "summaries"}:
        raise ValueError("Unsupported Detection workspace")

    if not path or path.startswith("/"):
        raise ValueError("Invalid Detection text blob path")

    parts = path.split("/")

    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe Detection text blob path")

    staged_marker = "/processing_center/staged/"

    if staged_marker in path:
        if not client or not project or not source_job_id:
            raise ValueError(
                "Review-staged text requires source-job identity"
            )

        clean_client = str(client).strip().strip("/")
        clean_project = (
            str(project).strip().strip("/").replace(" ", "_")
        )

        # SHARED_STAGED_TEXT_VARIANTS_V1
        # All three destinations are in workspace review storage.
        staged_root = (
            f"{clean_client}/{workspace}/{clean_project}"
            f"/processing_center/staged/{source_job_id}/"
        )

        allowed_text_prefixes = (
            staged_root + "text/",
            staged_root + "xl/text/",
            staged_root + "structured/text/",
        )

        matching_prefixes = [
            prefix for prefix in allowed_text_prefixes
            if path.startswith(prefix)
        ]

        if len(matching_prefixes) != 1:
            raise ValueError(
                "Review-staged text is outside an authorized "
                "source-job text directory"
            )

        filename = path[len(matching_prefixes[0]):]

        if (
            not filename
            or "/" in filename
            or not filename.endswith(".txt")
        ):
            raise ValueError(
                "Invalid review-staged text filename"
            )

        if doc_id:
            clean_doc_id = str(doc_id).strip()

            if (
                not clean_doc_id
                or "/" in clean_doc_id
                or "\\" in clean_doc_id
                or filename != f"{clean_doc_id}.txt"
            ):
                raise ValueError(
                    "Staged text does not match INSYT Doc ID"
                )

        return DetectionTextRoute(
            storage_source="review",
            container=review_container,
            blob_path=path,
        )

    # PROCESSING_TEXT_PROJECT_SCOPE_V1
    # Preserve processing-storage handoffs, but never allow
    # cross-client, cross-project, or cross-workspace access.
    clean_client = str(client).strip().strip("/")
    clean_project = (
        str(project).strip().strip("/").replace(" ", "_")
    )

    if not clean_client or not clean_project:
        raise ValueError("Processing text requires project identity")

    expected_project_prefix = (
        f"{clean_client}/{workspace}/{clean_project}/"
    )

    if not path.startswith(expected_project_prefix):
        raise ValueError(
            "Processing text is outside the requested project"
        )

    # Preserve established processing-storage handoffs.
    # Source-job-specific prefixes remain to be verified.
    return DetectionTextRoute(
        storage_source="processing",
        container=processing_container,
        blob_path=path,
    )
