"""Integrated Cyber2 preview, execution, storage, and listing regression."""

import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_cyber2_exact_preview_api import harness
from test_cyber2_execute_api import setup_execution
from test_cyber2_spreadsheet_preview_api import spreadsheet


def test_full_merge_workflow_with_retry_and_stale_protection(
    harness, monkeypatch
):
    api, user, registry = harness

    # Reuse the existing approved mapping and synthetic RAW records.
    container, store, records = setup_execution(
        monkeypatch, api
    )

    original_raw = copy.deepcopy(records)

    # The production store supports Azure Blob prefix enumeration.
    # Add equivalent behavior to the existing offline fake.
    container.list_blobs = lambda *, name_starts_with: [
        SimpleNamespace(name=path)
        for path in container.storage
        if path.startswith(name_starts_with)
    ]

    # 1. Obtain an authorized spreadsheet preview.
    preview_response, preview = spreadsheet(api, user)

    assert preview_response.status_code == 200
    assert preview["status"] == "spreadsheet_preview"
    assert preview["header_set_id"] == "HDR-1"
    assert preview["preview_row_count"] == 2
    assert len(preview["preview_rows"]) == 2
    assert len(preview["snapshot_fingerprint"]) == 64

    fingerprint = preview["snapshot_fingerprint"]

    request_id = "a3c75694-79a1-4181-819e-f76e77424e89"

    def execute(snapshot):
        body = api.MergeExecuteBody(
            client="ACME",
            project="CaseA",
            header_set_id=preview["header_set_id"],
            merge_index=preview["merge_index"],
            snapshot_fingerprint=snapshot,
            request_id=request_id,
        )

        return api.execute_cyber2_exact_merge(
            "capture", body, user
        )

    # 2. Reject an invalid/stale fingerprint before saving.
    with pytest.raises(HTTPException) as stale:
        execute("0" * 64)

    assert stale.value.status_code == 409
    assert len(container.storage) == 0
    assert records == original_raw

    # 3. Execute using the actual preview fingerprint.
    receipt = execute(fingerprint)

    assert receipt["status"] == "completed"
    assert receipt["idempotent_replay"] is False
    assert receipt["raw_record_count"] == 2
    assert receipt["working_record_count"] == 1
    assert receipt["merged_group_count"] == 1
    assert receipt["merge_set_id"].startswith("MSET-")
    assert len(container.storage) == 1

    # 4. Confirm consolidated values and source lineage.
    saved = store.load(receipt["merge_set_id"])

    assert saved["working_record_count"] == 1
    assert saved["working_records"][0]["source_ucids"] == [
        "R1", "R2"
    ]
    assert len(saved["working_records"]) == 1
    assert saved["created_at"] == receipt["created_at"]

    # 5. Retry the same request. No second blob is created.
    retry = execute(fingerprint)

    assert retry["status"] == "completed"
    assert retry["idempotent_replay"] is True
    assert retry["merge_set_id"] == receipt["merge_set_id"]
    assert retry["created_at"] == receipt["created_at"]
    assert len(container.storage) == 1

    # 6. Retrieve the completed set through the authenticated API.
    listing_response = api.list_cyber2_completed_merge_sets(
        workspace="capture",
        client="ACME",
        project="CaseA",
        current_user=user,
    )

    listing = json.loads(listing_response.body)

    assert listing_response.status_code == 200
    assert listing_response.headers["cache-control"] == (
        "no-store, private"
    )
    assert listing["status"] == "ok"
    assert listing["count"] == 1

    completed = listing["merge_sets"][0]

    assert completed["merge_set_id"] == receipt["merge_set_id"]
    assert completed["created_at"] == receipt["created_at"]
    assert completed["raw_record_count"] == 2
    assert completed["working_record_count"] == 1
    assert completed["merged_group_count"] == 1

    # Listing must never expose sensitive captured cell values.
    assert "900-12-0001" not in str(listing)

    # 7. Confirm that RAW and the membership registry are unchanged.
    assert records == original_raw
    assert registry["writes"] == 0
    assert len(container.storage) == 1
