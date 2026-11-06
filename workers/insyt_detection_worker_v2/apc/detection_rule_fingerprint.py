from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from .detection.built_in_rules import get_built_in_rules
from .detection.rules import DetectionRule, rule_to_dict


RULE_FINGERPRINT_VERSION = 1


def effective_rule_fingerprint(
    *,
    workspace: str,
    structured_rules: Iterable[DetectionRule] | None,
    rule_source: str,
    selected_sheets: Iterable[str] = (),
) -> str:
    """
    Fingerprint the actual effective structured rules.

    Capture may use its built-in fallback when the
    workbook loader returns None.

    Discovery must provide explicit Discovery rules.

    Rule ordering is retained. Rule content, workspace,
    source identity and selected sheets are included.
    """
    workspace_key = str(workspace or "").strip().lower()

    if workspace_key not in {"capture", "discovery"}:
        raise ValueError("Unsupported detection workspace.")

    source = str(rule_source or "").strip()

    if not source:
        raise ValueError("Rule source is required.")

    if structured_rules is None:
        if workspace_key != "capture":
            raise ValueError(
                "Discovery cannot use Capture fallback rules."
            )

        if source != "built_in_rules_fallback":
            raise ValueError(
                "Missing Capture rules require explicit fallback."
            )

        rules = list(get_built_in_rules())
    else:
        rules = list(structured_rules)

    if any(
        not isinstance(rule, DetectionRule)
        for rule in rules
    ):
        raise TypeError(
            "All effective rules must be DetectionRule instances."
        )

    if workspace_key == "discovery" and not rules:
        raise ValueError(
            "Discovery requires effective search rules."
        )

    if not rules:
        raise ValueError("Effective detection rules are empty.")

    sheets = list(selected_sheets)

    if any(
        not isinstance(sheet, str)
        for sheet in sheets
    ):
        raise TypeError("Sheet names must be strings.")

    identity: dict[str, Any] = {
        "schema_version": RULE_FINGERPRINT_VERSION,
        "workspace": workspace_key,
        "rule_source": source,
        "selected_sheets": sheets,
        "rules": [
            rule_to_dict(rule)
            for rule in rules
        ],
    }

    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(
        canonical
    ).hexdigest()