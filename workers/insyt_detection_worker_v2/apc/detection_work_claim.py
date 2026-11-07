from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from azure.core.exceptions import ResourceExistsError

from .detection_checkpoint import DetectionCheckpoint
from .detection_checkpoint_store import _safe_segment


@dataclass
class WorkClaim:
    """An active Azure Blob lease for one detection work unit."""

    blob_path: str
    lease: Any
    blob: Any = None
    released: bool = False

    def renew(self) -> None:
        if self.released:
            raise RuntimeError("Cannot renew a released claim.")
        self.lease.renew()

    def assert_active(self) -> None:
        """
        Verify ownership with the Azure lease service.

        Renewing the lease checks that this lease still
        exists and remains valid. Fail closed if ownership
        cannot be verified.

        This check alone does not fence subsequent writes.
        """
        if self.released:
            raise RuntimeError(
                "Work claim was already released."
            )

        try:
            self.lease.renew()
        except Exception as exc:
            raise RuntimeError(
                "Work claim ownership could not be verified."
            ) from exc

    def publish_completion(
        self,
        payload: dict[str, Any],
    ) -> None:
        """
        Publish a completion record to the leased
        coordination blob.

        Azure Storage must validate the lease ID as
        part of the write itself.

        This is not yet the final checkpoint publication
        or consolidated-result commit.
        """
        if self.released:
            raise RuntimeError(
                "Released worker cannot publish completion."
            )

        if self.blob is None:
            raise RuntimeError(
                "Work claim has no coordination blob."
            )

        if not isinstance(payload, dict):
            raise ValueError(
                "Completion payload must be an object."
            )

        data = json.dumps(
            payload,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")

        try:
            self.blob.upload_blob(
                data,
                overwrite=True,
                lease=self.lease,
            )
        except Exception as exc:
            raise RuntimeError(
                "Lease-protected completion publication failed."
            ) from exc

    def release(self) -> None:
        if self.released:
            return
        self.lease.release()
        self.released = True


class DetectionWorkClaimStore:
    """
    Lease-based mutual exclusion for detection work units.

    Uses an injected existing processing-container client.
    Does not dispatch messages or modify detection results.
    """

    def __init__(
        self,
        container_client: Any,
        *,
        project_prefix: str,
        lease_seconds: int = 60,
    ) -> None:
        segments = str(project_prefix or "").split("/")

        if len(segments) != 3:
            raise ValueError(
                "Project prefix must be client/workspace/project."
            )

        self.project_prefix = "/".join(
            _safe_segment(segment) for segment in segments
        )

        if not 15 <= lease_seconds <= 60:
            raise ValueError(
                "Azure fixed lease must be 15-60 seconds."
            )

        self.container = container_client
        self.lease_seconds = lease_seconds

    def claim_path(
        self,
        checkpoint: DetectionCheckpoint,
    ) -> str:
        job = _safe_segment(checkpoint.detection_job_id)
        doc = _safe_segment(checkpoint.doc_id)
        unit = _safe_segment(checkpoint.unit_id)

        return (
            f"{self.project_prefix}/processing_center/"
            f"detection/jobs/{job}/claims/"
            f"{doc}/{unit}.lock"
        )

    def try_acquire(
        self,
        checkpoint: DetectionCheckpoint,
    ) -> WorkClaim | None:
        path = self.claim_path(checkpoint)
        blob = self.container.get_blob_client(path)

        # Create the lock blob once, with no overwrite.
        # A persistent blob can be leased again after release
        # or expiry; we do not delete shared lock blobs.
        try:
            blob.upload_blob(b"", overwrite=False)
        except ResourceExistsError:
            pass

        try:
            lease = blob.acquire_lease(
                lease_duration=self.lease_seconds
            )
        except ResourceExistsError:
            # An existing active lease prevents ownership.
            return None

        return WorkClaim(
            blob_path=path,
            lease=lease,
            blob=blob,
        )