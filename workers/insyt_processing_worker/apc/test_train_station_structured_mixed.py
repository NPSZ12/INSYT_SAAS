from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile

from pathlib import Path
from unittest.mock import patch

from apc.azure_layout import AzureRoutingConfig, build_xl_files_staging_plan
from apc.config import Settings
from apc.db import LedgerDB
from apc.doc_id_registry import DocIdAllocation
from apc.orchestrator import create_job
from apc.processing_sets import build_processing_sets
from apc.routing.train_station import route_train_station_files
from apc.stages.container_expansion import run_container_expansion
from apc.stages.doc_id import run_doc_id_assignment
from apc.stages.inventory import run_inventory


class MixedStructuredTrainStationTests(unittest.TestCase):

    def test_mixed_source_job_without_preinventory_json_conversion(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "salesforce_synthetic_smoke.json"
        )

        self.assertTrue(fixture.is_file())

        with tempfile.TemporaryDirectory(
            prefix="insyt_mixed_train_station_"
        ) as temp:
            root = Path(temp)
            uploads = root / "uploads"
            uploads.mkdir()

            shutil.copy2(fixture, uploads / "salesforce.json")

            (uploads / "plain.json").write_text(
                json.dumps({
                    "records": [
                        {"name": "Alpha"},
                        {"name": "Beta"},
                    ]
                }),
                encoding="utf-8",
            )

            (uploads / "slack.json").write_text(
                json.dumps({
                    "workspace": {
                        "id": "W1",
                        "name": "Synthetic",
                    },
                    "channels": [{
                        "id": "C1",
                        "name": "general",
                    }],
                    "users": [{
                        "id": "U1",
                        "name": "synthetic_user",
                    }],
                    "messages": [{
                        "type": "message",
                        "channel": "C1",
                        "user": "U1",
                        "text": "Mixed-job Slack JSON",
                        "ts": "1794600000.000001",
                    }],
                }),
                encoding="utf-8",
            )

            (uploads / "ordinary.csv").write_text(
                "name,value\nDirect,123\n",
                encoding="utf-8",
            )

            with zipfile.ZipFile(
                uploads / "ordinary.zip", "w"
            ) as archive:
                archive.writestr(
                    "folder/document.txt",
                    "Ordinary ZIP synthetic text",
                )

            with zipfile.ZipFile(
                uploads / "slack-export.zip", "w"
            ) as archive:
                archive.writestr(
                    "users.json",
                    json.dumps([{
                        "id": "U1",
                        "name": "synthetic_user",
                    }]),
                )
                archive.writestr(
                    "channels.json",
                    json.dumps([{
                        "id": "C1",
                        "name": "general",
                    }]),
                )
                archive.writestr(
                    "general/2026-11-13.json",
                    json.dumps([{
                        "type": "message",
                        "user": "U1",
                        "text": "Mixed-job Slack ZIP",
                        "ts": "1794600000.000002",
                    }]),
                )

            original_hashes = {
                path.name: hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in uploads.iterdir()
            }

            self.assertEqual(len(original_hashes), 6)

            db = LedgerDB(str(root / "ledger.sqlite"))

            try:
                db.init_schema()
                settings = Settings()
                matter = "SYNTHETIC-MIXED-TRAIN-STATION"

                routing = AzureRoutingConfig.from_args(
                    workspace="capture",
                    client="INSYT-SYNTHETIC",
                    project=matter,
                    azure_write=False,
                )

                job = create_job(
                    db,
                    matter_id=matter,
                    client_id="INSYT-SYNTHETIC",
                )

                with patch.dict(
                    os.environ,
                    {"INSYT_ZIP_ADAPTER_ENABLED": "1"},
                ):
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
                    SELECT file_id, extension, parent_file_id,
                           original_path, normalized_path,
                           is_container, stage_status_json
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                # Native JSON remains a primary source document.
                # It must never generate a derived child during APC.
                self.assertEqual(len(rows), 10)

                native_names = {
                    "salesforce.json",
                    "plain.json",
                    "slack.json",
                }

                native_rows = [
                    row for row in rows
                    if Path(row["original_path"]).name
                    in native_names
                    and not row["parent_file_id"]
                ]

                self.assertEqual(len(native_rows), 3)

                for row in native_rows:
                    self.assertEqual(
                        row["extension"].lower().lstrip("."),
                        "json",
                    )
                    self.assertFalse(row["is_container"])
                    status = json.loads(
                        row["stage_status_json"] or "{}"
                    )
                    self.assertIsInstance(
                        status.get("structured_json_parent"),
                        dict,
                    )

                # No JSON-derived CSV children.
                for row in rows:
                    status = json.loads(
                        row["stage_status_json"] or "{}"
                    )
                    self.assertNotIn(
                        "structured_json_child", status
                    )

                # Slack ZIP preserves its three original JSON
                # members rather than generating a CSV.
                slack_members = [
                    row for row in rows
                    if row["parent_file_id"]
                    and row["extension"].lower().lstrip(".")
                    == "json"
                ]
                self.assertEqual(len(slack_members), 3)
                self.assertEqual(
                    {
                        Path(row["original_path"]).name
                        for row in slack_members
                    },
                    {
                        "users.json",
                        "channels.json",
                        "2026-11-13.json",
                    },
                )
                for row in slack_members:
                    self.assertFalse(row["is_container"])

                # Original CSV intake remains separate.
                direct_csv = [
                    row for row in rows
                    if Path(row["original_path"]).name
                    == "ordinary.csv"
                    and not row["parent_file_id"]
                ]
                self.assertEqual(len(direct_csv), 1)

                # Ordinary ZIP must still expand to native TXT.
                self.assertTrue(any(
                    row["parent_file_id"]
                    and row["extension"].lower().lstrip(".")
                    == "txt"
                    for row in rows
                ))

                routes = route_train_station_files(
                    db=db, job_id=job,
                )

                self.assertGreaterEqual(
                    routes["continue_count"], 3
                )

                sets = build_processing_sets(
                    db=db,
                    job_id=job,
                    matter_id=matter,
                    set_size=500,
                )

                eligible = sets["eligible_file_count"]
                self.assertGreaterEqual(eligible, 3)

                members = db.query(
                    """
                    SELECT file_id, membership_role,
                           counts_toward_set_size
                    FROM processing_set_file
                    WHERE job_id=?
                    """,
                    (job,),
                )

                for row in native_rows:
                    matches = [
                        member for member in members
                        if member["file_id"] == row["file_id"]
                    ]
                    self.assertEqual(len(matches), 1)
                    self.assertEqual(
                        matches[0]["membership_role"],
                        "primary",
                    )
                    self.assertEqual(
                        matches[0]["counts_toward_set_size"],
                        1,
                    )

                allocation = DocIdAllocation(
                    start_number=1,
                    end_number=eligible,
                    assigned_count=eligible,
                    prefix="INSYT",
                    width=9,
                    registry_blob_path="offline-test-registry",
                    previous_last_assigned_number=0,
                    new_last_assigned_number=eligible,
                )

                with patch(
                    "apc.stages.doc_id.reserve_doc_ids",
                    return_value=allocation,
                ) as reserve:
                    run_doc_id_assignment(
                        db=db,
                        settings=settings,
                        job_id=job,
                        matter_id=matter,
                        routing=routing,
                    )

                reserve.assert_called_once()
                self.assertEqual(
                    reserve.call_args.kwargs["count"],
                    eligible,
                )

                assigned = db.query(
                    """
                    SELECT file_id, doc_id
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                assigned_by_file = {
                    row["file_id"]: row["doc_id"]
                    for row in assigned
                }

                for row in native_rows:
                    doc_id = assigned_by_file[row["file_id"]]
                    self.assertTrue(doc_id)
                    self.assertNotIn(".", doc_id)

                # All six uploaded natives remain byte-identical.
                self.assertEqual(
                    {
                        path.name: hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest()
                        for path in uploads.iterdir()
                    },
                    original_hashes,
                )

                print(
                    "PASS: Three primary native JSON documents, "
                    "no JSON-derived children, independent CSV "
                    "and ZIP handling preserved",
                    flush=True,
                )

            finally:
                if hasattr(db, "close"):
                    db.close()


if __name__ == "__main__":
    unittest.main()