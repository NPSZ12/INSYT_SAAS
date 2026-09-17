from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectionCandidate:
    entity_type: str
    detected_value: str
    start_offset: int
    end_offset: int

    entity_subtype: str = ""
    normalized_value: str = ""
    masked_value: str = ""

    confidence: float = 0.0

    detector_name: str = ""
    detector_version: str = ""
    detection_rule: str = ""

    protocol_name: str = ""
    protocol_version: str = ""

    reportability: str = "UNCLASSIFIED"

    page_number: int | None = None

    methods: list[str] = field(default_factory=list)
    context_terms: list[str] = field(default_factory=list)

    validation_status: str = ""
    validation_method: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> tuple:
        return (
            self.entity_type.casefold(),
            self.entity_subtype.casefold(),
            self.start_offset,
            self.end_offset,
            self.detected_value.casefold(),
        )

    def overlaps(self, other: "DetectionCandidate") -> bool:
        return (
            self.start_offset < other.end_offset
            and other.start_offset < self.end_offset
        )