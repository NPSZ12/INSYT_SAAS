from pathlib import Path

from apc.adapters.base import AdapterContext, AdapterResult
from apc.adapters.containers.zip_adapter import ZIP_ADAPTER
from app.services.structured_intake.adapters.json_slack import (
    is_slack_export_zip,
)


class SlackZipAdapter:
    """Extract Slack ZIP members natively using the secure ZIP adapter."""

    name = "slack_zip_router"
    extensions = (".zip",)

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path)

        # Ordinary ZIP processing remains unchanged.
        if not is_slack_export_zip(source):
            return ZIP_ADAPTER.process(context)

        # Use the existing ZIP security checks and extraction limits.
        result = ZIP_ADAPTER.process(context)

        if result.status not in {
            "completed",
            "completed_with_warnings",
        }:
            return result

        return AdapterResult(
            adapter_name=self.name,
            handled=True,
            status=result.status,
            source_file_id=context.file_id,
            children=result.children,
            metadata={
                **(result.metadata or {}),
                "source_profile": "slack",
                "native_source_path": str(source),
            },
        )


SLACK_ZIP_ADAPTER = SlackZipAdapter()
