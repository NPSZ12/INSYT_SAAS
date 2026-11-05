"""Offline tests for authenticated Cyber2 merge execution."""

import copy
import pytest
from fastapi import HTTPException

from test_cyber2_exact_preview_api import (
    configure,
    harness,
    mapping,
    raw,
)
from test_cyber2_merge_set_store import (
    Cyber2MergeSetStore,
    FakeContainer,
)


def execute(
    api,
    user,
    *,
    fingerprint=None,
    request_id="fda03b5b-0a09-4539-a4f0-74ceaa3878c1",
):
    from app.services.cyber2.merge_snapshot import (
        merge_snapshot_fingerprint,
    )

    index = ["First Name", "Last Name", "SSN"]

    if fingerprint is None:
        fingerprint = merge_snapshot_fingerprint(
            approved_mapping=mapping(),
            merge_index=index,
            raw_records=api.load_cyber2_raw_capture_records(
                "capture", "ACME", "CaseA"
            ),
        )

    body = api.MergeExecuteBody(
        client="ACME",
        project="CaseA",
        header_set_id="HDR-1",
        merge_index=["First Name", "Last Name", "SSN"],
        snapshot_fingerprint=fingerprint,
        request_id=request_id,
    )
    return api.execute_cyber2_exact_merge(
        "capture", body, user
    )


def setup_execution(monkeypatch, api, *, approved=None, records=None):
    container = FakeContainer()

    if records is None:
        records = [
            raw("R1", "D1"),
            raw("R2", "D2"),
        ]

    configure(
        monkeypatch,
        api,
        approved=approved,
        records=records,
    )

    store = Cyber2MergeSetStore(
        container,
        "ACME/capture/CaseA",
        content_settings_factory=lambda: {
            "content_type": "application/json"
        },
    )

    monkeypatch.setattr(
        api, "_cyber2_merge_store_for",
        lambda workspace, client, project: store,
    )
    monkeypatch.setattr(
        api, "_cyber2_execution_actor",
        lambda user: "TEST-ADMIN",
    )

    return container, store, records


def test_execution_saves_derived_set_without_raw_changes(
    harness, monkeypatch
):
    api, user, registry = harness

    container, store, records = setup_execution(
        monkeypatch, api
    )
    original = copy.deepcopy(records)

    receipt = execute(api, user)

    assert receipt["status"] == "completed"
    assert receipt["working_record_count"] == 1
    assert receipt["raw_record_count"] == 2
    assert receipt["merged_group_count"] == 1

    document = store.load(receipt["merge_set_id"])

    assert document["executed_by"] == "TEST-ADMIN"
    assert document["working_records"][0]["source_ucids"] == [
        "R1", "R2"
    ]
    assert document["working_records"][0]["cells"]["SSN"] == (
        "900-12-0001"
    )
    assert records == original
    assert registry["writes"] == 0
    assert len(container.storage) == 1


def test_execution_recalculates_conflicting_identifiers(
    harness, monkeypatch
):
    api, user, registry = harness

    records = [
        raw("R1", "D1", "900-12-0001"),
        raw("R2", "D2", "900-12-0002"),
    ]

    container, store, _ = setup_execution(
        monkeypatch, api, records=records
    )

    # Name and DOB match, but the selected index contains SSN.
    # The two different identities must remain separate.
    receipt = execute(api, user)

    assert receipt["merged_group_count"] == 0
    assert receipt["working_record_count"] == 2

    document = store.load(receipt["merge_set_id"])

    assert all(
        len(row["source_ucids"]) == 1
        for row in document["working_records"]
    )
    assert registry["writes"] == 0
    assert len(container.storage) == 1


def test_cross_project_mapping_never_saves(
    harness, monkeypatch
):
    api, user, registry = harness
    approved = mapping()
    approved["project"] = "OtherCase"

    container, _, _ = setup_execution(
        monkeypatch, api, approved=approved
    )

    with pytest.raises(HTTPException) as exc:
        execute(api, user)

    assert exc.value.status_code == 409
    assert not container.storage
    assert registry["writes"] == 0


def test_denied_admin_never_saves(
    harness, monkeypatch
):
    api, user, registry = harness

    container, _, _ = setup_execution(monkeypatch, api)

    monkeypatch.setattr(
        api,
        "require_admin",
        lambda user: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="Forbidden")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        execute(api, user)

    assert exc.value.status_code == 403
    assert not container.storage
    assert registry["writes"] == 0


def test_changed_raw_value_rejects_stale_execution(
    harness, monkeypatch
):
    from app.services.cyber2.merge_snapshot import (
        merge_snapshot_fingerprint,
    )

    api, user, registry = harness
    container, _, records = setup_execution(monkeypatch, api)

    old_fingerprint = merge_snapshot_fingerprint(
        approved_mapping=mapping(),
        merge_index=["First Name", "Last Name", "SSN"],
        raw_records=records,
    )

    records[1]["metadata"]["Street 1"] = "Updated address"

    with pytest.raises(HTTPException) as exc:
        execute(api, user, fingerprint=old_fingerprint)

    assert exc.value.status_code == 409
    assert not container.storage
    assert registry["writes"] == 0


def test_invalid_fingerprint_rejects_execution(
    harness, monkeypatch
):
    api, user, registry = harness
    container, _, _ = setup_execution(monkeypatch, api)

    with pytest.raises(HTTPException) as exc:
        execute(api, user, fingerprint="invalid")

    assert exc.value.status_code == 409
    assert not container.storage
    assert registry["writes"] == 0



def test_execution_retry_is_idempotent(
    harness, monkeypatch
):
    api, user, registry = harness

    container, store, records = setup_execution(
        monkeypatch, api
    )
    original = copy.deepcopy(records)

    first = execute(api, user)
    retry = execute(api, user)

    assert first["status"] == "completed"
    assert retry["status"] == "completed"
    assert first["merge_set_id"] == retry["merge_set_id"]
    assert first["idempotent_replay"] is False
    assert retry["idempotent_replay"] is True
    assert len(container.storage) == 1
    assert store.load(first["merge_set_id"])[
        "working_record_count"
    ] == 1
    assert records == original
    assert registry["writes"] == 0


def test_distinct_execution_requests_get_distinct_sets(
    harness, monkeypatch
):
    api, user, registry = harness

    container, store, records = setup_execution(
        monkeypatch, api
    )

    first = execute(
        api,
        user,
        request_id="45e1d98d-7681-4da4-8d9a-c9cb411ac012",
    )
    second = execute(
        api,
        user,
        request_id="5728050f-635f-4fca-a4f2-f76b294337f5",
    )

    assert first["merge_set_id"] != second["merge_set_id"]
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is False
    assert len(container.storage) == 2
    assert registry["writes"] == 0
