from __future__ import annotations

import json
import ijson

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
    Build a small structural signature without loading
    the complete JSON document into memory.

    Classification is preliminary. The selected converter
    remains responsible for full source validation.
    """
    extension = source_path.suffix.strip().lower()

    if extension == ".json":
        with source_path.open("rb") as handle:
            # Allow UTF-8 BOM without materializing the file.
            if handle.read(3) != bytes((0xEF, 0xBB, 0xBF)):
                handle.seek(0)

            events = ijson.parse(handle)

            try:
                _, root_event, _ = next(events)
            except StopIteration:
                raise ValueError("Empty JSON document.")

            if root_event == "start_map":
                sample: dict[str, Any] = {}

                for prefix, event, value in events:
                    if prefix == "" and event == "map_key":
                        sample[str(value)] = None

                    elif (
                        prefix == "attributes"
                        and event == "start_map"
                    ):
                        sample["attributes"] = {}

                    elif (
                        prefix.startswith("attributes.")
                        and event in {
                            "string", "number",
                            "boolean", "null"
                        }
                    ):
                        attributes = sample.setdefault(
                            "attributes", {}
                        )
                        if isinstance(attributes, dict):
                            attributes[
                                prefix[len("attributes."):]
                            ] = value

                    elif (
                        prefix == "records"
                        and event == "start_array"
                    ):
                        sample["records"] = []

                return sample

            if root_event == "start_array":
                first: dict[str, Any] = {}

                for prefix, event, value in events:
                    if prefix == "item" and event == "end_map":
                        break

                    if (
                        prefix == "item"
                        and event not in {
                            "start_map", "end_map", "map_key"
                        }
                    ):
                        # Generic JSON arrays may contain
                        # scalar values or nested arrays.
                        # They are not Salesforce objects.
                        return {}

                    if prefix == "item" and event == "map_key":
                        first[str(value)] = None

                    elif (
                        prefix == "item.attributes"
                        and event == "start_map"
                    ):
                        first["attributes"] = {}

                    elif (
                        prefix.startswith("item.attributes.")
                        and event in {
                            "string", "number",
                            "boolean", "null"
                        }
                    ):
                        attributes = first.setdefault(
                            "attributes", {}
                        )
                        if isinstance(attributes, dict):
                            attributes[
                                prefix[len("item.attributes."):]
                            ] = value

                return first

            raise ValueError(
                "Unsupported JSON root for profile detection."
            )

    if extension in {".jsonl", ".ndjson"}:
        with source_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as handle:
            for line in handle:
                value = line.strip()
                if value:
                    return json.loads(value)
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