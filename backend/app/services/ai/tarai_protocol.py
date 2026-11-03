"""Map Discovery protocol coding fields for TARai.

Read-only. Never creates or modifies project coding.
"""

from __future__ import annotations

from typing import Any


class TARaiProtocolError(ValueError):
    pass


def resolve_privilege_fields(
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(fields, list):
        raise TARaiProtocolError("Protocol fields must be a list.")

    sections: dict[str, dict[str, str]] = {}

    for field in fields:
        if not isinstance(field, dict):
            raise TARaiProtocolError("Invalid protocol field.")

        section = str(field.get("section") or "").strip()
        label = str(field.get("data_element") or "").strip()
        field_format = str(
            field.get("format")
            or field.get("default_format")
            or ""
        ).strip()

        if section.casefold() not in {
            "privilege",
            "privilege status",
        }:
            continue

        if field_format.casefold() != "tag":
            raise TARaiProtocolError(
                "Privilege fields must use Tag format."
            )

        if not label:
            raise TARaiProtocolError(
                "Privilege field label is missing."
            )

        section_key = section.casefold()
        section_fields = sections.setdefault(section_key, {})

        label_key = label.casefold()

        if label_key in section_fields:
            raise TARaiProtocolError(
                "Duplicate privilege field in the same section."
            )

        section_fields[label_key] = label

    required = {"privileged", "not privileged"}

    if not sections:
        raise TARaiProtocolError(
            "No Discovery privilege section found."
        )

    for section, labels in sections.items():
        if set(labels) != required:
            raise TARaiProtocolError(
                f"Incomplete or conflicting privilege fields: {section}"
            )

    # Prefer the explicit Privilege section when both exist.
    selected = (
        "privilege"
        if "privilege" in sections
        else "privilege status"
    )

    return {
        "section": selected,
        "privileged": sections[selected]["privileged"],
        "not_privileged": sections[selected]["not privileged"],
        "available_sections": sorted(sections),
        "requires_reviewer_approval": True,
    }