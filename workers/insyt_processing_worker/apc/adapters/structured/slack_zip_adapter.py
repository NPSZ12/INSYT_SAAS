from __future__ import annotations

from pathlib import Path

from apc.adapters.base import AdapterContext, AdapterResult, PreparedChild
from apc.adapters.containers.zip_adapter import ZIP_ADAPTER

from app.services.structured_intake.adapters.json_slack import (
    is_slack_export_zip,
    normalize_slack_zip_to_csv,
)
from app.services.structured_intake.json_csv_partition import (
    partition_normalized_json_csv,
)


class SlackZipAdapter:
    """
    Handle Slack export ZIPs without changing ordinary ZIP processing.

    The original ZIP adapter must successfully validate and extract
    the entire archive before Slack normalization is permitted.
    """

    name = "slack_zip_router"
    extensions = (".zip",)

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path).resolve()

        # Ordinary ZIPs retain their original adapter and behavior.
        if not is_slack_export_zip(source):
            return ZIP_ADAPTER.process(context)

        # Enforce the same budgets, member checks, traversal restrictions,
        # extraction isolation, and member-error reporting as normal ZIPs.
        validated = ZIP_ADAPTER.process(context)

        if (
            validated.status != "completed"
            or validated.metadata.get("member_errors")
        ):
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error="SLACK_ZIP_MEMBER_VALIDATION_FAILED",
                metadata={
                    "source_profile": "slack",
                    "zip_validation_status": validated.status,
                    "member_errors": validated.metadata.get(
                        "member_errors", []
                    ),
                },
            )

        work_root = (
            Path(context.work_dir or source.parent / ".insyt_prepared")
            .resolve() / "slack_zip_normalized"
        )

        normalized_csv = work_root / "normalized.csv"
        partition_dir = work_root / "parts"

        try:
            if work_root.exists():
                raise FileExistsError(work_root)

            work_root.mkdir(parents=True)

            normalization = normalize_slack_zip_to_csv(
                source_path=source,
                output_path=normalized_csv,
            )

            expected = int(normalization.package.record_count or 0)

            partitions = partition_normalized_json_csv(
                source_csv=normalized_csv,
                output_dir=partition_dir,
            )

            actual = sum(
                int(part["record_count"])
                for part in partitions
            )

            if actual != expected:
                raise RuntimeError(
                    "Slack ZIP CSV record-count mismatch: "
                    f"expected={expected}, actual={actual}"
                )

            if not partitions:
                raise RuntimeError(
                    "Slack ZIP produced no normalized CSV children"
                )

            children = []

            for part in partitions:
                number = int(part["part_number"])
                path = Path(part["path"]).resolve()

                if not path.is_file() or path.suffix.lower() != ".csv":
                    raise RuntimeError(
                        f"Invalid Slack ZIP CSV child: {path}"
                    )

                if path.stat().st_size != int(part["bytes"]):
                    raise RuntimeError(
                        f"Slack ZIP CSV byte mismatch: {path}"
                    )

                lineage = {
                    "source_profile": "slack",
                    "parent_file_id": context.file_id,
                    "child_number": number,
                    "record_count": int(part["record_count"]),
                    "first_record": int(part["first_record"]),
                    "last_record": int(part["last_record"]),
                    "derivation_method": "slack_zip_to_csv",
                }

                children.append(
                    PreparedChild(
                        source_path=path,
                        normalized_path=(
                            f"{context.normalized_path}"
                            f"!/slack/part{number:04d}.csv"
                        ),
                        relationship="structured_csv",
                        original_name=path.name,
                        extension=".csv",
                        metadata={
                            "structured_json_child": lineage,
                            "stage_status": {
                                "structured_json_child": dict(lineage)
                            },
                        },
                    )
                )

            normalized_csv.unlink()

            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=context.file_id,
                children=children,
                metadata={
                    "source_profile": "slack",
                    "record_count": expected,
                    "csv_child_count": len(children),
                    "validated_zip_member_count": len(
                        validated.children
                    ),
                    "group_counts": normalization.group_counts,
                    "native_source_path": str(source),
                    "stage_status": {
                        "structured_json_parent": {
                            "source_filename": source.name,
                            "source_profile": "slack",
                            "record_count": expected,
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
                metadata={
                    "source_profile": "slack",
                    "zip_validation_status": validated.status,
                },
            )


SLACK_ZIP_ADAPTER = SlackZipAdapter()