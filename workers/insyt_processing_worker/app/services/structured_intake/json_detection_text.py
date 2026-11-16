"""Detection-only text for original native JSON documents.

Never changes the original JSON, Doc ID, or native storage bytes.
Never generates CSV or performs Header Mapping.
"""

import json


def build_native_json_detection_text(
    original: bytes,
    extension: str,
) -> str:
    ext = str(extension or "").lower().lstrip(".")

    if ext not in {"json", "jsonl", "ndjson"}:
        raise ValueError("Unsupported native JSON extension.")

    # Fail closed on invalid source bytes.
    content = original.decode("utf-8-sig")

    if ext == "json":
        records = [json.loads(content)]
    else:
        records = [
            json.loads(line)
            for line in content.splitlines()
            if line.strip()
        ]

        if not records:
            raise ValueError("Empty JSONL/NDJSON source.")

    lines = []

    def emit(path, label, value):
        lines.append(f"Source path: {path}")

        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(
                value,
                ensure_ascii=False,
            )

        lines.append(f"{label}: {rendered}")

    def visit(value, path="", label="Value"):
        if isinstance(value, dict):
            if not value:
                emit(path or "$", label, "{}")

            for key, child in value.items():
                field = str(key)
                child_path = (
                    f"{path}.{field}" if path else field
                )
                visit(child, child_path, field)

        elif isinstance(value, list):
            if not value:
                emit(path or "$", label, "[]")

            for index, child in enumerate(value):
                child_path = f"{path}[{index}]"
                visit(child, child_path, label)

        else:
            emit(path or "$", label, value)

    for index, record in enumerate(records):
        if ext == "json":
            visit(record)
        else:
            visit(record, f"record[{index}]")

    return "\n".join(lines) + "\n"
