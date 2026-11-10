"""C2 projection and evidence-retention regressions."""

from copy import deepcopy

import pytest

from app.services.cyber2.c2_transfer_projection import (
    C2ProjectionError,
    build_c2_projection,
)


def fixture():
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDR-TEST",
    }

    merge = {
        **scope,
        "merge_set_id": "MSET-" + "A" * 32,
        "integrity_sha256": "b" * 64,
        "status": "completed",
        "approved_headers": [
            "First Name", "Gross Pay", "Custom Field"
        ],
        "raw_record_count": 2,
        "working_record_count": 1,
        "working_records": [{
            "working_record_id": "WORK-000001",
            "classification": "exact_merged",
            "source_ucids": ["U1", "U2"],
            "source_doc_ids": ["DOC-1", "DOC-2"],
            "cells": {
                "First Name": "Alex",
                "Gross Pay": "1450.00; 1512.42",
                "Custom Field": "Original evidence",
            },
            "field_provenance": {
                "First Name": [{"ucid": "U1"}, {"ucid": "U2"}],
                "Gross Pay": [
                    {"ucid": "U1", "original_value": "1450.00"},
                    {"ucid": "U2", "original_value": "1512.42"},
                ],
                "Custom Field": [
                    {"ucid": "U1"}, {"ucid": "U2"}
                ],
            },
        }],
    }

    mapping = {
        **scope,
        "status": "approved",
        "protocol_headers": ["First Name", "Gross Pay", "DOB"],
    }

    conservation = {
        "source_conservation_verified": True,
        "header_set_id": "HDR-TEST",
        "working_record_count": 1,
        "original_source_record_count": 2,
    }

    origin = {
        "origin_authorized": True,
        "merge_set_id": merge["merge_set_id"],
        "header_set_id": "HDR-TEST",
    }

    return merge, mapping, conservation, origin


def test_retains_complete_original_evidence():
    inputs = fixture()
    before = deepcopy(inputs)

    result = build_c2_projection(*inputs)

    assert result["working_record_count"] == 1
    assert result["original_source_record_count"] == 2
    assert result["headers"] == [
        "Doc ID", "First Name", "Gross Pay", "DOB"
    ]
    assert result["rows"][0]["DOB"] == ""
    assert result["rows"][0]["Doc ID"] == "DOC-1; DOC-2"
    assert result["records"][0]["source_ucids"] == ["U1", "U2"]
    assert result["records"][0]["cells"]["Custom Field"] == (
        "Original evidence"
    )
    assert result["records"][0]["field_provenance"][
        "Gross Pay"
    ][1]["original_value"] == "1512.42"
    assert inputs == before


@pytest.mark.parametrize("index", [2, 3])
def test_requires_both_prior_validation_results(index):
    inputs = list(fixture())
    inputs[index] = {}
    with pytest.raises(C2ProjectionError):
        build_c2_projection(*inputs)


def test_rejects_wrong_origin_merge_binding():
    inputs = list(fixture())
    inputs[3]["merge_set_id"] = "MSET-OTHER"
    with pytest.raises(C2ProjectionError):
        build_c2_projection(*inputs)


def test_rejects_duplicate_source_identity():
    inputs = list(fixture())
    repeated = deepcopy(inputs[0]["working_records"][0])
    repeated["working_record_id"] = "WORK-000002"
    inputs[0]["working_records"].append(repeated)
    inputs[0]["working_record_count"] = 2
    inputs[2]["working_record_count"] = 2

    with pytest.raises(C2ProjectionError):
        build_c2_projection(*inputs)


def test_rejects_wrong_project():
    inputs = list(fixture())
    inputs[1]["project"] = "Other"

    with pytest.raises(C2ProjectionError):
        build_c2_projection(*inputs)


def test_rejects_missing_source_ucid():
    inputs = list(fixture())
    inputs[0]["working_records"][0]["source_ucids"] = ["U1"]

    with pytest.raises(C2ProjectionError):
        build_c2_projection(*inputs)
