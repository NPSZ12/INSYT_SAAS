from __future__ import annotations

import json
import shutil

from pathlib import Path
from typing import Any

from .adapters.json_plain import (
    normalize_plain_json_to_csv,
)

from .json_router import (
    detect_json_source_profile,
    is_json_structured_source,
)


def prepare_json_structured_sources(
    *,
    staging_dir: Path,
) -> dict[str, Any]:
    """
    Prepare JSON structured sources before the normal APC pipeline.

    IMPORTANT:
    - Existing CSV files are never inspected or modified here.
    - Existing XL files are never inspected or modified here.
    - Only .json, .jsonl, and .ndjson are handled.
    - Original JSON files are preserved outside the APC input
      directory.
    - Normalized CSV working artifacts are placed into the APC
      input directory for the existing downstream pipeline.
    """

    staging_dir = Path(
        staging_dir
    ).resolve()

    run_root = staging_dir.parent

    structured_root = (
        run_root
        / "structured_intake"
    )

    source_root = (
        structured_root
        / "source"
    )

    manifest_path = (
        structured_root
        / "manifest.json"
    )


    source_root.mkdir(
        parents=True,
        exist_ok=True,
    )


    json_sources = [
        path
        for path in staging_dir.iterdir()
        if (
            path.is_file()
            and is_json_structured_source(
                path
            )
        )
    ]


    if not json_sources:
        return {
            "json_package_count": 0,
            "json_record_count": 0,
            "normalized_csv_count": 0,
            "manifest_path": None,
            "packages": [],
        }


    packages: list[
        dict[str, Any]
    ] = []

    total_record_count = 0


    for package_index, source_path in enumerate(
        sorted(
            json_sources,
            key=lambda value:
                value.name.lower(),
        ),
        start=1,
    ):

        profile = (
            detect_json_source_profile(
                source_path
            )
        )


        preserved_source_path = (
            source_root
            / source_path.name
        )


        shutil.move(
            str(source_path),
            str(
                preserved_source_path
            ),
        )


        #
        # Plain JSON is the first active adapter.
        #
        # Other detected profiles will receive their own
        # dedicated adapter scripts. Until those adapters are
        # enabled, do not silently flatten them as Plain JSON.
        #
        if profile != "plain":

            packages.append(
                {
                    "package_index":
                        package_index,
                        
                    "package_id":
                        f"JSON-PKG-{package_index:06d}",

                    "source_filename":
                        preserved_source_path.name,

                    "source_profile":
                        profile,

                    "status":
                        "adapter_not_enabled",

                    "original_source_path":
                        str(
                            preserved_source_path
                        ),

                    "record_count":
                        0,

                    "normalized_csv_path":
                        None,
                }
            )

            continue


        normalized_name = (
            f"{source_path.stem}"
            f".INSYT_JSON_PLAIN.csv"
        )


        normalized_csv_path = (
            staging_dir
            / normalized_name
        )


        result = (
            normalize_plain_json_to_csv(
                source_path=(
                    preserved_source_path
                ),
                output_path=(
                    normalized_csv_path
                ),
                package_id=(
                    f"JSON-PKG-"
                    f"{package_index:06d}"
                ),
            )
        )


        record_count = int(
            result.package.record_count
            or 0
        )


        total_record_count += (
            record_count
        )


        packages.append(
            {
                "package_index":
                    package_index,

                "source_filename":
                    preserved_source_path.name,

                "source_format":
                    "json",

                "source_profile":
                    profile,

                "status":
                    "normalized",

                "original_source_path":
                    str(
                        preserved_source_path
                    ),

                "normalized_csv_path":
                    str(
                        normalized_csv_path
                    ),

                "normalized_filename":
                    normalized_csv_path.name,

                "record_count":
                    record_count,

                "package_count":
                    1,
            }
        )


    manifest_payload = {
        "schema_version": 1,

        "source_family":
            "structured",

        "json_package_count":
            len(
                json_sources
            ),

        "json_record_count":
            total_record_count,

        "normalized_csv_count":
            sum(
                1
                for package in packages
                if (
                    package.get(
                        "status"
                    )
                    == "normalized"
                )
            ),

        "packages":
            packages,
    }


    manifest_path.write_text(
        json.dumps(
            manifest_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    return {
        **manifest_payload,

        "manifest_path":
            str(
                manifest_path
            ),
    }