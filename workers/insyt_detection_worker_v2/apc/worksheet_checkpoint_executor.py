from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .detection_checkpoint import (
    CHECKPOINT_COMPLETED,
    DetectionCheckpoint,
)
from .detection_candidate_codec import (
    deserialize_candidate_batch,
    serialize_candidate_batch,
)
from .detection_unit_identity import (
    worksheet_detection_fingerprint,
)
from .worksheet_work_units import WorksheetWorkUnit


RESULT_SCHEMA_VERSION = 1

COUNT_FIELDS = (
    "azure_candidate_count",
    "structured_candidate_count",
    "merged_candidate_count",
)


@dataclass
class WorksheetCheckpointExecutor:
    """
    Checkpoint-backed worksheet chunk executor.

    This implementation is for controlled integration tests.
    Distributed publication requires lease-fenced finalization
    before enabling this executor in production.
    """

    store: Any
    detection_job_id: str
    doc_id: str
    protocol_fingerprint: str
    detection_mode: str
    include_phi: bool
    enable_azure: bool
    structured_rules: Any
    engine: Callable[..., dict[str, Any]]
    protocol_name: str | None = None
    protocol_version: str | None = None

    def _fingerprint(
        self,
        unit: WorksheetWorkUnit,
    ) -> str:
        return worksheet_detection_fingerprint(
            unit,
            protocol_fingerprint=self.protocol_fingerprint,
            detection_mode=self.detection_mode,
            include_phi=self.include_phi,
            enable_azure=self.enable_azure,
            enable_structured_rules=True,
        )

    def _checkpoint(
        self,
        unit: WorksheetWorkUnit,
        fingerprint: str,
        *,
        completed_at: str = "",
    ) -> DetectionCheckpoint:
        provisional = DetectionCheckpoint(
            detection_job_id=self.detection_job_id,
            doc_id=self.doc_id,
            unit_id=unit.unit_id,
            protocol_fingerprint=fingerprint,
        )

        if not completed_at:
            return provisional

        return DetectionCheckpoint(
            detection_job_id=self.detection_job_id,
            doc_id=self.doc_id,
            unit_id=unit.unit_id,
            protocol_fingerprint=fingerprint,
            state=CHECKPOINT_COMPLETED,
            result_blob_path=self.store.result_path(
                provisional
            ),
            completed_at=completed_at,
        )

    def _restore(
        self,
        unit: WorksheetWorkUnit,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        expected = self._checkpoint(
            unit,
            fingerprint,
        )

        saved = self.store.load_reusable(expected)

        if saved is None:
            return None

        blob = self.store.container.get_blob_client(
            saved.result_blob_path
        )

        payload = json.loads(
            blob.download_blob().readall().decode("utf-8")
        )

        if not isinstance(payload, dict):
            raise ValueError("Invalid chunk result artifact.")

        if set(payload) != {
            "schema_version",
            "unit_id",
            "fingerprint",
            "chunk_length",
            "candidate_batch",
            *COUNT_FIELDS,
        }:
            raise ValueError("Chunk result schema mismatch.")

        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != RESULT_SCHEMA_VERSION
            or payload["unit_id"] != unit.unit_id
            or payload["fingerprint"] != fingerprint
            or type(payload["chunk_length"]) is not int
            or payload["chunk_length"] != len(unit.text)
        ):
            raise ValueError(
                "Chunk result identity verification failed."
            )

        counts = {}

        for field in COUNT_FIELDS:
            value = payload[field]

            if type(value) is not int or value < 0:
                raise ValueError(
                    f"Invalid chunk result counter: {field}"
                )

            counts[field] = value

        candidates = deserialize_candidate_batch(
            payload["candidate_batch"],
            chunk_length=len(unit.text),
        )

        return {
            "candidates": candidates,
            **counts,
        }

    def __call__(
        self,
        unit: WorksheetWorkUnit,
    ) -> dict[str, Any]:
        fingerprint = self._fingerprint(unit)

        cached = self._restore(unit, fingerprint)

        if cached is not None:
            return cached

        result = self.engine(
            unit.text,
            include_phi=self.include_phi,
            protocol_name=self.protocol_name,
            protocol_version=self.protocol_version,
            enable_azure=self.enable_azure,
            enable_structured_rules=True,
            structured_rules=self.structured_rules,
        )

        if not isinstance(result, dict):
            raise TypeError(
                "Detection engine must return a dictionary."
            )

        candidates = result.get("candidates")

        if not isinstance(candidates, list):
            raise ValueError("Missing detection candidates.")

        counts = {}

        for field in COUNT_FIELDS:
            value = result.get(field)

            if type(value) is not int or value < 0:
                raise ValueError(
                    f"Invalid detection counter: {field}"
                )

            counts[field] = value

        artifact = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "unit_id": unit.unit_id,
            "fingerprint": fingerprint,
            "chunk_length": len(unit.text),
            "candidate_batch": serialize_candidate_batch(
                candidates,
                chunk_length=len(unit.text),
            ),
            **counts,
        }

        from .util import utc_now

        completed = self._checkpoint(
            unit,
            fingerprint,
            completed_at=utc_now(),
        )

        published = self.store.save_completed(
            completed,
            result_payload=artifact,
        )

        if not published:
            # Do not assume another worker's output is safe.
            # Require a verified, readable checkpoint.
            recovered = self._restore(unit, fingerprint)

            if recovered is None:
                raise RuntimeError(
                    "Chunk checkpoint publication conflict."
                )

            return recovered

        recovered = self._restore(unit, fingerprint)

        if recovered is None:
            raise RuntimeError(
                "Published chunk could not be verified."
            )

        return recovered