from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from apc.azure_job_runner import resolve_azure_completion_status
from apc.config import Settings
from apc.db import LedgerDB
from apc.orchestrator import create_job
from apc.processing_sets import build_processing_sets
from apc.routing.train_station import route_train_station_files
from apc.stages.container_expansion import run_container_expansion
from apc.stages.inventory import run_inventory


class FailedAdapterRoutingTests(unittest.TestCase):

    def test_failed_json_does_not_enter_processing_sets(self):
        with tempfile.TemporaryDirectory(
            prefix="insyt_adapter_failure_"
        ) as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()

            bad = uploads / "malformed.json"
            bad.write_text(
                '{"objects":[{"name":"Account","records":[',
                encoding="utf-8",
            )

            good = uploads / "valid.csv"
            good.write_text(
                "name,value\nValid,123\n",
                encoding="utf-8",
            )

            originals = {
                p.name: p.read_bytes()
                for p in uploads.iterdir()
            }

            db = LedgerDB(str(root / "ledger.sqlite"))

            try:
                db.init_schema()
                settings = Settings()
                matter = "SYNTHETIC-FAILED-ADAPTER"

                job = create_job(
                    db,
                    matter_id=matter,
                    client_id="INSYT-SYNTHETIC",
                )

                run_inventory(
                    db, settings, job, matter,
                    input_dir=str(uploads),
                )

                run_container_expansion(
                    db, settings, job, matter,
                    input_dir=str(uploads),
                )

                rows = db.query(
                    """
                    SELECT file_id, extension,
                           stage_status_json, exception_json
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                self.assertEqual(len(rows), 2)

                failed = next(
                    r for r in rows
                    if r["extension"] == "json"
                )
                valid = next(
                    r for r in rows
                    if r["extension"] == "csv"
                )

                failure_status = json.loads(
                    failed["stage_status_json"] or "{}"
                )

                self.assertEqual(
                    failure_status["container_expansion"]["status"],
                    "failed",
                )

                self.assertTrue(failed["exception_json"])

                # Simulate the final job state and verify that
                # persisted expansion failure evidence still
                # prevents a clean-completion result.
                db.execute(
                    """
                    UPDATE processing_job
                    SET status='completed', exception_count=0
                    WHERE job_id=?
                    """,
                    (job,),
                )

                completion, message = (
                    resolve_azure_completion_status(
                        db=db,
                        job_id=job,
                    )
                )

                self.assertEqual(
                    completion,
                    "completed_with_exceptions",
                )
                self.assertIn("exceptions", message)


                routing = route_train_station_files(
                    db=db, job_id=job,
                )

                self.assertEqual(
                    routing["train_station_count"], 1
                )
                self.assertEqual(
                    routing["continue_count"], 1
                )

                routed = db.query(
                    """
                    SELECT file_id, stage_status_json
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                statuses = {
                    r["file_id"]: json.loads(
                        r["stage_status_json"] or "{}"
                    )["file_routing"]
                    for r in routed
                }

                self.assertEqual(
                    statuses[failed["file_id"]]["status"],
                    "train_station",
                )
                self.assertEqual(
                    statuses[failed["file_id"]]["reason"],
                    "adapter_expansion_failed_or_skipped",
                )
                self.assertEqual(
                    statuses[valid["file_id"]]["status"],
                    "continue",
                )

                sets = build_processing_sets(
                    db=db,
                    job_id=job,
                    matter_id=matter,
                    set_size=500,
                )

                self.assertEqual(
                    sets["eligible_file_count"], 1
                )

                members = db.query(
                    """
                    SELECT file_id, membership_role
                    FROM processing_set_file
                    WHERE job_id=?
                    """,
                    (job,),
                )

                self.assertEqual(len(members), 1)
                self.assertEqual(
                    members[0]["file_id"],
                    valid["file_id"],
                )
                self.assertEqual(
                    members[0]["membership_role"],
                    "primary",
                )

                self.assertEqual(
                    {
                        p.name: p.read_bytes()
                        for p in uploads.iterdir()
                    },
                    originals,
                )

                print(
                    "PASS: Failed JSON excluded from Processing Sets",
                    flush=True,
                )
                print(
                    "PASS: Unrelated CSV remains primary",
                    flush=True,
                )
                print(
                    "PASS: Failed source and exception evidence preserved",
                    flush=True,
                )

            finally:
                if hasattr(db, "close"):
                    db.close()


if __name__ == "__main__":
    unittest.main()