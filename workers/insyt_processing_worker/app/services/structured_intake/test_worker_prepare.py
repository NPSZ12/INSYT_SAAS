from __future__ import annotations

import json
import tempfile

from pathlib import Path

from .worker_prepare import (
    prepare_json_structured_sources,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        run_root = Path(temp_dir)

        staging_dir = (
            run_root
            / "uploads"
        )

        staging_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


        #
        # Existing non-JSON sources.
        #
        # These must remain untouched.
        #

        (staging_dir / "existing.csv").write_text(
            "id,name\n1,Alice\n",
            encoding="utf-8",
        )

        (staging_dir / "document.pdf").write_bytes(
            b"%PDF-TEST"
        )


        #
        # Plain JSON source.
        #

        json_source = (
            staging_dir
            / "customers.json"
        )

        json_source.write_text(
            json.dumps(
                [
                    {
                        "id": 101,
                        "name": "Bob",
                        "address": {
                            "city": "Nashville",
                            "state": "TN",
                        },
                    },
                    {
                        "id": 102,
                        "name": "Carol",
                        "address": {
                            "city": "Knoxville",
                            "state": "TN",
                        },
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )


        print()
        print("Before Preparation")
        print("==================")

        for path in sorted(
            staging_dir.iterdir()
        ):
            print(path.name)


        result = (
            prepare_json_structured_sources(
                staging_dir=staging_dir,
            )
        )


        print()
        print("Preparation Result")
        print("==================")

        print(
            "JSON Package Count:",
            result.get(
                "json_package_count"
            ),
        )

        print(
            "JSON Record Count:",
            result.get(
                "json_record_count"
            ),
        )

        print(
            "Normalized CSV Count:",
            result.get(
                "normalized_csv_count"
            ),
        )

        print(
            "Manifest:",
            result.get(
                "manifest_path"
            ),
        )


        print()
        print("After Preparation")
        print("=================")

        for path in sorted(
            staging_dir.iterdir()
        ):
            print(path.name)


        print()
        print("Preserved JSON Sources")
        print("======================")

        source_dir = (
            run_root
            / "structured_intake"
            / "source"
        )

        for path in sorted(
            source_dir.iterdir()
        ):
            print(path.name)


        print()
        print("Normalized CSV")
        print("==============")

        normalized_csv = (
            staging_dir
            / "customers.INSYT_JSON_PLAIN.csv"
        )

        print(
            normalized_csv.read_text(
                encoding="utf-8-sig"
            )
        )


        #
        # Safety checks.
        #

        assert (
            staging_dir
            / "existing.csv"
        ).exists()

        assert (
            staging_dir
            / "document.pdf"
        ).exists()

        assert not (
            staging_dir
            / "customers.json"
        ).exists()

        assert (
            source_dir
            / "customers.json"
        ).exists()

        assert normalized_csv.exists()

        assert (
            result.get(
                "json_package_count"
            )
            == 1
        )

        assert (
            result.get(
                "json_record_count"
            )
            == 2
        )


        print()
        print("Worker Preparation Test: PASS")


if __name__ == "__main__":
    main()