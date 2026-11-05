"""Tests for scoped Cyber2 Completed Merge Sets retrieval."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_cyber2_membership_api import harness
from test_cyber2_merge_set_store import setup, save


def listing_setup(monkeypatch, api):
    container, store, _, derived = setup()

    def list_blobs(*, name_starts_with):
        return [
            SimpleNamespace(name=path)
            for path in container.storage
            if path.startswith(name_starts_with)
        ]

    container.list_blobs = list_blobs

    monkeypatch.setattr(
        api,
        "_cyber2_merge_store_for",
        lambda workspace, client, project: store,
    )

    return container, store, derived


def listing(api, user):
    response = api.list_cyber2_completed_merge_sets(
        workspace="capture",
        client="ACME",
        project="CaseA",
        current_user=user,
    )
    return response, json.loads(response.body)


def test_completed_listing_empty(harness, monkeypatch):
    api, user, registry = harness
    listing_setup(monkeypatch, api)

    response, result = listing(api, user)

    assert response.status_code == 200
    assert result["count"] == 0
    assert result["merge_sets"] == []
    assert registry["writes"] == 0


def test_completed_listing_returns_saved_set_metadata(
    harness, monkeypatch
):
    api, user, registry = harness
    container, store, derived = listing_setup(monkeypatch, api)

    saved = save(store, derived)

    response, result = listing(api, user)

    assert result["count"] == 1
    row = result["merge_sets"][0]
    assert row["merge_set_id"] == saved["merge_set_id"]
    assert row["raw_record_count"] == 4
    assert row["working_record_count"] == 3
    assert row["merged_group_count"] == 1
    assert response.headers["cache-control"] == "no-store, private"
    assert "900-12-0001" not in str(result)
    assert len(container.storage) == 1
    assert registry["writes"] == 0


def test_listing_rejects_corrupted_saved_set(
    harness, monkeypatch
):
    api, user, registry = harness
    container, store, derived = listing_setup(monkeypatch, api)

    save(store, derived)
    path = next(iter(container.storage))
    document = json.loads(container.storage[path])
    document["working_record_count"] = 999
    container.storage[path] = json.dumps(document).encode()

    with pytest.raises(HTTPException) as exc:
        listing(api, user)

    # Integrity failures must not be silently treated as empty sets.
    assert exc.value.status_code >= 400
    assert registry["writes"] == 0


def test_admin_denial_prevents_storage_read(
    harness, monkeypatch
):
    api, user, registry = harness
    listing_setup(monkeypatch, api)

    touched = []

    def forbidden(_user):
        raise HTTPException(status_code=403, detail="Forbidden")

    def prohibited(*args):
        touched.append(True)
        raise AssertionError("Storage was accessed")

    monkeypatch.setattr(api, "require_admin", forbidden)
    monkeypatch.setattr(
        api, "_cyber2_merge_store_for", prohibited
    )

    with pytest.raises(HTTPException) as exc:
        listing(api, user)

    assert exc.value.status_code == 403
    assert not touched
    assert registry["writes"] == 0


def test_listing_rejects_over_limit(harness, monkeypatch):
    api, user, registry = harness
    _, store, derived = listing_setup(monkeypatch, api)

    save(store, derived)
    save(store, derived)

    with pytest.raises(ValueError):
        store.list_completed(max_sets=1)

    assert registry["writes"] == 0
