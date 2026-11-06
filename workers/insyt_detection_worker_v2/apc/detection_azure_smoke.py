from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from .detection.engine import run_detection_engine
from .detection_checkpoint_store import DetectionCheckpointStore
from .detection_rule_fingerprint import effective_rule_fingerprint
from .worksheet_checkpoint_executor import WorksheetCheckpointExecutor
from .worksheet_work_units import WorksheetWorkUnit


SMOKE_PROJECT_PREFIX = "INSYT_SMOKE/capture/Checkpoint_V2"

SMOKE_TEXT = "email,smoke@example.test\n"


@dataclass(frozen=True)
class SmokeResult:
    smoke_id: str
    checkpoint_path: str
    result_path: str
    reused_checkpoint: bool
    candidate_count: int


def run_checkpoint_smoke(
    *,
    container_client: Any,
    smoke_id: str,
    engine: Callable[..., dict[str, Any]] = run_detection_engine,
) -> SmokeResult:
    """
    Controlled synthetic Detection V2 Azure checkpoint smoke test.

    No client documents are read.
    No detection job status is modified.
    No continuation messages are published.
    Azure Language detection is disabled.
    """
    if (
        not isinstance(smoke_id, str)
        or re.fullmatch(
            r"SMOKE-[A-Z0-9]{8,24}",
            smoke_id,
        )
        is None
    ):
        raise ValueError("Invalid smoke-test identifier.")

    text = SMOKE_TEXT

    unit = WorksheetWorkUnit(
        unit_id="chunk-000001",
        start_row=1,
        end_row=1,
        start_offset=0,
        end_offset=len(text),
        row_count=1,
        text_sha256=hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest(),
        text=text,
    )

    store = DetectionCheckpointStore(
        container_client,
        project_prefix=SMOKE_PROJECT_PREFIX,
    )

    rule_fingerprint = effective_rule_fingerprint(
        workspace="capture",
        structured_rules=None,
        rule_source="built_in_rules_fallback",
    )

    executor = WorksheetCheckpointExecutor(
        store=store,
        detection_job_id=smoke_id,
        doc_id="INSYTSMOKE000001",
        protocol_fingerprint=rule_fingerprint,
        detection_mode="worksheet_triage",
        include_phi=False,
        enable_azure=False,
        structured_rules=None,
        engine=engine,
        protocol_name="INSYT Synthetic Smoke",
        protocol_version="smoke-v1",
    )

    fingerprint = executor._fingerprint(unit)
    expected = executor._checkpoint(unit, fingerprint)

    reused = store.load_reusable(expected) is not None

    result = executor(unit)

    verified = store.load_reusable(expected)

    if verified is None:
        raise RuntimeError(
            "Smoke-test checkpoint not verified in Blob Storage."
        )

    restored = executor(unit)

    if restored != result:
        raise RuntimeError(
            "Smoke-test checkpoint restoration mismatch."
        )

    response = SmokeResult(
        smoke_id=smoke_id,
        checkpoint_path=store.checkpoint_path(expected),
        result_path=store.result_path(expected),
        reused_checkpoint=reused,
        candidate_count=len(result["candidates"]),
    )

    logging.info(
        "INSYT Detection checkpoint smoke PASS: "
        "smoke_id=%s reused=%s candidates=%d "
        "checkpoint=%s",
        response.smoke_id,
        response.reused_checkpoint,
        response.candidate_count,
        response.checkpoint_path,
    )

    return response