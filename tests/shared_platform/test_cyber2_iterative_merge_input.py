from copy import deepcopy

import pytest

from app.services.cyber2.iterative_merge_input import (
    IterativeMergeInputError,
    prepare_iterative_candidates,
)


def parent():
    def row(ident, ucids, ssns, dob="1985-04-12"):
        headers = ["First Name", "SSN", "DOB"]
        values = {
            "First Name": ["Jordan"] * len(ucids),
            "SSN": ssns,
            "DOB": [dob] * len(ucids),
        }
        return {
            "working_record_id": ident,
            "source_ucids": ucids,
            "source_doc_ids": ["D1"],
            "cells": {
                field: "; ".join(dict.fromkeys(values[field]))
                for field in headers
            },
            "field_provenance": {
                field: [
                    {"ucid": uid, "original_value": val}
                    for uid, val in zip(ucids, values[field])
                ]
                for field in headers
            },
        }

    return {
        "status": "completed",
        "merge_set_id": "MSET-" + "A" * 32,
        "header_set_id": "HDR-1",
        "approved_headers": ["First Name", "SSN", "DOB"],
        "raw_record_count": 4,
        "working_record_count": 2,
        "working_records": [
            row("WORK-000001", ["R1", "R2"], ["111", "111"]),
            row("WORK-000002", ["R3", "R4"], ["222", "333"]),
        ],
    }


def test_uses_parent_working_population_without_mutation():
    source = parent()
    original = deepcopy(source)
    result = prepare_iterative_candidates(source, ["First Name", "SSN"])
    assert result["input_working_record_count"] == 2
    assert result["original_source_record_count"] == 4
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["source_ucids"] == ["R1", "R2"]
    assert result["excluded"][0]["reason"] == "multiple_identifier_values"
    assert source == original


def test_rejects_repeated_original_source_identity():
    source = parent()
    source["working_records"][1]["source_ucids"][0] = "R1"
    source["working_records"][1]["field_provenance"]["SSN"][0]["ucid"] = "R1"
    source["working_records"][1]["field_provenance"]["DOB"][0]["ucid"] = "R1"
    source["working_records"][1]["field_provenance"]["First Name"][0]["ucid"] = "R1"
    with pytest.raises(IterativeMergeInputError):
        prepare_iterative_candidates(source, ["SSN"])


def test_rejects_missing_field_lineage():
    source = parent()
    source["working_records"][0]["field_provenance"]["DOB"].pop()
    with pytest.raises(IterativeMergeInputError):
        prepare_iterative_candidates(source, ["SSN"])


def test_rejects_unapproved_merge_index():
    with pytest.raises(IterativeMergeInputError):
        prepare_iterative_candidates(parent(), ["Employee ID"])


def test_different_index_can_include_both_working_records():
    result = prepare_iterative_candidates(parent(), ["First Name", "DOB"])
    assert len(result["candidates"]) == 2
    assert len(result["excluded"]) == 0
    assert result["candidates"][0]["key"] == result["candidates"][1]["key"]
