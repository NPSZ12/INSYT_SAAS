from __future__ import annotations

from typing import Any, Callable

from .detection.engine import run_detection_engine
from .detection_rule_fingerprint import (
    effective_rule_fingerprint,
)
from .worksheet_checkpoint_executor import (
    WorksheetCheckpointExecutor,
)


def make_worksheet_executor_factory(
    *,
    store: Any,
    detection_job_id: str,
    claim_store: Any = None,
    engine: Callable[..., dict[str, Any]] = run_detection_engine,
):
    """
    Construct document-scoped checkpoint executors.

    The caller supplies the existing INSYT processing
    container checkpoint store and detection job ID.

    This factory does not enable checkpoints, acquire
    worker claims, or enqueue continuation messages.
    """
    job_id = str(detection_job_id or "").strip()

    if not job_id:
        raise ValueError("Detection job ID is required.")

    if store is None:
        raise ValueError("Checkpoint store is required.")

    if not callable(engine):
        raise TypeError("Detection engine must be callable.")

    def factory(
        *,
        doc_id: str,
        workspace: str,
        structured_rules,
        rule_source: str,
        selected_sheets,
        include_phi: bool,
        enable_azure: bool,
        protocol_name: str | None,
        protocol_version: str | None,
    ) -> WorksheetCheckpointExecutor:

        document_id = str(doc_id or "").strip()

        if not document_id:
            raise ValueError("Document ID is required.")

        rules = (
            None
            if structured_rules is None
            else list(structured_rules)
        )

        rule_fingerprint = effective_rule_fingerprint(
            workspace=workspace,
            structured_rules=rules,
            rule_source=rule_source,
            selected_sheets=selected_sheets,
        )

        return WorksheetCheckpointExecutor(
            store=store,
            detection_job_id=job_id,
            doc_id=document_id,
            protocol_fingerprint=rule_fingerprint,
            detection_mode="worksheet_triage",
            include_phi=include_phi,
            enable_azure=enable_azure,
            structured_rules=rules,
            claim_store=claim_store,
            engine=engine,
            protocol_name=protocol_name,
            protocol_version=protocol_version,
        )

    return factory