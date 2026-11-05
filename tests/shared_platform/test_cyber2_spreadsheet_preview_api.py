"""Regression tests for authorized Cyber2 full-value spreadsheet previews."""

import json

import pytest
from fastapi import HTTPException

from test_cyber2_exact_preview_api import (
    configure,
    harness,
    mapping,
    raw,
)


def spreadsheet(api, user, fields=None):
    body = api.ExactDedupePreviewBody(
        client="ACME",
        project="CaseA",
        header_set_id="HDR-1",
        merge_index=fields or [
            "First Name",
            "Last Name",
            "SSN",
        ],
    )
    response = api.preview_cyber2_spreadsheet(
        "capture",
        body,
        user,
    )
    return response, json.loads(response.body)


def test_spreadsheet_shows_actual_values_and_lineage(
    harness, monkeypatch
):
    api, user, store = harness
    configure(monkeypatch, api)

    response, result = spreadsheet(api, user)

    assert response.status_code == 200
    assert result["status"] == "spreadsheet_preview"
    assert len(result["snapshot_fingerprint"]) == 64
    assert result["preview_rows_complete"] is True
    assert result["execution_enabled"] is False
    assert result["preview_row_count"] == 2
    assert len(result["preview_rows"]) == 2
    assert result["preview_columns"] == mapping()[
        "canonical_column_order"
    ]

    assert {
        row["ucid"] for row in result["preview_rows"]
    } == {"R1", "R2"}

    assert {
        row["doc_id"] for row in result["preview_rows"]
    } == {"D1", "D2"}

    for row in result["preview_rows"]:
        assert row["classification"] == "exact_duplicate"
        assert row["group_number"] == 1
        assert row["cells"]["SSN"] == "900-12-0001"
        assert row["cells"]["DOB"] == "1985-04-12"
        assert row["cells"]["Street 1"] == "100 Main Street"
        assert row["source"]["header_set_id"] == "HDR-1"
        assert row["source"]["source_row_number"] == 2

    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert store["writes"] == 0


def test_summary_still_excludes_actual_ssn(
    harness, monkeypatch
):
    api, user, store = harness
    configure(monkeypatch, api)

    body = api.ExactDedupePreviewBody(
        client="ACME",
        project="CaseA",
        header_set_id="HDR-1",
        merge_index=["First Name", "Last Name", "SSN"],
    )
    summary = api.preview_cyber2_exact_dedupe(
        "capture",
        body,
        user,
    )

    assert "900-12-0001" not in str(summary)
    assert store["writes"] == 0


def test_spreadsheet_rejects_cross_project_mapping(
    harness, monkeypatch
):
    api, user, store = harness
    approved = mapping()
    approved["project"] = "OtherProject"

    configure(monkeypatch, api, approved=approved)

    with pytest.raises(HTTPException) as exc:
        spreadsheet(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_spreadsheet_rejects_unapproved_mapping(
    harness, monkeypatch
):
    api, user, store = harness
    approved = mapping()
    approved["status"] = "pending"

    configure(monkeypatch, api, approved=approved)

    with pytest.raises(HTTPException) as exc:
        spreadsheet(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_spreadsheet_rejects_wrong_provenance(
    harness, monkeypatch
):
    api, user, store = harness

    records = [
        raw("R1", "D1"),
        raw("R2", "D2"),
    ]

    records[1]["provenance"]["header_set_id"] = "OTHER-SET"

    configure(monkeypatch, api, records=records)

    with pytest.raises(HTTPException) as exc:
        spreadsheet(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_spreadsheet_denies_admin_access(
    harness, monkeypatch
):
    api, user, store = harness
    configure(monkeypatch, api)

    def deny_admin(_user):
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    monkeypatch.setattr(api, "require_admin", deny_admin)

    with pytest.raises(HTTPException) as exc:
        spreadsheet(api, user)

    assert exc.value.status_code == 403
    assert store["writes"] == 0


def test_spreadsheet_rejects_incomplete_population(
    harness, monkeypatch
):
    api, user, store = harness

    configure(
        monkeypatch,
        api,
        records=[raw("R1", "D1")],
    )

    with pytest.raises(HTTPException) as exc:
        spreadsheet(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_spreadsheet_preserves_conflict_values(
    harness, monkeypatch
):
    api, user, store = harness

    configure(
        monkeypatch,
        api,
        records=[
            raw("R1", "D1", "900-12-0001"),
            raw("R2", "D2", "900-12-0002"),
        ],
    )

    _, result = spreadsheet(
        api,
        user,
        ["First Name", "Last Name", "DOB", "Street 1"],
    )

    assert result["preview_row_count"] == 2
    assert all(
        row["classification"] == "qc_conflict"
        for row in result["preview_rows"]
    )
    assert {
        row["cells"]["SSN"]
        for row in result["preview_rows"]
    } == {"900-12-0001", "900-12-0002"}

    assert store["writes"] == 0
