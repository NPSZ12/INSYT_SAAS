from __future__ import annotations

from pathlib import Path

from apc.adapters.base import AdapterContext, AdapterResult
from apc.adapters.structured.salesforce_processor import (
    SALESFORCE_JSON_PROCESSOR,
)
from apc.adapters.structured.plain_json_processor import (
    PLAIN_JSON_PROCESSOR,
)
from apc.adapters.structured.slack_json_processor import (
    SLACK_JSON_PROCESSOR,
)
from app.services.structured_intake.json_router import (
    detect_json_source_profile,
)


class JsonProfileAdapter:
    """
    Generic JSON entry point for the Train Station.

    Profile classification and processor selection happen
    entirely within this adapter, not in APC orchestration.

    Do not register until all previously supported JSON
    profiles have been connected and regression-tested.
    """

    name = "json_structured"
    extensions = (".json", ".jsonl", ".ndjson")

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path)

        try:
            profile = detect_json_source_profile(source)

            if profile == "salesforce":
                return SALESFORCE_JSON_PROCESSOR.process(context)

            if profile == "plain":
                return PLAIN_JSON_PROCESSOR.process(context)

            if profile == "slack":
                return SLACK_JSON_PROCESSOR.process(context)

            # These profiles must be connected before the JSON
            # adapter is registered for production dispatch.
            # Never reinterpret them as Salesforce.
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error=(
                    f"JSON profile processor not connected: {profile}"
                ),
                metadata={
                    "source_profile": profile,
                    "routing_status": "not_connected",
                },
            )

        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error=f"{type(exc).__name__}: {exc}",
            )


JSON_PROFILE_ADAPTER = JsonProfileAdapter()