from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .detection_checkpoint import DetectionCheckpoint


FINALIZATION_SCHEMA_VERSION = 1


def finalize_detection_job_once(
    *,
    claim_store: Any,
    detection_job_id: str,
    protocol_fingerprint: str,
    verify_all_completed: Callable[[], bool],
    finalize: Callable[[Any], None],
) -> bool:
    """
    Serialize job finalization through an Azure Blob lease.

    The finalize callback must be idempotent because a crash
    can happen after writing results but before publishing the
    leased completion record.

    Returns True when this invocation finalizes the job.
    Returns False for an already finalized or busy job.

    Does not enqueue messages or modify status.json.
    """
    if not callable(verify_all_completed):
        raise TypeError("Verification callback required.")

    if not callable(finalize):
        raise TypeError("Finalization callback required.")

    if not detection_job_id or not detection_job_id.strip():
        raise ValueError("Detection job ID required.")

    if not protocol_fingerprint or not protocol_fingerprint.strip():
        raise ValueError("Protocol fingerprint required.")

    identity = DetectionCheckpoint(
        detection_job_id=detection_job_id,
        doc_id="_job",
        unit_id="finalization",
        protocol_fingerprint=protocol_fingerprint,
    )

    claim = claim_store.try_acquire(identity)

    if claim is None:
        return False

    try:
        if claim.blob is None:
            raise RuntimeError("Coordination blob missing.")

        raw = claim.blob.download_blob().readall()

        if raw:
            record = json.loads(raw.decode("utf-8"))

            if not isinstance(record, dict):
                raise ValueError("Invalid finalization record.")

            expected_fields = {
                "schema_version",
                "state",
                "detection_job_id",
                "protocol_fingerprint",
            }

            if set(record) != expected_fields:
                raise ValueError("Finalization schema mismatch.")

            if (
                record["schema_version"]
                != FINALIZATION_SCHEMA_VERSION
                or record["detection_job_id"]
                != detection_job_id
                or record["protocol_fingerprint"]
                != protocol_fingerprint
                or record["state"] != "completed"
            ):
                raise ValueError(
                    "Conflicting finalization record."
                )

            return False

        if verify_all_completed() is not True:
            raise RuntimeError(
                "Cannot finalize incomplete detection job."
            )

        # This callback must safely tolerate a retry.
        # It receives the active claim so it can renew
        # ownership during longer finalization work.
        finalize(claim)

        # Azure validates the lease during this write.
        claim.publish_completion({
            "schema_version": FINALIZATION_SCHEMA_VERSION,
            "state": "completed",
            "detection_job_id": detection_job_id,
            "protocol_fingerprint": protocol_fingerprint,
        })

        return True

    finally:
        claim.release()