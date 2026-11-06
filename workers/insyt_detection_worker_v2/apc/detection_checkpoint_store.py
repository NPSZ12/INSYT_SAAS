from __future__ import annotations

import hashlib
import json
from typing import Any

from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from .detection_checkpoint import (
    CHECKPOINT_COMPLETED,
    DetectionCheckpoint,
    checkpoint_is_reusable_for,
)


def _safe_segment(value: str) -> str:
    value = str(value or "").strip()

    if (
        not value
        or value in {".", ".."}
        or not all(
            char.isalnum() or char in "_-."
            for char in value
        )
    ):
        raise ValueError("Unsafe checkpoint path segment.")

    return value


class DetectionCheckpointStore:
    """
    Immutable completed-work checkpoint storage.

    The container client is injected so this module can
    use the existing INSYT processing storage connection
    without creating a second storage configuration.

    This component does not claim work, schedule workers,
    or finalize a detection job.
    """

    def __init__(
        self,
        container_client: Any,
        *,
        project_prefix: str,
    ) -> None:
        if not project_prefix or not project_prefix.strip("/"):
            raise ValueError("Project prefix is required.")

        self.container = container_client
        self.project_prefix = project_prefix.strip("/")

    def _prefix(
        self,
        checkpoint: DetectionCheckpoint,
    ) -> str:
        job_id = _safe_segment(
            checkpoint.detection_job_id
        )
        doc_id = _safe_segment(
            checkpoint.doc_id
        )
        unit_id = _safe_segment(
            checkpoint.unit_id
        )

        fingerprint = str(
            checkpoint.protocol_fingerprint
        ).strip()

        if not fingerprint:
            raise ValueError(
                "Checkpoint fingerprint is required."
            )

        fingerprint_id = hashlib.sha256(
            fingerprint.encode("utf-8")
        ).hexdigest()

        return (
            f"{self.project_prefix}/processing_center/"
            f"detection/jobs/{job_id}/checkpoints/"
            f"{doc_id}/{unit_id}/fingerprints/"
            f"{fingerprint_id}"
        )

    def checkpoint_path(
        self,
        checkpoint: DetectionCheckpoint,
    ) -> str:
        return f"{self._prefix(checkpoint)}/checkpoint.json"

    def result_path(
        self,
        checkpoint: DetectionCheckpoint,
    ) -> str:
        return f"{self._prefix(checkpoint)}/result.json"

    def save_completed(
        self,
        checkpoint: DetectionCheckpoint,
        *,
        result_payload: dict[str, Any],
    ) -> bool:
        """
        Save result first, then the completion marker.

        Both uploads are create-only. A competing worker
        cannot overwrite a previously published artifact.

        False means an artifact or checkpoint already
        exists and must be verified before reuse.
        """
        if checkpoint.state != CHECKPOINT_COMPLETED:
            raise ValueError("Checkpoint must be completed.")

        expected_result_path = self.result_path(
            checkpoint
        )

        if checkpoint.result_blob_path != expected_result_path:
            raise ValueError(
                "Checkpoint result path does not match its work unit."
            )

        result_data = json.dumps(
            result_payload,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")

        result_blob = self.container.get_blob_client(
            expected_result_path
        )

        try:
            result_blob.upload_blob(
                result_data,
                overwrite=False,
            )
        except ResourceExistsError:
            # A previous worker may have saved the
            # artifact before losing its invocation.
            #
            # Recover only when the existing artifact
            # is byte-for-byte identical. Never adopt
            # or overwrite conflicting results.
            try:
                existing_data = (
                    result_blob.download_blob().readall()
                )
            except ResourceNotFoundError:
                return False

            if existing_data != result_data:
                return False

        checkpoint_blob = self.container.get_blob_client(
            self.checkpoint_path(checkpoint)
        )

        checkpoint_data = json.dumps(
            checkpoint.to_dict(),
            sort_keys=True,
        ).encode("utf-8")

        try:
            checkpoint_blob.upload_blob(
                checkpoint_data,
                overwrite=False,
            )
        except ResourceExistsError:
            return False

        return True

    def load_reusable(
        self,
        expected: DetectionCheckpoint,
    ) -> DetectionCheckpoint | None:
        """
        Return a completed checkpoint only after verifying
        its identity and result artifact existence.
        """
        checkpoint_blob = self.container.get_blob_client(
            self.checkpoint_path(expected)
        )

        try:
            raw = checkpoint_blob.download_blob().readall()
        except ResourceNotFoundError:
            return None

        saved = DetectionCheckpoint.from_dict(
            json.loads(raw.decode("utf-8"))
        )

        if saved.result_blob_path != self.result_path(expected):
            return None

        artifact = self.container.get_blob_client(
            saved.result_blob_path
        )

        try:
            artifact.get_blob_properties()
            artifact_exists = True
        except ResourceNotFoundError:
            artifact_exists = False

        if not checkpoint_is_reusable_for(
            saved,
            detection_job_id=expected.detection_job_id,
            doc_id=expected.doc_id,
            unit_id=expected.unit_id,
            protocol_fingerprint=expected.protocol_fingerprint,
            artifact_exists=artifact_exists,
        ):
            return None

        return saved