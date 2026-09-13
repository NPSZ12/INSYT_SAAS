from __future__ import annotations

import json
import tempfile

from pathlib import Path

from apc.config import DEFAULT_SETTINGS
from apc.db import LedgerDB
from apc.stages.inventory import run_inventory

from .provenance import (
    apply_structured_json_provenance,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        staging_dir = root / "uploads"
        structured_dir = root / "structured_intake"

        staging_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        structured_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


        #
        # Ordinary CSV.
        #
        # This must remain untouched.
        #

        normal_csv = (
            staging_dir
            / "existing.csv"
        )

        normal_csv.write_text(
            "id,name\n1,Alice\n",
            encoding="utf-8",
        )


        #
        # JSON-normalized CSV working artifact.
        #

        json_csv = (
            staging_dir
            / "customers.INSYT_JSON_PLAIN.csv"
        )

        json_csv.write_text(
            (
                "INSYT_Source_Record_ID,"
                "INSYT_Record_Type,"
                "id,name\n"
                "1,object,101,Bob\n"
                "2,object,102,Carol\n"
            ),
            encoding="utf-8",
        )


        #
        # Structured-intake manifest.
        #

        manifest_path = (
            structured_dir
            / "manifest.json"
        )

        manifest_payload = {
            "schema_version": 1,
            "source_family": "structured",
            "json_package_count": 1,
            "json_record_count": 2,
            "normalized_csv_count": 1,
            "packages": [
                {
                    "package_index": 1,
                    "package_id": "JSON-PKG-000001",
                    "source_filename": "customers.json",
                    "source_format": "json",
                    "source_profile": "plain",
                    "status": "normalized",
                    "original_source_path": (
                        str(
                            structured_dir
                            / "source"
                            / "customers.json"
                        )
                    ),
                    "normalized_csv_path": str(
                        json_csv
                    ),
                    "normalized_filename": (
                        json_csv.name
                    ),
                    "record_count": 2,
                    "package_count": 1,
                }
            ],
        }

        manifest_path.write_text(
            json.dumps(
                manifest_payload,
                indent=2,
            ),
            encoding="utf-8",
        )


        #
        # Local test ledger.
        #

        db_path = (
            root
            / "test_ledger.db"
        )

        db = LedgerDB(
            str(db_path)
        )

        db.init_schema()


        matter_id = "TEST_JSON_PROVENANCE"
        job_id = "JOB-JSON-PROVENANCE-TEST"


        db.execute(
            """
            INSERT INTO processing_job (
                job_id,
                matter_id,
                client_id,
                created_at,
                status,
                metadata_json
            )
            VALUES (
                ?,
                ?,
                ?,
                datetime('now'),
                ?,
                '{}'
            )
            """,
            (
                job_id,
                matter_id,
                "TEST_CLIENT",
                "running",
            ),
        )


        run_inventory(
            db,
            DEFAULT_SETTINGS,
            job_id,
            matter_id,
            input_dir=str(
                staging_dir
            ),
        )


        result = (
            apply_structured_json_provenance(
                db=db,
                job_id=job_id,
                staging_dir=staging_dir,
                manifest_path=manifest_path,
            )
        )


        print()
        print("Provenance Result")
        print("=================")
        print(result)


        rows = db.query(
            """
            SELECT
                normalized_path,
                stage_status_json
            FROM file_processing_metrics
            WHERE job_id=?
            ORDER BY normalized_path
            """,
            (
                job_id,
            ),
        )


        print()
        print("Inventory Rows")
        print("==============")

        for row in rows:

            normalized_path = str(
                row["normalized_path"]
            )

            status = json.loads(
                row["stage_status_json"]
                or "{}"
            )

            print()
            print(
                "File:",
                normalized_path,
            )

            print(
                "Stage Status:",
                json.dumps(
                    status,
                    indent=2,
                ),
            )


            if (
                normalized_path
                == "existing.csv"
            ):
                assert (
                    "structured_source"
                    not in status
                )


            if (
                normalized_path
                == json_csv.name
            ):
                structured_source = (
                    status.get(
                        "structured_source"
                    )
                    or {}
                )

                assert (
                    structured_source.get(
                        "source_format"
                    )
                    == "json"
                )

                assert (
                    structured_source.get(
                        "source_profile"
                    )
                    == "plain"
                )

                assert (
                    structured_source.get(
                        "record_count"
                    )
                    == 2
                )

                assert (
                    structured_source.get(
                        "package_id"
                    )
                    == "JSON-PKG-000001"
                )


        assert (
            result.get(
                "updated_count"
            )
            == 1
        )


        db.close()


        print()
        print(
            "JSON Provenance Test: PASS"
        )


if __name__ == "__main__":
    main()