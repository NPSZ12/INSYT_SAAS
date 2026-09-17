from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from .config import Settings
from .db import LedgerDB
from .pricing import PricingEngine, PriceQuote
from .util import json_dumps, new_id, utc_now


@dataclass
class StageMetrics:
    files_in: int = 0
    files_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    documents_in: int = 0
    documents_out: int = 0
    pages_in: int = 0
    pages_out: int = 0
    exceptions: int = 0
    retry_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class StageRunner:
    """Context manager that records processing_stage_run and cost_event rows.

    Every processing stage should be wrapped in StageRunner so we get consistent
    timing, counts, exception data, and compute-cost estimates.
    """

    def __init__(
        self,
        db: LedgerDB,
        settings: Settings,
        job_id: str,
        matter_id: str,
        stage_name: str,
        worker_name: str,
    ):
        self.db = db
        self.settings = settings
        self.job_id = job_id
        self.matter_id = matter_id
        self.stage_name = stage_name
        self.worker_name = worker_name
        self.stage_run_id = new_id("STAGE")
        self.started_at = utc_now()
        self.ended_at: str | None = None
        self.start_perf = 0.0
        self.metrics = StageMetrics()
        self.pricing = PricingEngine(db, settings)
        self.quoted_cost_usd = 0.0

    def __enter__(self) -> "StageRunner":
        self.start_perf = time.perf_counter()
        self.db.execute(
            """
            INSERT INTO processing_stage_run (
                stage_run_id, job_id, matter_id, stage_name, worker_name,
                started_at, status
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                self.stage_run_id,
                self.job_id,
                self.matter_id,
                self.stage_name,
                self.worker_name,
                self.started_at,
                "running",
            ),
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc is not None:
            self.metrics.exceptions += 1
            self.metrics.extra.setdefault("exception", repr(exc))
        status = "failed" if exc is not None else "completed"
        self.finish(status=status)
        return False

    def finish(self, status: str = "completed") -> None:
        duration_ms = int((time.perf_counter() - self.start_perf) * 1000)
        self.ended_at = utc_now()
        cpu_seconds = max(0.001, (duration_ms / 1000.0) * self.settings.worker_vcpu)
        memory_gib_seconds = max(0.001, (duration_ms / 1000.0) * self.settings.worker_memory_gib)

        vcpu_quote = self.quote_cost(
            azure_service="Azure Container Apps",
            meter_name="vCPU Seconds",
            quantity=cpu_seconds,
            unit="seconds",
            confidence_note="estimated from configured worker vCPU and wall-clock duration",
        )
        mem_quote = self.quote_cost(
            azure_service="Azure Container Apps",
            meter_name="Memory GiB Seconds",
            quantity=memory_gib_seconds,
            unit="gib-seconds",
            confidence_note="estimated from configured worker memory and wall-clock duration",
        )
        estimated_cost = self.quoted_cost_usd

        self.db.execute(
            """
            UPDATE processing_stage_run
            SET ended_at=?, status=?, duration_ms=?, files_in=?, files_out=?, bytes_in=?, bytes_out=?,
                documents_in=?, documents_out=?, pages_in=?, pages_out=?, exceptions=?, retry_count=?,
                cpu_seconds_estimated=?, memory_gib_seconds_estimated=?, estimated_cost_usd=?, metrics_json=?
            WHERE stage_run_id=?
            """,
            (
                self.ended_at,
                status,
                duration_ms,
                self.metrics.files_in,
                self.metrics.files_out,
                self.metrics.bytes_in,
                self.metrics.bytes_out,
                self.metrics.documents_in,
                self.metrics.documents_out,
                self.metrics.pages_in,
                self.metrics.pages_out,
                self.metrics.exceptions,
                self.metrics.retry_count,
                cpu_seconds,
                memory_gib_seconds,
                estimated_cost,
                json_dumps(self.metrics.extra),
                self.stage_run_id,
            ),
        )

    def quote_cost(
        self,
        azure_service: str,
        meter_name: str,
        quantity: float,
        unit: str,
        file_id: str | None = None,
        confidence_note: str | None = None,
        cost_type: str = "estimated",
    ) -> PriceQuote:
        quote = self.pricing.quote(azure_service, meter_name, quantity, unit)
        self.emit_cost_event(quote=quote, file_id=file_id, notes=confidence_note, cost_type=cost_type)
        self.quoted_cost_usd += float(quote.estimated_cost_usd or 0)
        return quote

    def emit_cost_event(self, quote: PriceQuote, file_id: str | None = None, notes: str | None = None, cost_type: str = "estimated") -> None:
        self.db.execute(
            """
            INSERT INTO cost_event (
                cost_event_id, matter_id, job_id, stage_run_id, file_id, event_time,
                azure_service, azure_resource_id, meter_name, meter_id, region,
                quantity, unit_of_measure, unit_price_usd, estimated_cost_usd,
                price_source, price_effective_date, confidence, cost_type, notes, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                new_id("COST"),
                self.matter_id,
                self.job_id,
                self.stage_run_id,
                file_id,
                utc_now(),
                quote.azure_service,
                None,
                quote.meter_name,
                quote.meter_id,
                self.settings.azure_region,
                quote.quantity,
                quote.unit_of_measure,
                quote.unit_price_usd,
                quote.estimated_cost_usd,
                quote.price_source,
                quote.price_effective_date,
                quote.confidence,
                cost_type,
                notes,
                json_dumps(quote.raw or {}),
            ),
        )
