"""No Azure dependency: Cyber² field-specific RAW evidence contract."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.cyber2.field_evidence import FieldEvidenceError, find_field_evidence


def raw(i, *, ssn=None, dob=None, name="John Smith"):
    metadata = {"Name": name, "DOB": dob or "", "SSN": ssn or "", "UCID": f"RAW-{i:03}"}
    return {
        "ucid": f"RAW-{i:03}",
        "doc_id": f"DOC-{i:03}",
        "metadata": metadata,
        "provenance": {"source_row_number": i + 1, "original_filename": f"source-{i}.json", "source_csv_path": "staging/example.csv"},
    }


def test_one_ssn_source_out_of_one_hundred_and_raw_is_unchanged():
    records = [raw(i, ssn="123-45-6789" if i == 47 else None, dob="1980-04-15" if i < 8 else None) for i in range(100)]
    before = copy.deepcopy(records)
    result = find_field_evidence(records, entity_raw_ucids=[r["ucid"] for r in records], field="SSN")
    assert result["entity_raw_record_count"] == 100
    assert result["matching_document_count"] == 1
    assert result["matching_occurrence_count"] == 1
    assert result["documents"][0]["source_doc_id"] == "DOC-047"
    assert result["documents"][0]["occurrences"][0]["source_field"] == "SSN"
    assert records == before


def test_dob_only_returns_dob_sources_and_not_other_entity():
    records = [raw(i, dob="1980-04-15" if i < 7 else None) for i in range(10)]
    records.append(raw(99, dob="1980-04-15", name="Different Person"))
    result = find_field_evidence(records, entity_raw_ucids=[f"RAW-{i:03}" for i in range(10)], field="DOB")
    assert result["matching_document_count"] == 7
    assert all(doc["source_doc_id"] != "DOC-099" for doc in result["documents"])


def test_multiple_ssn_values_are_filterable_exactly():
    records = [raw(1, ssn="111"), raw(2, ssn="222"), raw(3, ssn="111")]
    result = find_field_evidence(records, entity_raw_ucids=["RAW-001", "RAW-002", "RAW-003"], field="SSN", value="111")
    assert [doc["source_doc_id"] for doc in result["documents"]] == ["DOC-001", "DOC-003"]


def test_explicit_approved_field_mapping_only():
    records = [raw(1)]
    records[0]["metadata"]["social_security_number"] = "111"
    assert find_field_evidence(records, entity_raw_ucids=["RAW-001"], field="SSN")["matching_document_count"] == 0
    result = find_field_evidence(records, entity_raw_ucids=["RAW-001"], field="SSN", field_aliases={"social_security_number": "SSN"})
    assert result["matching_document_count"] == 1


def test_missing_raw_records_fail_closed():
    with pytest.raises(FieldEvidenceError, match="Incomplete RAW"):
        find_field_evidence([raw(1)], entity_raw_ucids=["RAW-001", "RAW-002"], field="SSN")


def test_bad_raw_linkage_fail_closed():
    record = raw(1, ssn="111")
    record["doc_id"] = ""
    with pytest.raises(FieldEvidenceError, match="doc_id"):
        find_field_evidence([record], entity_raw_ucids=["RAW-001"], field="SSN")


def test_no_entity_ucids_never_returns_anyone_elses_records():
    assert find_field_evidence([raw(1, ssn="111")], entity_raw_ucids=[], field="SSN")["documents"] == []
