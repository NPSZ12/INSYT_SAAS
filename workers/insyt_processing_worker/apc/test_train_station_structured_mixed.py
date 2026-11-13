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

                self.assertEqual(len(rows), 11)

                structured_parents = []
                structured_children = []

                for row in rows:
                    status = json.loads(
                        row["stage_status_json"] or "{}"
                    )

                    if isinstance(
                        status.get("structured_json_parent"),
                        dict,
                    ):
                        structured_parents.append(row)

                    if isinstance(
                        status.get("structured_json_child"),
                        dict,
                    ):
                        structured_children.append(row)

                self.assertEqual(len(structured_parents), 4)
                self.assertEqual(len(structured_children), 4)

                parent_ids = {
                    row["file_id"]
                    for row in structured_parents
                }

                expected_counts = {
                    "salesforce": 4,
                    "plain": 2,
                    "slack": 1,
                }

                observed = []

                for row in structured_children:
                    status = json.loads(
                        row["stage_status_json"]
                    )
                    metadata = status["structured_json_child"]
                    profile = metadata["source_profile"]

                    self.assertIn(
                        row["parent_file_id"],
                        parent_ids,
                    )
                    self.assertEqual(
                        metadata["parent_file_id"],
                        row["parent_file_id"],
                    )
                    self.assertEqual(row["extension"], "csv")
                    self.assertFalse(row["is_container"])

                    with Path(row["original_path"]).open(
                        "r",
                        encoding="utf-8-sig",
                        newline="",
                    ) as stream:
                        records = list(csv.DictReader(stream))

                    self.assertEqual(
                        len(records),
                        metadata["record_count"],
                    )

                    if profile == "slack":
                        self.assertEqual(len(records), 1)
                    else:
                        self.assertEqual(
                            len(records),
                            expected_counts[profile],
                        )

                    observed.append(
                        metadata["derivation_method"]
                    )

                self.assertEqual(len(set(observed)), 4)

                print(
                    "PASS: Four structured formats, "
                    "four CSV children, correct record counts",
                    flush=True,
                )

                routes = route_train_station_files(
                    db=db, job_id=job,
                )

                self.assertEqual(
                    routes["continue_count"], 6
                )

                sets = build_processing_sets(
                    db=db,
                    job_id=job,
                    matter_id=matter,
                    set_size=500,
                )

                self.assertEqual(
                    sets["eligible_file_count"], 6
                )

                members = db.query(
                    """
                    SELECT file_id, membership_role,
                           counts_toward_set_size
                    FROM processing_set_file
                    WHERE job_id=?
                    """,
                    (job,),
                )

                for parent in structured_parents:
                    support = [
                        member
                        for member in members
                        if member["file_id"] == parent["file_id"]
                    ]
                    self.assertEqual(len(support), 1)
                    self.assertEqual(
                        support[0]["counts_toward_set_size"],
                        0,
                    )

                self.assertEqual(
                    sum(
                        int(m["counts_toward_set_size"])
                        for m in members
                    ),
                    6,
                )

                allocation = DocIdAllocation(
                    start_number=1,
                    end_number=6,
                    assigned_count=6,
                    prefix="INSYT",
                    width=9,
                    registry_blob_path="offline-test-registry",
                    previous_last_assigned_number=0,
                    new_last_assigned_number=6,
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
                    reserve.call_args.kwargs["count"], 6
                )

                assigned = db.query(
                    """
                    SELECT file_id, doc_id, parent_file_id
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                by_id = {
                    row["file_id"]: row
                    for row in assigned
                }

                for child in structured_children:
                    parent_doc_id = by_id[
                        child["parent_file_id"]
                    ]["doc_id"]
                    child_doc_id = by_id[
                        child["file_id"]
                    ]["doc_id"]

                    self.assertTrue(parent_doc_id)
                    self.assertEqual(
                        child_doc_id,
                        parent_doc_id + ".1",
                    )

                plan = build_xl_files_staging_plan(
                    db=db,
                    job_id=job,
                    routing=routing,
                )

                self.assertEqual(len(plan), 8)
                self.assertEqual(
                    sum(
                        bool(item["is_structured_parent"])
                        for item in plan
                    ),
                    4,
                )
                self.assertEqual(
                    sum(
                        bool(item["is_csv_child"])
                        for item in plan
                    ),
                    4,
                )

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
                    "PASS: Six primary documents, "
                    "four support parents, family Doc IDs, "
                    "eight common staging entries",
                    flush=True,
                )
                print(
                    "PASS: All six native uploads unchanged",
                    flush=True,
                )

            finally:
                if hasattr(db, "close"):
                    db.close()


if __name__ == "__main__":
    unittest.main()