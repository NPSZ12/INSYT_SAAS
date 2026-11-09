"""Offline tests for authenticated Cyber2 exact-dedupe preview API."""

import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from test_cyber2_membership_api import harness


def mapping():
    return {
        "schema_version": 1,
        "status": "approved",
        "workspace": "capture",
        "client": "ACME",
        "project": "CaseA",
        "header_set_id": "HDR-1",
        "canonical_column_order": [
            "First Name", "Last Name", "SSN", "DOB", "Street 1"
        ],
        "documents": [
            {"doc_id": "D1"},
            {"doc_id": "D2"},
        ],
    }


def raw(ucid, doc, ssn="900-12-0001"):
    return {
        "ucid": ucid,
        "doc_id": doc,
        "metadata": {
            "First Name": "Jordan",
            "Last Name": "Sample",
            "SSN": ssn,
            "DOB": "1985-04-12",
            "Street 1": "100 Main Street",
        },
        "provenance": {
            "header_set_id": "HDR-1",
            "source_row_number": 2,
        },
    }


def configure(monkeypatch, api, *, approved=None, records=None):
    schema = types.ModuleType("app.api.cyber2.schema_mapping")

    schema._approved_mapping_path = (
        lambda **kwargs:
        f"{kwargs['client']}/{kwargs['workspace']}/"
        f"{kwargs['project']}/{kwargs['header_set_id']}"
    )

    supplied = approved if approved is not None else mapping()

    schema._load_required_json = (
        lambda path, *, description: supplied
    )

    monkeypatch.setitem(
        sys.modules,
        "app.api.cyber2.schema_mapping",
        schema,
    )

    api.load_cyber2_raw_capture_records = (
        lambda *args: records if records is not None else [
            raw("R1", "D1"),
            raw("R2", "D2"),
        ]
    )

    # API unit tests supply synthetic mapped records through the
    # current processing-set contract. Dedicated loader tests verify
    # persisted Mapped CSV manifests, paths, and column lineage.
    monkeypatch.setattr(
        api,
        "_load_cyber2_merge_processing_set",
        lambda **kwargs: {
            "records": api.load_cyber2_raw_capture_records(
                kwargs["workspace"],
                kwargs["client"],
                kwargs["project"],
            ),
            "output_headers": list(
                supplied["canonical_column_order"]
            ),
        },
    )


def preview(api, user, fields=None):
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

    return api.preview_cyber2_exact_dedupe(
        "capture", body, user
    )


def test_exact_preview_no_registry_write(harness, monkeypatch):
    api, user, store = harness
    configure(monkeypatch, api)

    result = preview(api, user)

    assert result["status"] == "preview"
    assert result["execution_enabled"] is False
    assert result["duplicate_group_count"] == 1
    assert result["working_record_count"] == 1
    assert result["header_set_id"] == "HDR-1"
    assert store["writes"] == 0
    assert "900-12-0001" not in str(result)


def test_conflicting_ssn_excluded_from_auto_merge(harness, monkeypatch):
    api, user, store = harness

    configure(
        monkeypatch,
        api,
        records=[
            raw("R1", "D1", "900-12-0001"),
            raw("R2", "D2", "900-12-0002"),
        ],
    )

    result = preview(
        api,
        user,
        ["First Name", "Last Name", "DOB", "Street 1"],
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert "SSN" in result["conflicts"][0]["conflict_fields"]
    assert store["writes"] == 0


def test_unapproved_mapping_rejected(harness, monkeypatch):
    api, user, store = harness

    approved = mapping()
    approved["status"] = "pending"
    configure(monkeypatch, api, approved=approved)

    with pytest.raises(HTTPException) as exc:
        preview(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_cross_project_mapping_rejected(harness, monkeypatch):
    api, user, store = harness

    approved = mapping()
    approved["project"] = "DifferentCase"
    configure(monkeypatch, api, approved=approved)

    with pytest.raises(HTTPException) as exc:
        preview(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_unapproved_merge_index_rejected(harness, monkeypatch):
    api, user, store = harness
    configure(monkeypatch, api)

    with pytest.raises(HTTPException) as exc:
        preview(api, user, ["Unapproved Field"])

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_missing_raw_document_rejected(harness, monkeypatch):
    api, user, store = harness

    configure(
        monkeypatch,
        api,
        records=[raw("R1", "D1")],
    )

    with pytest.raises(HTTPException) as exc:
        preview(api, user)

    assert exc.value.status_code == 409
    assert store["writes"] == 0


def test_project_access_denial_before_data_read(harness, monkeypatch):
    api, user, store = harness
    touched = []

    configure(monkeypatch, api)

    def deny(*args):
        raise HTTPException(status_code=403)

    api.require_scoped_project_access = deny
    api.load_cyber2_raw_capture_records = (
        lambda *args: touched.append(True)
    )

    with pytest.raises(HTTPException) as exc:
        preview(api, user)

    assert exc.value.status_code == 403
    assert not touched
    assert store["writes"] == 0


def test_admin_denial_before_data_read(harness, monkeypatch):
    api, user, store = harness
    touched = []

    configure(monkeypatch, api)

    def deny(*args):
        raise HTTPException(status_code=403)

    api.require_admin = deny
    api.load_cyber2_raw_capture_records = (
        lambda *args: touched.append(True)
    )

    with pytest.raises(HTTPException) as exc:
        preview(api, user)

    assert exc.value.status_code == 403
    assert not touched
    assert store["writes"] == 0

def test_actual_insyt_protocol_identifier_labels(harness, monkeypatch):
    api, user, store = harness

    approved = mapping()
    approved["canonical_column_order"] = [
        "First Name (or Initial)",
        "Last Name (FULL)",
        "Social Security number (SSN)",
        "Date of Birth (DOB)",
        "Street 1",
    ]

    rows = []
    for ucid, doc, dob in [
        ("R1", "D1", "1985-04-12"),
        ("R2", "D2", "1990-01-01"),
    ]:
        rows.append({
            "ucid": ucid,
            "doc_id": doc,
            "metadata": {
                "First Name (or Initial)": "Jordan",
                "Last Name (FULL)": "Sample",
                "Social Security number (SSN)": "900-12-0001",
                "Date of Birth (DOB)": dob,
                "Street 1": "100 Main Street",
            },
            "provenance": {
                "header_set_id": "HDR-1",
                "source_row_number": 2,
            },
        })

    configure(monkeypatch, api, approved=approved, records=rows)

    result = preview(
        api,
        user,
        [
            "First Name (or Initial)",
            "Last Name (FULL)",
            "Social Security number (SSN)",
        ],
    )

    assert result["duplicate_group_count"] == 0
    assert result["conflict_group_count"] == 1
    assert "Date of Birth (DOB)" in result["conflict_headers_checked"]
    assert "Date of Birth (DOB)" in result["conflicts"][0]["conflict_fields"]
    assert store["writes"] == 0