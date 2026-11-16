from pathlib import Path

from apc.adapters.base import AdapterContext, AdapterResult
from app.services.structured_intake.json_router import (
    detect_json_source_profile,
)


class JsonProfileAdapter:
    """Preserve native JSON for the shared text/Detection pipeline."""

    name = "json_structured"
    extensions = (".json", ".jsonl", ".ndjson")

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path)

        try:
            if source.suffix.lower() not in self.extensions:
                raise ValueError("Unsupported JSON extension")

            if not source.is_file():
                raise FileNotFoundError(str(source))

            profile = detect_json_source_profile(source)

            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=context.file_id,
                children=[],
                metadata={
                    "source_profile": profile,
                    "native_source_path": str(source),
                    "native_detection_required": True,
                    "stage_status": {
                        "structured_json_parent": {
                            "source_filename": source.name,
                            "source_profile": profile,
                            "native_detection_required": True,
                        }
                    },
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
