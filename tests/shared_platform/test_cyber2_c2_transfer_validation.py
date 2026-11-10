"""C2 transfer conservation and source-isolation regressions."""

from copy import deepcopy

import pytest

from app.services.cyber2.c2_transfer_validation import (
    C2TransferValidationError,
    validate_c2_merge_population,
)


def fixture():
    records = []
    headers = ["First Name", "DOB", "Pay Date", "Gross Pay"]

    for ucid, doc, date, amount in [
        ("U1", "D1", "2026-01-09", "1450.00"),
        ("U2", "D2", "2026-01-23", "1512.42"),
    ]:
        records.append({
            "ucid": ucid,
            "doc_id": doc,
            "metadata": {
                "First Name": "Alex",
                "DOB": "1973-01-01",
                "Pay Date": date,
                "Gross Pay": amount,
            },
            "provenance": {
                "header_set_id": "HDR-TEST",
                "capture_source": "cyber2_mapped_csv",
                "source_row_number": 2,
            },
        })

    evidence = {
        field: [
            {
                "ucid": record["ucid"],
                "doc_id": record["doc_id"],
                "source_row_number": 2,
                "output_header": field,
                "original_value": record["metadata"][field],
            }
            for record in records
        ]
        for field in headers
    }

    merge_set = {
        "status": "completed",
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDR-TEST",
        "integrity_sha256": "a" * 64,
        "approved_headers": headers,
        "raw_record_count": 2,
        "working_record_count": 1,
        "working_records": [{
            "working_record_id": "WORK-000001",
            "source_ucids": ["U1", "U2"],
            "source_doc_ids": ["D1", "D2"],
            "cells": {field: "" for field in headers},
            "field_provenance": evidence,
        }],
    }
    return merge_set, records


def audit(saved, records):
    return validate_c2_merge_population(
        saved,
        records,
        workspace="capture",
        client="Demo",
        project="Payroll",
    )


def test_original_source_conservation_without_transfer():
    saved, records = fixture()
    before = deepcopy((saved, records))

    result = audit(saved, records)

    assert result["working_record_count"] == 1
    assert result["original_source_record_count"] == 2
    assert result["source_conservation_verified"] is True
    assert result["capture_origin_authorized"] is False
    assert result["transfer_authorized"] is False
    assert (saved, records) == before


def test_rejects_ai_or_manual_processing_origin():
    for origin in ["ai_extraction", "manual_capture", "unknown"]:
        saved, records = fixture()
        records[0]["provenance"]["capture_source"] = origin
        with pytest.raises(C2TransferValidationError):
            audit(saved, records)


def test_rejects_source_substitution():
    saved, records = fixture()
    saved["working_records"][0]["field_provenance"][
        "Gross Pay"
    ][1]["original_value"] = "9999.99"

    with pytest.raises(
        C2TransferValidationError,
        match="Field provenance differs",
    ):
        audit(saved, records)


def test_rejects_duplicate_source_membership():
    saved, records = fixture()
    saved["working_records"].append(
        deepcopy(saved["working_records"][0])
    )
    saved["working_records"][1]["working_record_id"] = "WORK-000002"
    saved["working_record_count"] = 2

    with pytest.raises(C2TransferValidationError):
        audit(saved, records)


def test_rejects_wrong_project():
    saved, records = fixture()
    saved["project"] = "Other"

    with pytest.raises(
        C2TransferValidationError,
        match="scope mismatch",
    ):
        audit(saved, records)
