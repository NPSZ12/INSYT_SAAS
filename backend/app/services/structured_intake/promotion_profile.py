"""Pure JSON source classifier for explicit manual Cyber2 Promotion."""
import json
from pathlib import Path

from .json_detector import detect_json_profile

EXTENSIONS = {".json", ".jsonl", ".ndjson"}


def classify_promoted_json(
    source_bytes: bytes,
    original_filename: str,
    source_extension: str,
) -> str:
    extension = str(source_extension or "").strip().lower()
    if extension and not extension.startswith("."):
        extension = "." + extension

    if extension not in EXTENSIONS:
        raise ValueError("Unsupported native JSON extension.")
    if not source_bytes:
        raise ValueError("Empty native JSON source.")

    try:
        text = source_bytes.decode("utf-8-sig")
        if extension in {".jsonl", ".ndjson"}:
            first = next(
                (line for line in text.splitlines() if line.strip()),
                None,
            )
            if first is None:
                raise ValueError("No JSON records.")
            payload = json.loads(first)
        else:
            payload = json.loads(text)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid native JSON.") from exc

    filename = Path(original_filename or "source.json").name
    profile = detect_json_profile(
        source_path=Path(filename),
        payload=payload,
    )

    if profile == "plain":
        lower_name = filename.lower()
        declared = ""
        if isinstance(payload, dict):
            declared = str(
                payload.get("source_profile")
                or payload.get("source_system")
                or ""
            ).strip().lower()

        if (
            "custom_api" in lower_name
            or "custom-api" in lower_name
            or declared in {"custom_api", "custom-api"}
            or (
                isinstance(payload, dict)
                and "custom_records" in payload
            )
        ):
            profile = "custom_api"

    if profile not in {
        "plain", "slack", "salesforce",
        "teams", "google", "custom_api",
    }:
        raise ValueError("Unsupported JSON source profile.")

    return profile
