from __future__ import annotations

from pathlib import Path

from apc.adapters.base import (
    AdapterContext,
    AdapterResult,
    PreparedChild,
)
from app.services.structured_intake.adapters.json_salesforce import (
    normalize_salesforce_json_to_csv,
)
from app.services.structured_intake.json_csv_partition import (
    partition_normalized_json_csv,
)


class SalesforceJsonProcessor:
    """Self-contained Salesforce-to-CSV preparation adapter."""

    name = "json_salesforce"
    extensions = (".json",)

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path).resolve()
        work_root = (
            Path(context.work_dir or source.parent / ".insyt_prepared")
            .resolve() / "salesforce"
        )
        normalized_csv = work_root / "normalized.csv"
        partition_dir = work_root / "parts"

        try:
            if not source.is_file():
                raise FileNotFoundError(source)
            if work_root.exists():
                raise FileExistsError(work_root)

            work_root.mkdir(parents=True)

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=normalized_csv,
            )
            expected = int(result.package.record_count or 0)

            partitions = partition_normalized_json_csv(
                source_csv=normalized_csv,
                output_dir=partition_dir,
            )

            actual = sum(
                int(part["record_count"]) for part in partitions
            )
            if actual != expected:
                raise RuntimeError(
                    f"Record mismatch: expected={expected}, actual={actual}"
                )

            children = []
            for part in partitions:
                number = int(part["part_number"])
                path = Path(part["path"]).resolve()
                if not path.is_file() or path.suffix.lower() != ".csv":
                    raise RuntimeError(f"Invalid CSV child: {path}")
                if path.stat().st_size != int(part["bytes"]):
                    raise RuntimeError(f"CSV byte mismatch: {path}")

                children.append(
                    PreparedChild(
                        source_path=path,
                        normalized_path=(
                            f"{context.normalized_path}"
                            f"!/salesforce/part{number:04d}.csv"
                        ),
                        relationship="structured_csv",
                        original_name=path.name,
                        extension=".csv",
                        metadata={
                            "structured_json_child": {
                                "source_profile": "salesforce",
                                "parent_file_id": context.file_id,
                                "child_number": number,
                                "record_count": int(part["record_count"]),
                                "first_record": int(part["first_record"]),
                                "last_record": int(part["last_record"]),
                                "derivation_method": "salesforce_json_to_csv",
                            }
                        },
                    )
                )

            # Publish adapter-owned lineage through the generic
            # Train Station stage-status transport contract.
            for generated_child in children:
                generated_child.metadata["stage_status"] = {
                    "structured_json_child": dict(
                        generated_child.metadata["structured_json_child"]
                    )
                }

            normalized_csv.unlink()

            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=context.file_id,
                children=children,
                metadata={
                    "source_profile": "salesforce",
                    "record_count": expected,
                    "csv_child_count": len(children),
                    "native_source_path": str(source),
                    "stage_status": {
                        "structured_json_parent": {
                            "source_filename": source.name,
                            "source_profile": "salesforce",
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
                metadata={"source_profile": "salesforce"},
            )


SALESFORCE_JSON_PROCESSOR = SalesforceJsonProcessor()