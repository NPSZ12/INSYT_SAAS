from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CHECKPOINT_SCHEMA_VERSION = 1

CHECKPOINT_PENDING = "pending"
CHECKPOINT_RUNNING = "running"
CHECKPOINT_COMPLETED = "completed"
CHECKPOINT_FAILED = "failed"

VALID_STATES = {
    CHECKPOINT_PENDING,
    CHECKPOINT_RUNNING,
    CHECKPOINT_COMPLETED,
    CHECKPOINT_FAILED,
}


@dataclass(frozen=True)
class DetectionCheckpoint:
    detection_job_id: str
    doc_id: str
    unit_id: str
    protocol_fingerprint: str
    state: str = CHECKPOINT_PENDING
    attempt: int = 0
    result_blob_path: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        if not self.detection_job_id.strip():
            raise ValueError("Detection job ID is required.")

        if not self.doc_id.strip():
            raise ValueError("Document ID is required.")

        if not self.unit_id.strip():
            raise ValueError("Work-unit ID is required.")

        if not self.protocol_fingerprint.strip():
            raise ValueError("Protocol fingerprint is required.")

        if self.state not in VALID_STATES:
            raise ValueError("Invalid checkpoint state.")

        if self.attempt < 0:
            raise ValueError("Checkpoint attempt cannot be negative.")

        if self.state == CHECKPOINT_COMPLETED:
            if not self.result_blob_path.strip():
                raise ValueError(
                    "Completed checkpoint requires result artifact."
                )

            if not self.completed_at.strip():
                raise ValueError(
                    "Completed checkpoint requires completion time."
                )

    @property
    def reusable(self) -> bool:
        return (
            self.state == CHECKPOINT_COMPLETED
            and bool(self.result_blob_path)
            and bool(self.completed_at)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "detection_job_id": self.detection_job_id,
            "doc_id": self.doc_id,
            "unit_id": self.unit_id,
            "protocol_fingerprint": self.protocol_fingerprint,
            "state": self.state,
            "attempt": self.attempt,
            "result_blob_path": self.result_blob_path,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "DetectionCheckpoint":
        if not isinstance(value, dict):
            raise ValueError("Checkpoint must be a JSON object.")

        if value.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("Unsupported checkpoint schema version.")

        return cls(
            detection_job_id=str(
                value.get("detection_job_id") or ""
            ),
            doc_id=str(value.get("doc_id") or ""),
            unit_id=str(value.get("unit_id") or ""),
            protocol_fingerprint=str(
                value.get("protocol_fingerprint") or ""
            ),
            state=str(value.get("state") or CHECKPOINT_PENDING),
            attempt=int(value.get("attempt") or 0),
            result_blob_path=str(
                value.get("result_blob_path") or ""
            ),
            completed_at=str(value.get("completed_at") or ""),
        )

def checkpoint_is_reusable_for(
    checkpoint: DetectionCheckpoint,
    *,
    detection_job_id: str,
    doc_id: str,
    unit_id: str,
    protocol_fingerprint: str,
    artifact_exists: bool,
) -> bool:
    """
    Check that a completed checkpoint belongs to the
    requested work unit and that its result artifact exists.

    The caller must independently verify artifact existence
    in the configured processing storage.
    """
    return (
        checkpoint.reusable
        and checkpoint.detection_job_id == detection_job_id
        and checkpoint.doc_id == doc_id
        and checkpoint.unit_id == unit_id
        and checkpoint.protocol_fingerprint == protocol_fingerprint
        and artifact_exists is True
    )