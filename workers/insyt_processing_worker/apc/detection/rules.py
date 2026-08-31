from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DetectionRule:
    rule_id: str
    entity_type: str

    entity_subtype: str = ""

    regex_pattern: str = ""

    context_terms: tuple[str, ...] = ()

    validator: str = ""

    base_confidence: float = 0.70

    country: str = ""
    framework: tuple[str, ...] = ()

    enabled: bool = True

    methods: tuple[str, ...] = (
        "regex",
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


def rule_to_dict(
    rule: DetectionRule,
) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "entity_type": rule.entity_type,
        "entity_subtype": rule.entity_subtype,
        "regex_pattern": rule.regex_pattern,
        "context_terms": list(rule.context_terms),
        "validator": rule.validator,
        "base_confidence": rule.base_confidence,
        "country": rule.country,
        "framework": list(rule.framework),
        "enabled": rule.enabled,
        "methods": list(rule.methods),
        "metadata": dict(rule.metadata),
    }