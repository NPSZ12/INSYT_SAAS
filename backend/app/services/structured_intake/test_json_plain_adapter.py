from __future__ import annotations

import json
import tempfile

from pathlib import Path

from .adapters.json_plain import (
    normalize_plain_json_to_csv,
)


def test_json_array(root: Path) -> None:
    source_path = root / "plain_test.json"
    output_path = root / "plain_test.normalized.csv"

    payload = [
        {
            "id": 101,
            "name": "Alice",
            "email": "alice@example.com",
            "address": {
                "city": "Nashville",
                "state": "TN",
            },
            "phones": [
                "555-1000",
                "555-1001",
            ],
        },
        {
            "id": 102,
            "name": "Bob",
            "email": "bob@example.com",
            "address": {
                "city": "Knoxville",
                "state": "TN",
            },
            "phones": [
                "555-2000",
            ],
        },
        {
            "id": 103,
            "name": "Carol",
            "email": "carol@example.com",
            "address": {
                "city": "Memphis",
                "state": "TN",
                "zip": "38103",
            },
            "active": True,
        },
    ]

    source_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = normalize_plain_json_to_csv(
        source_path=source_path,
        output_path=output_path,
        package_id="TEST-JSON-PLAIN-001",
    )

    print()
    print("JSON Array Test")
    print("===============")

    print(
        "Package Count:",
        result.package.package_count,
    )

    print(
        "Record Count:",
        result.package.record_count,
    )

    print(
        output_path.read_text(
            encoding="utf-8-sig"
        )
    )


def test_jsonl(root: Path) -> None:
    source_path = root / "plain_test.jsonl"
    output_path = root / "plain_test_jsonl.normalized.csv"

    records = [
        {
            "id": 201,
            "name": "David",
            "department": "Legal",
        },
        {
            "id": 202,
            "name": "Emma",
            "department": "Finance",
            "location": {
                "city": "Atlanta",
                "state": "GA",
            },
        },
        {
            "id": 203,
            "name": "Frank",
            "department": "Operations",
        },
    ]

    with source_path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        for record in records:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
            )

            handle.write("\n")


    result = normalize_plain_json_to_csv(
        source_path=source_path,
        output_path=output_path,
        package_id="TEST-JSONL-PLAIN-001",
    )

    print()
    print("JSONL Test")
    print("==========")

    print(
        "Package Count:",
        result.package.package_count,
    )

    print(
        "Record Count:",
        result.package.record_count,
    )

    print(
        output_path.read_text(
            encoding="utf-8-sig"
        )
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        test_json_array(root)

        test_jsonl(root)


if __name__ == "__main__":
    main()