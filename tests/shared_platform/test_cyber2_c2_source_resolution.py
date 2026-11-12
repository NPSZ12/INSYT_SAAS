import pytest

from app.services.cyber2.c2_source_resolution import (
    C2SourceResolutionError,
    resolve_c2_source_document,
)


RECORD_ID = "MSET-" + ("A" * 32) + ":WR1"
MERGE_ID = "MSET-" + ("A" * 32)


def fixtures():
    snapshot = {
        "status": "transferred",
        "merge_set_id": MERGE_ID,
        "projection": {
            "records": [
                {
                    "c2_record_id": RECORD_ID,
                    "merge_set_id": MERGE_ID,
                    "source_doc_ids": ["D1", "D2", "D3"],
                },
                {
                    "c2_record_id": MERGE_ID + ":WR2",
                    "merge_set_id": MERGE_ID,
                    "source_doc_ids": ["D1"],
                },
            ],
        },
    }
    mapping = {
        "status": "approved",
        "documents": [
            {"doc_id": "D1", "source_csv_path": "project/source/one.csv"},
            {"doc_id": "D2", "source_csv_path": "project/source/two.csv"},
            {"doc_id": "D3", "source_csv_path": "project/source/three.csv"},
        ],
    }
    return snapshot, mapping


def resolve(snapshot, mapping, doc_id="D2", record_id=RECORD_ID):
    return resolve_c2_source_document(
        snapshot, mapping, doc_id=doc_id, record_id=record_id
    )


def test_resolves_single_member_and_full_navigation_order():
    snapshot, mapping = fixtures()
    result = resolve(snapshot, mapping)
    assert result["doc_id"] == "D2"
    assert result["doc_ids"] == ["D1", "D2", "D3"]
    assert result["doc_index"] == 1
    assert result["doc_count"] == 3
    assert result["source_path"] == "project/source/two.csv"


def test_unknown_record_fails():
    snapshot, mapping = fixtures()
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping, record_id="unknown")


def test_unrelated_document_fails():
    snapshot, mapping = fixtures()
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping, doc_id="D4")


def test_duplicate_approved_document_fails():
    snapshot, mapping = fixtures()
    mapping["documents"].append(mapping["documents"][1].copy())
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)


def test_incomplete_source_membership_fails():
    snapshot, mapping = fixtures()
    snapshot["projection"]["records"][0]["source_doc_ids"] = ["D1", "D1"]
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)


def test_missing_source_path_fails():
    snapshot, mapping = fixtures()
    mapping["documents"][1]["source_csv_path"] = ""
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)


def test_unapproved_mapping_fails():
    snapshot, mapping = fixtures()
    mapping["status"] = "pending"
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)


def test_untransferred_snapshot_fails():
    snapshot, mapping = fixtures()
    snapshot["status"] = "pending"
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)


def test_transfer_identity_mismatch_fails():
    snapshot, mapping = fixtures()
    snapshot["projection"]["records"][0]["merge_set_id"] = "OTHER"
    with pytest.raises(C2SourceResolutionError):
        resolve(snapshot, mapping)
