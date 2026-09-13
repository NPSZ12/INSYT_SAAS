from __future__ import annotations

from pathlib import Path
from typing import Any


JSON_PROFILE_PLAIN = "plain"
JSON_PROFILE_SLACK = "slack"
JSON_PROFILE_SALESFORCE = "salesforce"
JSON_PROFILE_TEAMS = "teams"
JSON_PROFILE_GOOGLE = "google"
JSON_PROFILE_CUSTOM_API = "custom_api"


def _lower_keys(
    value: dict[str, Any],
) -> set[str]:
    return {
        str(key).strip().lower()
        for key in value.keys()
    }


def detect_json_profile(
    *,
    source_path: Path,
    payload: Any,
) -> str:
    """
    Detect the most likely JSON source profile.

    Detection is intentionally conservative.

    Unknown valid JSON defaults to JSON Plain rather than
    being incorrectly classified as Slack, Salesforce, etc.
    """

    filename = source_path.name.lower()


    # ---------------------------------------------------------
    # Slack
    # ---------------------------------------------------------

    if isinstance(payload, dict):

        keys = _lower_keys(payload)

        if (
            "channels" in keys
            and "users" in keys
            and (
                "messages" in keys
                or "team" in keys
                or "workspace" in keys
            )
        ):
            return JSON_PROFILE_SLACK


    # ---------------------------------------------------------
    # Salesforce
    # ---------------------------------------------------------

    if isinstance(payload, dict):

        keys = _lower_keys(payload)

        if (
            "records" in keys
            and (
                "totalsize" in keys
                or "done" in keys
            )
        ):
            return JSON_PROFILE_SALESFORCE

        attributes = payload.get(
            "attributes"
        )

        if isinstance(
            attributes,
            dict,
        ):
            attribute_keys = _lower_keys(
                attributes
            )

            if (
                "type" in attribute_keys
                or "url" in attribute_keys
            ):
                return JSON_PROFILE_SALESFORCE


    # ---------------------------------------------------------
    # Microsoft Teams
    # ---------------------------------------------------------

    if isinstance(payload, dict):

        keys = _lower_keys(payload)

        if (
            "teamid" in keys
            or "channelidentity" in keys
            or "chatid" in keys
        ):
            return JSON_PROFILE_TEAMS


    # ---------------------------------------------------------
    # Google
    # ---------------------------------------------------------

    if isinstance(payload, dict):

        keys = _lower_keys(payload)

        if (
            "spaces" in keys
            or (
                "thread" in keys
                and "sender" in keys
            )
        ):
            return JSON_PROFILE_GOOGLE


    # ---------------------------------------------------------
    # Filename hints
    #
    # These are secondary hints only.
    # ---------------------------------------------------------

    if "slack" in filename:
        return JSON_PROFILE_SLACK

    if "salesforce" in filename:
        return JSON_PROFILE_SALESFORCE

    if "teams" in filename:
        return JSON_PROFILE_TEAMS


    # ---------------------------------------------------------
    # Unknown valid JSON
    # ---------------------------------------------------------

    return JSON_PROFILE_PLAIN