from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import ijson


class IncompleteJsonNativeScan(RuntimeError):
    """JSON scan incomplete; NO_HITS classification is prohibited."""


def prepare_json_detection_text(
    source_path: Path,
    text_path: Path,
    *,
    max_values: int = 100000,
    max_text_bytes: int = 64 * 1024 * 1024,
) -> dict:
    """Prepare detection-only scalar text without changing native JSON."""
    source = Path(source_path)
    target = Path(text_path)
    lineage = target.with_suffix(target.suffix + ".paths.jsonl")

    if source.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
        raise ValueError("Unsupported JSON extension.")

    if not source.is_file():
        raise FileNotFoundError(source)

    if target.exists() or lineage.exists():
        raise FileExistsError("Detection output already exists.")

    if max_values < 1 or max_text_bytes < 1:
        raise ValueError("Detection limits must be positive.")

    target.parent.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    temp_text = target.with_name(target.name + "." + token + ".tmp")
    temp_paths = lineage.with_name(lineage.name + "." + token + ".tmp")

    count = 0
    text_bytes = 0
    published_text = False

    # Maintain exact array indexes independently of ijson's
    # generic "item" path segments.
    stack = []
    root_index = 0
    multiple_roots = source.suffix.lower() in {".jsonl", ".ndjson"}

    def escape_pointer(value):
        return str(value).replace("~", "~0").replace("/", "~1")

    def next_path():
        nonlocal root_index

        if not stack:
            path = (str(root_index),) if multiple_roots else ()
            root_index += 1
            return path

        parent = stack[-1]

        if parent["kind"] == "array":
            index = parent["next_index"]
            parent["next_index"] += 1
            return parent["path"] + (str(index),)

        key = parent["pending_key"]
        if key is None:
            raise IncompleteJsonNativeScan(
                "JSON object value without a field name."
            )

        parent["pending_key"] = None
        return parent["path"] + (key,)

    try:
        try:
            with (
                source.open("rb") as input_file,
                temp_text.open("wb") as text_file,
                temp_paths.open("w", encoding="utf-8") as paths_file,
            ):
                events = ijson.parse(
                    input_file,
                    multiple_values=source.suffix.lower()
                    in {".jsonl", ".ndjson"},
                )

                for prefix, event, value in events:
                    if event == "map_key":
                        if not stack or stack[-1]["kind"] != "map":
                            raise IncompleteJsonNativeScan(
                                "Invalid JSON object-key sequence."
                            )
                        stack[-1]["pending_key"] = str(value)
                        continue

                    if event in {"end_map", "end_array"}:
                        if not stack:
                            raise IncompleteJsonNativeScan(
                                "Unexpected JSON closing event."
                            )
                        expected_kind = (
                            "map" if event == "end_map" else "array"
                        )
                        if stack[-1]["kind"] != expected_kind:
                            raise IncompleteJsonNativeScan(
                                "Mismatched JSON closing event."
                            )
                        stack.pop()
                        continue

                    path_parts = next_path()

                    if event in {"start_map", "start_array"}:
                        stack.append({
                            "kind": (
                                "map" if event == "start_map" else "array"
                            ),
                            "path": path_parts,
                            "next_index": 0,
                            "pending_key": None,
                        })
                        continue

                    if event not in {"string", "number"}:
                        continue

                    json_pointer = "".join(
                        "/" + escape_pointer(part)
                        for part in path_parts
                    )

                    scalar = re.sub(
                        r"\s+", " ", str(value)
                    ).strip()

                    if not scalar:
                        continue

                    encoded = (scalar + "\n").encode("utf-8")

                    if count + 1 > max_values:
                        raise IncompleteJsonNativeScan(
                            "JSON value count limit exceeded."
                        )

                    if text_bytes + len(encoded) > max_text_bytes:
                        raise IncompleteJsonNativeScan(
                            "JSON detection byte limit exceeded."
                        )

                    paths_file.write(
                        json.dumps({
                            "json_path": prefix,
                            "json_pointer": json_pointer,
                            "text_offset": text_bytes,
                            "text_length": len(encoded),
                        }) + "\n"
                    )

                    text_file.write(encoded)
                    text_bytes += len(encoded)
                    count += 1

        except ijson.common.JSONError as exc:
            raise IncompleteJsonNativeScan(
                f"JSON parsing incomplete or invalid: {exc}"
            ) from exc

        if count == 0:
            raise IncompleteJsonNativeScan(
                "No usable scalar values available for detection."
            )

        if target.exists() or lineage.exists():
            raise FileExistsError(
                "Detection output appeared during scan."
            )

        os.replace(temp_text, target)
        published_text = True
        os.replace(temp_paths, lineage)

        return {
            "status": "prepared",
            "values_scanned": count,
            "text_bytes": text_bytes,
            "text_path": str(target),
            "lineage_path": str(lineage),
        }

    except Exception:
        if published_text:
            target.unlink(missing_ok=True)
        raise

    finally:
        temp_text.unlink(missing_ok=True)
        temp_paths.unlink(missing_ok=True)