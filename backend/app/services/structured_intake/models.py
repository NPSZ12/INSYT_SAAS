from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class StructuredRecord:
    source_record_id: str
    record_type: str

    fields: dict[str, Any] = field(
        default_factory=dict
    )

    group_id: str | None = None
    group_name: str | None = None

    parent_record_id: str | None = None

    relationships: list[dict[str, Any]] = field(
        default_factory=list
    )

    attachments: list[dict[str, Any]] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class StructuredPackageInfo:
    source_family: str
    source_format: str
    source_profile: str

    source_path: Path
    source_filename: str

    package_id: str | None = None

    package_count: int = 1
    record_count: int = 0

    normalized_format: str = "csv"
    normalized_csv_path: Path | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class StructuredNormalizationResult:
    package: StructuredPackageInfo

    normalized_csv_paths: list[Path] = field(
        default_factory=list
    )

    group_counts: dict[str, int] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


StructuredRecordIterator = Iterable[StructuredRecord]