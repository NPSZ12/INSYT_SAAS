from __future__ import annotations

import json
import threading
from typing import Any, Callable

from .detection_checkpoint import DetectionCheckpoint


class PublicationBusy(RuntimeError):
    """Another invocation owns final publication."""


def publish_detection_once(
    *,
    detection_job_id: str,
    claim_store: Any,
    publish_results: Callable[[], dict[str, Any]],
    publish_results_with_claim: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Coordinate job-level final publication.

    Uses the existing detection claim store and the
    Azure Blob lease-protected completion record.

    This controls publication ownership. The caller
    must separately ensure all checkpoint work is
    complete and that result writes are safely fenced.
    """
    job_id = str(detection_job_id or "").strip()

    if not job_id:
        raise ValueError("Detection job ID is required.")

    if not callable(publish_results):
        raise TypeError("Publisher must be callable.")

    checkpoint = DetectionCheckpoint(
        detection_job_id=job_id,
        doc_id="_job",
        unit_id="final_publication",
        protocol_fingerprint="publication-v1",
    )

    claim = claim_store.try_acquire(checkpoint)

    if claim is None:
        raise PublicationBusy(
            "Final publication is owned by another invocation."
        )

    try:
        claim.assert_active()

        if claim.blob is None:
            raise RuntimeError(
                "Publication claim has no coordination blob."
            )

        raw = claim.blob.download_blob().readall()

        if raw:
            saved = json.loads(raw.decode("utf-8"))

            if not isinstance(saved, dict):
                raise ValueError(
                    "Invalid publication completion record."
                )

            if (
                saved.get("state") != "completed"
                or saved.get("detection_job_id") != job_id
                or not isinstance(saved.get("result"), dict)
            ):
                raise ValueError(
                    "Publication completion record mismatch."
                )

            result = saved["result"]

            if result.get("status") not in {
                "completed",
                "completed_with_exceptions",
            }:
                raise ValueError(
                    "Saved publication is not terminal."
                )

            return result

        # Renew the Azure lease throughout publication.
        # The completion marker remains lease-fenced.
        stop_heartbeat = threading.Event()
        renewal_errors = []

        lease_seconds = getattr(
            claim_store, "lease_seconds", 60
        )

        if (
            type(lease_seconds) is not int
            or not 15 <= lease_seconds <= 60
        ):
            raise ValueError(
                "Invalid publication lease duration."
            )

        interval = max(1, lease_seconds // 3)

        def heartbeat():
            while not stop_heartbeat.wait(interval):
                try:
                    claim.renew()
                except Exception as exc:
                    renewal_errors.append(exc)
                    stop_heartbeat.set()
                    return

        thread = threading.Thread(
            target=heartbeat,
            name="insyt-detection-publication-lease",
            daemon=True,
        )
        thread.start()

        try:
            if publish_results_with_claim is None:
                result = publish_results()
            else:
                result = publish_results_with_claim(claim)
        finally:
            stop_heartbeat.set()
            thread.join()

        if renewal_errors:
            raise RuntimeError(
                "Publication lease renewal failed; "
                "completion prohibited."
            ) from renewal_errors[0]

        if not isinstance(result, dict):
            raise TypeError(
                "Final publication must return a dictionary."
            )

        if result.get("status") not in {
            "completed",
            "completed_with_exceptions",
        }:
            raise ValueError(
                "Cannot publish a nonterminal result."
            )

        if result.get("detection_job_id") != job_id:
            raise ValueError(
                "Publication result job ID mismatch."
            )

        claim.assert_active()

        # This write is protected by the Azure lease.
        claim.publish_completion({
            "state": "completed",
            "detection_job_id": job_id,
            "result": result,
        })

        return result

    finally:
        claim.release()