"""Verify actual saved Merge Set lineage, not only summaries."""

from copy import deepcopy

import pytest

from app.services.cyber2.c2_merge_lineage import (
    C2MergeLineageError,
)
from app.services.cyber2.c2_stored_lineage import (
    verify_c2_stored_lineage,
)


ROOT = "MSET-" + "A" * 32
CHILD = "MSET-" + "B" * 32


def fixture():
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDR-1",
        "status": "completed",
    }

    root = {
        **scope,
        "merge_set_id": ROOT,
        "raw_record_count": 2,
        "working_record_count": 2,
    }

    child = {
        **scope,
        "merge_set_id": CHILD,
        "parent_merge_set_id": ROOT,
        "pass_number": 2,
        "raw_record_count": 2,
        "working_record_count": 1,
    }

    documents = {
        ROOT: deepcopy(root),
        CHILD: deepcopy(child),
    }

    class Store:
        def __init__(self):
            self.loaded = []

        def load(self, merge_id):
            self.loaded.append(merge_id)
            return deepcopy(documents[merge_id])

    return Store(), [root, child], documents


def verify(store, summaries):
    return verify_c2_stored_lineage(
        store,
        summaries,
        workspace="capture",
        client="Demo",
        project="Payroll",
        header_set_id="HDR-1",
        merge_set_id=CHILD,
    )


def test_loads_and_verifies_every_pass():
    store, summaries, _ = fixture()

    result = verify(store, summaries)

    assert result["stored_lineage_verified"] is True
    assert result["verified_pass_count"] == 2
    assert store.loaded == [CHILD, ROOT]


def test_rejects_corrupt_ancestor_load():
    store, summaries, _ = fixture()

    original = store.load

    def corrupted(merge_id):
        if merge_id == ROOT:
            raise ValueError("SHA-256 integrity failure")
        return original(merge_id)

    store.load = corrupted

    with pytest.raises(
        C2MergeLineageError,
        match="could not be verified",
    ):
        verify(store, summaries)


def test_rejects_parent_mismatch():
    store, summaries, documents = fixture()
    documents[CHILD]["parent_merge_set_id"] = "MSET-OTHER"

    with pytest.raises(C2MergeLineageError):
        verify(store, summaries)


def test_rejects_wrong_project_in_ancestor():
    store, summaries, documents = fixture()
    documents[ROOT]["project"] = "Other"

    with pytest.raises(
        C2MergeLineageError,
        match="scope mismatch",
    ):
        verify(store, summaries)


def test_rejects_changed_ancestor_counts():
    store, summaries, documents = fixture()
    documents[ROOT]["working_record_count"] = 999

    with pytest.raises(
        C2MergeLineageError,
        match="counts differ",
    ):
        verify(store, summaries)


def test_rejects_missing_parent_summary():
    store, summaries, _ = fixture()

    with pytest.raises(C2MergeLineageError):
        verify(store, summaries[1:])


def test_rejects_forked_lineage():
    store, summaries, _ = fixture()
    third = deepcopy(summaries[1])
    third["merge_set_id"] = "MSET-" + "C" * 32
    summaries.append(third)

    with pytest.raises(C2MergeLineageError):
        verify(store, summaries)


def test_readiness_calls_stored_ancestor_verifier():
    from pathlib import Path

    source = Path(
        "backend/app/api/cyber2/membership_api.py"
    ).read_text(encoding="utf-8-sig")

    start = source.index(
        "def inspect_cyber2_c2_transfer_readiness("
    )
    end = source.index(
        "class C2OriginApprovalBody(", start
    )
    route = source[start:end]

    assert "verify_c2_stored_lineage(" in route
    assert "validate_c2_merge_population(" in route
    assert route.index(
        "verify_c2_stored_lineage("
    ) < route.index(
        "validate_c2_merge_population("
    )
