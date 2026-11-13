from __future__ import annotations

import json
import shutil

from pathlib import Path
from typing import Any

from .json_csv_partition import (
    partition_normalized_json_csv,
)

from .adapters.json_plain import (
    normalize_plain_json_to_csv,
)

from .adapters.json_salesforce import (
    normalize_salesforce_json_to_csv,
)

from .adapters.json_slack import (
    is_slack_export_zip,
    normalize_slack_json_to_csv,
    normalize_slack_zip_to_csv,
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
    - JSON structured sources and confirmed Slack export ZIPs
      are handled here.
    - Ordinary ZIP files are not intercepted.
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


    structured_sources = [
        path
        for path in staging_dir.iterdir()
        if (
            path.is_file()
            and (
                is_json_structured_source(
                    path
                )
                or is_slack_export_zip(
                    path
                )
            )
        )
    ]


    if not structured_sources:
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
            structured_sources,
            key=lambda value:
                value.name.lower(),
        ),
        start=1,
    ):

        if is_slack_export_zip(
            source_path
        ):
            profile = "slack"

        else:
            profile = (
                detect_json_source_profile(
                    source_path
                )
            )


        preserved_source_path = (
            source_root
            / source_path.name
        )


        if profile in {"plain", "salesforce"}:
            # Keep the original in APC input for inventory.
            # Normalize from an independent preserved copy.
            # The inventory callback will establish its
            # parent/child relationships before processing sets.
            shutil.copy2(
                str(source_path),
                str(preserved_source_path),
            )
        else:
            shutil.move(
                str(source_path),
                str(preserved_source_path),
            )


        #
        # Plain JSON is the first active adapter.
        #
        # Other detected profiles will receive their own
        # dedicated adapter scripts. Until those adapters are
        # enabled, do not silently flatten them as Plain JSON.
        #
        if profile not in {
            "plain",
            "slack",
            "salesforce",
        }:

            packages.append(
                {
                    "package_index":
                        package_index,

                    "package_id":
                        f"JSON-PKG-{package_index:06d}",

                    "source_filename":
                        preserved_source_path.name,

                    "source_format":
                        "json",

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

                    "package_count":
                        1,

                    "group_counts":
                        {},

                    "normalized_csv_path":
                        None,
                }
            )

            continue


        package_id = (
            f"JSON-PKG-"
            f"{package_index:06d}"
        )


        if profile == "slack":

            normalized_name = (
                f"{source_path.stem}"
                f".INSYT_JSON_SLACK.csv"
            )

            normalized_csv_path = (
                staging_dir
                / normalized_name
            )

            if (
                preserved_source_path
                .suffix
                .lower()
                == ".zip"
            ):
                result = (
                    normalize_slack_zip_to_csv(
                        source_path=(
                            preserved_source_path
                        ),
                        output_path=(
                            normalized_csv_path
                        ),
                        package_id=(
                            package_id
                        ),
                    )
                )

            else:
                result = (
                    normalize_slack_json_to_csv(
                        source_path=(
                            preserved_source_path
                        ),
                        output_path=(
                            normalized_csv_path
                        ),
                        package_id=(
                            package_id
                        ),
                    )
                )

        elif profile == "salesforce":

            normalized_name = (
                f"{source_path.stem}"
                f".INSYT_JSON_SALESFORCE.csv"
            )

            normalized_csv_path = (
                staging_dir / normalized_name
            )

            result = normalize_salesforce_json_to_csv(
                source_path=preserved_source_path,
                output_path=normalized_csv_path,
                package_id=package_id,
            )

        else:

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
                        package_id
                    ),
                )
            )


        record_count = int(
            result.package.record_count or 0
        )

        normalized_children = [
            {
                "path": normalized_csv_path,
                "part_number": 1,
                "record_count": record_count,
                "first_record": 1 if record_count else 0,
                "last_record": record_count,
            }
        ]

        if profile in {"plain", "salesforce"}:
            partition_dir = (
                structured_root
                / "partitions"
                / f"package_{package_index:06d}"
            )

            partitions = partition_normalized_json_csv(
                source_csv=normalized_csv_path,
                output_dir=partition_dir,
            )

            partition_count = sum(
                int(part["record_count"])
                for part in partitions
            )

            if partition_count != record_count:
                raise RuntimeError(
                    "JSON partition record totals do not match "
                    "the normalized source population."
                )

            if len(partitions) == 1:
                Path(partitions[0]["path"]).unlink()

            else:
                targets = [
                    (
                        Path(part["path"]),
                        staging_dir / (
                            f"{source_path.stem}"
                            f".INSYT_JSON_{profile.upper()}."
                            f"part{int(part['part_number']):04d}.csv"
                        ),
                        part,
                    )
                    for part in partitions
                ]

                if any(
                    target.exists()
                    for _, target, _ in targets
                ):
                    raise FileExistsError(
                        "JSON partition destination already exists."
                    )

                for temporary, target, _ in targets:
                    shutil.move(
                        str(temporary),
                        str(target),
                    )

                normalized_children = [
                    {
                        "path": target,
                        "part_number": int(
                            part["part_number"]
                        ),
                        "record_count": int(
                            part["record_count"]
                        ),
                        "first_record": int(
                            part["first_record"]
                        ),
                        "last_record": int(
                            part["last_record"]
                        ),
                    }
                    for _, target, part in targets
                ]

                normalized_csv_path.unlink()


        total_record_count += (
            record_count
        )


        for child in normalized_children:
            child_path = Path(child["path"])

            packages.append(
                {
                    "package_index": package_index,
                    "package_id": package_id,
                    "group_counts": result.group_counts,
                    "adapter": (
                        result.package.metadata.get("adapter")
                    ),
                    "source_filename": (
                        preserved_source_path.name
                    ),
                    "source_format": "json",
                    "source_profile": profile,
                    "status": "normalized",
                    "original_source_path": str(
                        preserved_source_path
                    ),
                    "normalized_csv_path": str(
                        child_path
                    ),
                    "normalized_filename": (
                        child_path.name
                    ),
                    "record_count": int(
                        child["record_count"]
                    ),
                    "source_record_start": int(
                        child["first_record"]
                    ),
                    "source_record_end": int(
                        child["last_record"]
                    ),
                    "child_number": int(
                        child["part_number"]
                    ),
                    "source_total_record_count": record_count,
                    "package_count": 1,
                }
            )

    manifest_payload = {
        "schema_version": 1,

        "source_family":
            "structured",

        "json_package_count":
            len(
                structured_sources
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