from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch, MagicMock

from apc.azure_layout import (
    AzureRoutingConfig,
    build_xl_files_staging_plan,
)
from apc.config import Settings
from apc.db import LedgerDB
from apc.doc_id_registry import DocIdAllocation
from apc.orchestrator import create_job
from apc.processing_sets import build_processing_sets
from apc.routing.train_station import route_train_station_files
from apc.stages.doc_id import run_doc_id_assignment
from apc.stages.inventory import run_inventory

from app.services.structured_intake.json_family import (
    link_plain_json_families,
)
from app.services.structured_intake.provenance import (
    apply_structured_json_provenance,
)
from app.services.structured_intake.worker_prepare import (
    prepare_json_structured_sources,
)


class JsonSQLiteIntegrationTests(unittest.TestCase):

    def test_json_family_end_to_end_offline(self):
        self._assert_json_family_end_to_end_offline("plain")

    def test_salesforce_family_end_to_end_offline(self):
        self._assert_json_family_end_to_end_offline(
            "salesforce"
        )

    def _assert_json_family_end_to_end_offline(self, profile):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "uploads"
            staging.mkdir()

            source = staging / "synthetic.json"
            unrelated = staging / "unrelated.csv"

            records = [
                {
                    "record_id": number,
                    "name": f"Person {number}",
                    "category": "synthetic",
                }
                for number in range(1, 20002)
            ]

            if profile == "salesforce":
                records = [
                    {
                        "attributes": {
                            "type": "Contact"
                        },
                        "Id": f"003{number:012d}",
                        **record,
                    }
                    for number, record in enumerate(
                        records, start=1
                    )
                ]

            payload = (
                records
                if profile == "plain"
                else {
                    "totalSize": len(records),
                    "done": True,
                    "records": records,
                }
            )

            source.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            unrelated.write_text(
                "record_id,name\n999999,Independent\n",
                encoding="utf-8",
            )

            original_bytes = source.read_bytes()
            original_hash = hashlib.sha256(
                original_bytes
            ).hexdigest()
            unrelated_bytes = unrelated.read_bytes()

            preparation = prepare_json_structured_sources(
                staging_dir=staging,
            )

            self.assertEqual(
                preparation["json_record_count"],
                20001,
            )
            self.assertEqual(
                preparation["normalized_csv_count"],
                3,
            )

            manifest_path = Path(
                preparation["manifest_path"]
            )
            self.assertTrue(manifest_path.is_file())

            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )

            packages = sorted(
                [
                    package
                    for package in manifest["packages"]
                    if (
                        package.get("status") == "normalized"
                        and package.get("source_profile") == profile
                    )
                ],
                key=lambda package: int(
                    package["child_number"]
                ),
            )

            self.assertEqual(len(packages), 3)

            expected_ranges = [
                (1, 10000, 10000),
                (10001, 20000, 10000),
                (20001, 20001, 1),
            ]

            for package, expected in zip(
                packages,
                expected_ranges,
            ):
                start, end, count = expected

                self.assertEqual(
                    int(package["source_record_start"]),
                    start,
                )
                self.assertEqual(
                    int(package["source_record_end"]),
                    end,
                )
                self.assertEqual(
                    int(package["record_count"]),
                    count,
                )

                child_path = (
                    staging / package["normalized_filename"]
                )
                self.assertTrue(child_path.is_file())

                with child_path.open(
                    newline="",
                    encoding="utf-8-sig",
                ) as handle:
                    rows = list(csv.DictReader(handle))

                self.assertEqual(len(rows), count)

                if profile == "salesforce":
                    self.assertEqual(
                        rows[0]["INSYT_SF_Object_Type"],
                        "Contact",
                    )
                    self.assertTrue(
                        rows[0]["INSYT_SF_Record_ID"].startswith(
                            "003"
                        )
                    )
                    self.assertIn(
                        "SF__name",
                        rows[0],
                    )

            self.assertEqual(
                hashlib.sha256(
                    source.read_bytes()
                ).hexdigest(),
                original_hash,
            )

            preserved = (
                root
                / "structured_intake"
                / "source"
                / source.name
            )
            self.assertTrue(preserved.is_file())
            self.assertEqual(
                preserved.read_bytes(),
                original_bytes,
            )

            self.assertEqual(
                unrelated.read_bytes(),
                unrelated_bytes,
            )

            db = LedgerDB(str(root / "apc.sqlite"))

            try:
                db.init_schema()

                settings = Settings()
                matter_id = "JSON-OFFLINE-TEST"
                client_id = "SYNTHETIC"

                job_id = create_job(
                    db,
                    matter_id=matter_id,
                    client_id=client_id,
                )

                run_inventory(
                    db,
                    settings,
                    job_id,
                    matter_id,
                    input_dir=str(staging),
                )

                provenance = apply_structured_json_provenance(
                    db=db,
                    job_id=job_id,
                    staging_dir=staging,
                    manifest_path=manifest_path,
                )

                self.assertEqual(
                    provenance["missing_count"],
                    0,
                )
                self.assertEqual(
                    provenance["updated_count"],
                    3,
                )

                family = link_plain_json_families(
                    db=db,
                    job_id=job_id,
                    staging_dir=staging,
                    manifest_path=manifest_path,
                )

                self.assertEqual(
                    family,
                    {"parents": 1, "children": 3},
                )

                inventory = db.query(
                    """
                    SELECT *
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job_id,),
                )

                self.assertEqual(len(inventory), 5)

                parents = [
                    row for row in inventory
                    if row["extension"] == "json"
                ]
                self.assertEqual(len(parents), 1)

                parent = parents[0]
                parent_id = parent["file_id"]
                self.assertEqual(parent["is_container"], 1)

                children = [
                    row for row in inventory
                    if row["parent_file_id"] == parent_id
                ]
                self.assertEqual(len(children), 3)

                for row in children:
                    metadata = json.loads(
                        row["stage_status_json"] or "{}"
                    )
                    self.assertIn(
                        "structured_source",
                        metadata,
                    )
                    self.assertIn(
                        "structured_json_child",
                        metadata,
                    )

                # All normalized CSV children must follow
                # the same core route as an ordinary CSV.
                routing_result = route_train_station_files(
                    db=db,
                    job_id=job_id,
                )

                self.assertEqual(
                    routing_result["continue_count"],
                    4,
                )
                self.assertEqual(
                    routing_result["container_support_count"],
                    1,
                )
                self.assertEqual(
                    routing_result["train_station_count"],
                    0,
                )

                routed_rows = db.query(
                    """
                    SELECT
                        file_id,
                        extension,
                        is_container,
                        parent_file_id,
                        stage_status_json
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job_id,),
                )

                csv_rows = [
                    row for row in routed_rows
                    if row["extension"] == "csv"
                ]

                self.assertEqual(len(csv_rows), 4)

                for row in csv_rows:
                    metadata = json.loads(
                        row["stage_status_json"] or "{}"
                    )

                    route = metadata["file_routing"]

                    self.assertEqual(
                        route["status"],
                        "continue",
                    )
                    self.assertEqual(
                        route["route"],
                        "core",
                    )
                    self.assertEqual(
                        route["extension"],
                        ".csv",
                    )

                json_parent_rows = [
                    row for row in routed_rows
                    if row["extension"] == "json"
                ]

                self.assertEqual(len(json_parent_rows), 1)
                self.assertEqual(
                    json_parent_rows[0]["is_container"],
                    1,
                )

                processing_sets = build_processing_sets(
                    db=db,
                    job_id=job_id,
                    matter_id=matter_id,
                    set_size=500,
                )

                self.assertIsNotNone(processing_sets)

                memberships = db.query(
                    """
                    SELECT
                        psf.file_id,
                        psf.membership_role,
                        psf.counts_toward_set_size
                    FROM processing_set_file psf
                    WHERE psf.job_id=?
                    """,
                    (job_id,),
                )

                self.assertEqual(len(memberships), 5)

                primary = [
                    row for row in memberships
                    if row["membership_role"] == "primary"
                ]
                self.assertEqual(len(primary), 4)

                self.assertEqual(
                    sum(
                        int(row["counts_toward_set_size"])
                        for row in memberships
                    ),
                    4,
                )

                parent_membership = [
                    row for row in memberships
                    if row["file_id"] == parent_id
                ]
                self.assertEqual(len(parent_membership), 1)
                self.assertEqual(
                    parent_membership[0][
                        "counts_toward_set_size"
                    ],
                    0,
                )

                routing = AzureRoutingConfig.from_args(
                    workspace="capture",
                    client=client_id,
                    project=matter_id,
                    azure_write=False,
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
                        db,
                        settings,
                        job_id,
                        matter_id,
                        routing=routing,
                    )

                reserve.assert_called_once()
                self.assertEqual(
                    reserve.call_args.kwargs["count"],
                    2,
                )

                final_rows = db.query(
                    """
                    SELECT *
                    FROM file_processing_metrics
                    WHERE job_id=?
                    """,
                    (job_id,),
                )

                self.assertEqual(len(final_rows), 5)

                # Exercise the hardened Excel/CSV path using
                # the real JSON parent and child SQLite rows.
                common_csv_plan = build_xl_files_staging_plan(
                    db,
                    job_id,
                    routing,
                )

                self.assertEqual(len(common_csv_plan), 4)

                common_parents = [
                    item for item in common_csv_plan
                    if item["is_structured_parent"]
                ]
                common_children = [
                    item for item in common_csv_plan
                    if item["is_csv_child"]
                ]

                self.assertEqual(len(common_parents), 1)
                self.assertEqual(len(common_children), 3)

                self.assertEqual(
                    common_parents[0]["file_id"],
                    parent_id,
                )
                self.assertEqual(
                    common_parents[0]["extension"],
                    "json",
                )
                self.assertEqual(
                    common_parents[0]["text_staged_blob_path"],
                    "",
                )
                self.assertEqual(
                    Path(
                        common_parents[0]["original_path"]
                    ).read_bytes(),
                    original_bytes,
                )

                for item in common_children:
                    self.assertEqual(item["extension"], "csv")
                    self.assertEqual(
                        item["parent_file_id"],
                        parent_id,
                    )
                    self.assertTrue(
                        item["text_staged_blob_path"]
                    )

                # Use the existing uploader with its real
                # ledger-derived plan; mock Azure only.
                from apc.azure_blob_adapter import (
                    azure_upload_xl_files_outputs,
                )

                mocked_adapter = MagicMock()
                mocked_adapter._content_settings_cls.side_effect = (
                    lambda **kwargs: MagicMock(**kwargs)
                )

                with patch(
                    "apc.azure_blob_adapter.DualStorageBlobAdapter",
                    return_value=mocked_adapter,
                ):
                    common_upload = azure_upload_xl_files_outputs(
                        db=db,
                        routing=routing,
                        job_id=job_id,
                        azure_write=True,
                        overwrite=True,
                    )

                self.assertEqual(
                    common_upload["uploaded_count"],
                    4,
                )
                self.assertEqual(
                    common_upload["failed_count"],
                    0,
                )

                uploaded_by_id = {
                    item["file_id"]: item
                    for item in common_upload["uploaded"]
                }

                self.assertFalse(
                    uploaded_by_id[parent_id]["detection_ready"]
                )

                for child_item in common_children:
                    self.assertTrue(
                        uploaded_by_id[
                            child_item["file_id"]
                        ]["detection_ready"]
                    )

                blob_calls = (
                    mocked_adapter.review_container
                    .get_blob_client.call_args_list
                )

                blob_paths = [
                    call.args[0]
                    for call in blob_calls
                ]

                # One retained native + three child CSVs
                # + three child text artifacts.
                self.assertEqual(len(blob_paths), 7)
                self.assertEqual(
                    len(set(blob_paths)),
                    7,
                )

                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    original_hash,
                )

                # Reuse the verified common CSV family.
                # Native remains retained only; children
                # remain the processing documents.
                parent_item = common_parents[0]
                child_items = common_children

                self.assertEqual(
                    sorted(item["doc_id"] for item in child_items),
                    [
                        f"{parent_item['doc_id']}.1",
                        f"{parent_item['doc_id']}.2",
                        f"{parent_item['doc_id']}.3",
                    ],
                )

                self.assertEqual(
                    len({
                        item["file_id"]
                        for item in common_csv_plan
                    }),
                    4,
                )

                for item in child_items:
                    self.assertEqual(
                        item["parent_file_id"],
                        parent_id,
                    )
                    self.assertTrue(
                        Path(item["original_path"]).is_file()
                    )
                    self.assertTrue(
                        item["native_staged_blob_path"].endswith(
                            f"/{item['doc_id']}.csv"
                        )
                    )
                    self.assertTrue(
                        item["text_staged_blob_path"].endswith(
                            f"/{item['doc_id']}.txt"
                        )
                    )

                # Verify REAL SQLite staging through the
                # ONE hardened CSV uploader.
                # Azure Blob I/O alone is mocked.
                from apc.azure_blob_adapter import (
                    azure_upload_xl_files_outputs,
                )

                uploaded_blobs = {}

                def make_blob(blob_path):
                    blob = MagicMock()

                    def capture(data, **kwargs):
                        payload = (
                            data.read()
                            if hasattr(data, "read")
                            else bytes(data)
                        )
                        uploaded_blobs[blob_path] = {
                            "bytes": payload,
                            "content_type": (
                                kwargs[
                                    "content_settings"
                                ].content_type
                            ),
                        }

                    blob.upload_blob.side_effect = capture
                    return blob

                adapter = MagicMock()
                adapter.review_container.get_blob_client.side_effect = (
                    make_blob
                )
                adapter._content_settings_cls.side_effect = (
                    lambda content_type: MagicMock(
                        content_type=content_type
                    )
                )

                with patch(
                    "apc.azure_blob_adapter.DualStorageBlobAdapter",
                    return_value=adapter,
                ):
                    uploaded = azure_upload_xl_files_outputs(
                        db=db,
                        routing=routing,
                        job_id=job_id,
                        azure_write=True,
                    )

                self.assertEqual(uploaded["planned_count"], 4)
                self.assertEqual(uploaded["uploaded_count"], 4)
                self.assertEqual(uploaded["failed_count"], 0)
                self.assertEqual(len(uploaded_blobs), 7)

                for item in common_csv_plan:
                    native_path = item["native_staged_blob_path"]
                    self.assertIn(native_path, uploaded_blobs)
                    self.assertEqual(
                        uploaded_blobs[native_path]["bytes"],
                        Path(item["original_path"]).read_bytes(),
                    )
                    self.assertEqual(
                        uploaded_blobs[native_path]["content_type"],
                        "application/octet-stream",
                    )

                    text_path = item["text_staged_blob_path"]
                    if item["is_structured_parent"]:
                        self.assertEqual(text_path, "")
                    else:
                        self.assertIn(text_path, uploaded_blobs)
                        self.assertEqual(
                            uploaded_blobs[text_path]["content_type"],
                            "text/plain; charset=utf-8",
                        )

                self.assertEqual(
                    sum(
                        bool(item["detection_ready"])
                        for item in uploaded["uploaded"]
                    ),
                    3,
                )
                self.assertEqual(
                    sum(
                        bool(item["is_structured_parent"])
                        for item in uploaded["uploaded"]
                    ),
                    1,
                )

                # Verify lifecycle output from the real ledger
                # and the confirmed mocked Azure upload results.
                # No PostgreSQL connection is used.
                from app.services.document_lifecycle_writer import (
                    build_document_lifecycle_rows,
                )

                lifecycle_rows = build_document_lifecycle_rows(
                    ledger_db=db,
                    workspace=routing.workspace,
                    client=routing.client,
                    project=routing.project,
                    source_job_id=job_id,
                    staging_payloads=[uploaded],
                )

                self.assertEqual(len(lifecycle_rows), 4)

                lifecycle_by_doc = {
                    row["doc_id"]: row
                    for row in lifecycle_rows
                }

                self.assertEqual(
                    len(lifecycle_by_doc),
                    4,
                )

                self.assertNotIn(
                    parent_item["doc_id"],
                    lifecycle_by_doc,
                )

                for item in child_items:
                    lifecycle = lifecycle_by_doc[item["doc_id"]]

                    self.assertEqual(
                        lifecycle["file_id"],
                        item["file_id"],
                    )
                    self.assertEqual(
                        lifecycle["parent_file_id"],
                        parent_id,
                    )
                    self.assertEqual(
                        lifecycle["source_job_id"],
                        job_id,
                    )
                    self.assertEqual(
                        lifecycle["detection_status"],
                        "READY",
                    )
                    self.assertEqual(
                        lifecycle["ingestion_status"],
                        "COMPLETE",
                    )

                other_lifecycle = [
                    row for row in lifecycle_rows
                    if row["parent_file_id"] is None
                ]

                self.assertEqual(
                    len(other_lifecycle),
                    1,
                )
                self.assertEqual(
                    other_lifecycle[0]["extension"],
                    "csv",
                )
                self.assertEqual(
                    other_lifecycle[0]["detection_status"],
                    "PENDING",
                )

                by_id = {
                    row["file_id"]: row
                    for row in final_rows
                }

                final_parent = by_id[parent_id]
                parent_doc_id = final_parent["doc_id"]

                self.assertRegex(
                    parent_doc_id,
                    r"^INSYT\d{9}$",
                )

                final_children = [
                    row for row in final_rows
                    if row["parent_file_id"] == parent_id
                ]

                child_doc_ids = sorted(
                    row["doc_id"]
                    for row in final_children
                )

                self.assertEqual(
                    child_doc_ids,
                    [
                        f"{parent_doc_id}.1",
                        f"{parent_doc_id}.2",
                        f"{parent_doc_id}.3",
                    ],
                )

                for row in final_children:
                    child_path = Path(
                        row["original_path"]
                    )
                    self.assertTrue(child_path.is_file())
                    self.assertEqual(
                        child_path.name,
                        f"{row['doc_id']}.csv",
                    )

                    metadata = json.loads(
                        row["stage_status_json"] or "{}"
                    )

                    child = metadata[
                        "structured_json_child"
                    ]

                    self.assertEqual(
                        child["parent_file_id"],
                        parent_id,
                    )
                    self.assertEqual(
                        child["parent_doc_id"],
                        parent_doc_id,
                    )
                    self.assertEqual(
                        Path(
                            child["derived_csv_path"]
                        ),
                        child_path,
                    )

                ordinary = [
                    row for row in final_rows
                    if row["extension"] == "csv"
                    and row["parent_file_id"] is None
                ]

                self.assertEqual(len(ordinary), 1)

                self.assertRegex(
                    ordinary[0]["doc_id"],
                    r"^INSYT\d{9}$",
                )
                self.assertNotEqual(
                    ordinary[0]["doc_id"],
                    parent_doc_id,
                )

                self.assertEqual(
                    unrelated.read_bytes(),
                    unrelated_bytes,
                )

                self.assertEqual(
                    source.read_bytes(),
                    original_bytes,
                )
                self.assertEqual(
                    preserved.read_bytes(),
                    original_bytes,
                )

                self.assertEqual(
                    db.query(
                        "PRAGMA foreign_key_check"
                    ),
                    [],
                )

            finally:
                db.close()




if __name__ == "__main__":
    unittest.main()