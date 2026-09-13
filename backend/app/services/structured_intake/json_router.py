from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from .json_detector import (
    JSON_PROFILE_CUSTOM_API,
    JSON_PROFILE_GOOGLE,
    JSON_PROFILE_PLAIN,
    JSON_PROFILE_SALESFORCE,
    JSON_PROFILE_SLACK,
    JSON_PROFILE_TEAMS,
    detect_json_profile,
)


JSON_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
}


def is_json_structured_source(
    source_path: Path,
) -> bool:
    """
    Return True only for extensions owned by the JSON
    structured-intake workflow.

    CSV is intentionally excluded.
    """

    return (
        source_path.suffix
        .strip()
        .lower()
        in JSON_EXTENSIONS
    )


def load_json_detection_sample(
    source_path: Path,
) -> Any:
    """
    Load enough source content to identify the JSON profile.

    Full normalization will later use streaming where possible.
    """

    extension = (
        source_path.suffix
        .strip()
        .lower()
    )


    if extension == ".json":

        with source_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as handle:
            return json.load(handle)


    if extension in {
        ".jsonl",
        ".ndjson",
    }:

        with source_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as handle:

            for line in handle:

                value = line.strip()

                if not value:
                    continue

                return json.loads(
                    value
                )


        return None


    raise ValueError(
        f"Unsupported JSON extension: "
        f"{extension or '[none]'}"
    )


def detect_json_source_profile(
    source_path: Path,
) -> str:
    """
    Identify which dedicated JSON adapter should handle
    this source.
    """

    if not is_json_structured_source(
        source_path
    ):
        raise ValueError(
            "Source is not a JSON structured-intake file: "
            f"{source_path}"
        )


    payload = load_json_detection_sample(
        source_path
    )


    return detect_json_profile(
        source_path=source_path,
        payload=payload,
    )


def adapter_name_for_profile(
    profile: str,
) -> str:
    """
    Map detected JSON profile to its dedicated adapter module.

    No CSV adapter is exposed here by design.
    """

    mapping = {
        JSON_PROFILE_PLAIN:
            "json_plain",

        JSON_PROFILE_SLACK:
            "json_slack",

        JSON_PROFILE_SALESFORCE:
            "json_salesforce",

        JSON_PROFILE_TEAMS:
            "json_teams",

        JSON_PROFILE_GOOGLE:
            "json_google",

        JSON_PROFILE_CUSTOM_API:
            "json_custom_api",
    }


    return mapping.get(
        profile,
        "json_plain",
    )