"""Cyber2 stale-preview fingerprint regression tests."""

import copy
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.cyber2.merge_snapshot import (
    MergeSnapshotError,
    merge_snapshot_fingerprint,
)

from test_cyber2_exact_preview_api import mapping, raw


INDEX = ["First Name", "Last Name", "SSN"]


def snapshot(approved=None, records=None, index=None):
    return merge_snapshot_fingerprint(
        approved_mapping=approved if approved is not None else mapping(),
        merge_index=index if index is not None else INDEX,
        raw_records=records if records is not None else [
            raw("R1", "D1"),
            raw("R2", "D2"),
        ],
    )


def test_identical_snapshot_has_identical_fingerprint():
    assert snapshot() == snapshot()
    assert len(snapshot()) == 64


def test_raw_record_order_does_not_change_fingerprint():
    records = [raw("R1", "D1"), raw("R2", "D2")]
    assert snapshot(records=records) == snapshot(
        records=list(reversed(records))
    )


def test_changed_captured_value_invalidates_preview():
    records = [raw("R1", "D1"), raw("R2", "D2")]
    original = snapshot(records=records)

    changed = copy.deepcopy(records)
    changed[1]["metadata"]["Street 1"] = "Changed address"

    assert snapshot(records=changed) != original


def test_changed_source_provenance_invalidates_preview():
    records = [raw("R1", "D1"), raw("R2", "D2")]
    original = snapshot(records=records)

    changed = copy.deepcopy(records)
    changed[1]["provenance"]["source_row_number"] = 99

    assert snapshot(records=changed) != original


def test_changed_mapping_invalidates_preview():
    approved = mapping()
    original = snapshot(approved=approved)

    changed = copy.deepcopy(approved)
    changed["canonical_column_order"] = list(reversed(
        changed["canonical_column_order"]
    ))

    assert snapshot(approved=changed) != original


def test_changed_merge_index_invalidates_preview():
    assert snapshot() != snapshot(
        index=["First Name", "Last Name", "DOB"]
    )


def test_added_source_record_invalidates_preview():
    records = [raw("R1", "D1"), raw("R2", "D2")]
    original = snapshot(records=records)

    changed = copy.deepcopy(records)
    changed.append(raw("R3", "D2"))

    assert snapshot(records=changed) != original


def test_missing_approved_document_rejected():
    with pytest.raises(MergeSnapshotError):
        snapshot(records=[raw("R1", "D1")])


def test_duplicate_ucid_rejected():
    with pytest.raises(MergeSnapshotError):
        snapshot(records=[
            raw("R1", "D1"),
            raw("R1", "D2"),
        ])


def test_other_header_set_does_not_change_fingerprint():
    records = [raw("R1", "D1"), raw("R2", "D2")]
    original = snapshot(records=records)

    outside = raw("OTHER", "D9")
    outside["provenance"]["header_set_id"] = "OTHER-SET"

    assert snapshot(records=records + [outside]) == original


def test_source_population_not_modified():
    approved = mapping()
    records = [raw("R1", "D1"), raw("R2", "D2")]

    original_mapping = copy.deepcopy(approved)
    original_records = copy.deepcopy(records)

    snapshot(approved=approved, records=records)

    assert approved == original_mapping
    assert records == original_records
