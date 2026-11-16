import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apc.config import Settings
from apc.db import LedgerDB
from apc.doc_id_registry import DocIdAllocation
from apc.orchestrator import create_job
from apc.processing_sets import build_processing_sets
from apc.routing.train_station import route_train_station_files
from apc.stages.container_expansion import run_container_expansion
from apc.stages.doc_id import run_doc_id_assignment
from apc.stages.inventory import run_inventory
from apc.stages.text_extraction import run_text_extraction
from apc.azure_layout import AzureRoutingConfig


from apc.stages.review_promotion import run_review_promotion
from app.services.document_lifecycle_writer import (
    build_document_lifecycle_rows,
)


class NativeJsonSQLiteIntegrationTests(unittest.TestCase):
    """JSON follows normal native-text processing, without conversion."""

    def test_plain_json(self):
        self._check_native_json("plain")

    def test_salesforce_json(self):
        self._check_native_json("salesforce")

    def _check_native_json(self, profile):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            uploads = root / "uploads"
            uploads.mkdir()

            records = [
                {"name": "Alex Example", "record_id": "R001"},
                {"name": "Jordan Example", "record_id": "R002"},
            ]

            if profile == "salesforce":
                records = [
                    {
                        "attributes": {"type": "Contact"},
                        "Id": f"003{i:012d}",
                        **record,
                    }
                    for i, record in enumerate(records, 1)
                ]
                payload = {
                    "totalSize": len(records),
                    "done": True,
                    "records": records,
                }
            else:
                payload = records

            native = uploads / f"{profile}.json"
            native.write_text(
                json.dumps(payload), encoding="utf-8"
            )

            ordinary = uploads / "ordinary.csv"
            ordinary.write_text(
                "name,value\nIndependent,123\n",
                encoding="utf-8",
            )

            original_native = native.read_bytes()
            original_csv = ordinary.read_bytes()
            native_hash = hashlib.sha256(
                original_native
            ).hexdigest()

            db = LedgerDB(str(root / "ledger.sqlite"))

            try:
                db.init_schema()
                settings = Settings()
                matter = "NATIVE-JSON-SMOKE"
                job = create_job(
                    db,
                    matter_id=matter,
                    client_id="SYNTHETIC",
                )

                routing = AzureRoutingConfig.from_args(
                    workspace="capture",
                    client="SYNTHETIC",
                    project=matter,
                    azure_write=False,
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
                    SELECT file_id, original_path, extension,
                           is_container, parent_file_id,
                           stage_status_json
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                # Two originals; no generated documents.
                self.assertEqual(len(rows), 2)
                self.assertFalse(
                    any(row["parent_file_id"] for row in rows)
                )

                json_rows = [
                    row for row in rows
                    if row["extension"].lower().lstrip(".")
                    == "json"
                ]
                self.assertEqual(len(json_rows), 1)
                self.assertFalse(json_rows[0]["is_container"])

                status = json.loads(
                    json_rows[0]["stage_status_json"] or "{}"
                )
                self.assertIsInstance(
                    status.get("structured_json_parent"),
                    dict,
                )

                routes = route_train_station_files(
                    db=db, job_id=job,
                )
                self.assertEqual(
                    routes["continue_count"], 2
                )

                sets = build_processing_sets(
                    db=db, job_id=job,
                    matter_id=matter, set_size=500,
                )
                self.assertEqual(
                    sets["eligible_file_count"], 2
                )

                allocation = DocIdAllocation(
                    start_number=1,
                    end_number=2,
                    assigned_count=2,
                    prefix="INSYT",
                    width=9,
                    registry_blob_path="offline-test-registry",
                    previous_last_assigned_number=0,
                    new_last_assigned_number=2,
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
                    reserve.call_args.kwargs["count"], 2
                )

                run_text_extraction(
                    db, settings, job, matter,
                    workspace="capture",
                )

                # Shared native/text preparation, not a JSON
                # staging planner or CSV conversion.
                review_root = root / "review"
                run_review_promotion(
                    db=db,
                    settings=settings,
                    job_id=job,
                    matter_id=matter,
                    output_root=str(review_root),
                )

                native_doc_id = db.query_one(
                    """
                    SELECT doc_id FROM file_processing_metrics
                    WHERE job_id=?
                      AND lower(extension)='json'
                    """,
                    (job,),
                )["doc_id"]

                prepared = review_root / job / "source"
                prepared_native = (
                    prepared / "native" /
                    f"{native_doc_id}.json"
                )
                prepared_text = (
                    prepared / "text" /
                    f"{native_doc_id}.txt"
                )

                self.assertTrue(prepared_native.is_file())
                self.assertTrue(prepared_text.is_file())
                self.assertEqual(
                    prepared_native.read_bytes(),
                    original_native,
                )
                self.assertIn(
                    b"Example",
                    prepared_text.read_bytes(),
                )

                # Simulate only the confirmed staging-result
                # metadata, not an Azure upload or Detection job.
                prefix = (
                    f"SYNTHETIC/capture/{matter}/"
                    f"processing_center/staged/{job}"
                )
                payload = {
                    "uploads": [
                        {
                            "doc_id": native_doc_id,
                            "kind": "native",
                            "status": "uploaded",
                            "blob_path": (
                                f"{prefix}/native/"
                                f"{native_doc_id}.json"
                            ),
                            "bytes": prepared_native.stat().st_size,
                        },
                        {
                            "doc_id": native_doc_id,
                            "kind": "text",
                            "status": "uploaded",
                            "blob_path": (
                                f"{prefix}/text/"
                                f"{native_doc_id}.txt"
                            ),
                            "bytes": prepared_text.stat().st_size,
                        },
                    ],
                }

                lifecycle = build_document_lifecycle_rows(
                    ledger_db=db,
                    workspace="capture",
                    client="SYNTHETIC",
                    project=matter,
                    source_job_id=job,
                    staging_payloads=[payload],
                )

                match = [
                    item for item in lifecycle
                    if item["doc_id"] == native_doc_id
                ]
                self.assertEqual(len(match), 1)
                self.assertEqual(
                    match[0]["detection_status"],
                    "READY",
                )
                self.assertEqual(
                    match[0]["ingestion_status"],
                    "COMPLETE",
                )

                final = db.query(
                    """
                    SELECT extension, doc_id, is_container,
                           text_bytes
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job,),
                )

                self.assertEqual(len(final), 2)

                for row in final:
                    self.assertTrue(row["doc_id"])
                    self.assertFalse(row["is_container"])

                json_final = next(
                    row for row in final
                    if row["extension"].lower().lstrip(".")
                    == "json"
                )

                self.assertGreater(
                    int(json_final["text_bytes"] or 0), 0
                )

                self.assertEqual(
                    hashlib.sha256(native.read_bytes()).hexdigest(),
                    native_hash,
                )
                self.assertEqual(
                    native.read_bytes(), original_native
                )
                self.assertEqual(
                    ordinary.read_bytes(), original_csv
                )

            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
