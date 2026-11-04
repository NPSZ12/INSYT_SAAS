import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.cyber2.entity_membership import (
    MembershipError, approved_entity_ucids, merge_entities, new_registry,
    register_entity, reverse_last_merge,
)


def base():
    return new_registry(workspace="capture", client="ACME", project="Case_A")


def add(r, name, ucid, status="approved"):
    return register_entity(r, entity_id=name, raw_ucids=[ucid], known_raw_ucids=["RAW1", "RAW2", "RAW3"], actor="reviewer", status=status)


def test_scope():
    assert base()["project"] == "Case_A"
    with pytest.raises(MembershipError):
        new_registry(workspace="other", client="ACME", project="Case_A")


def test_register_and_retrieve():
    r = add(base(), "E1", "RAW1")
    assert approved_entity_ucids(r, entity_id="E1") == ["RAW1"]
    assert base()["entities"] == {}


def test_pending_cannot_be_queried():
    with pytest.raises(MembershipError):
        approved_entity_ucids(add(base(), "E1", "RAW1", status="pending"), entity_id="E1")


def test_reject_cross_entity_duplicate():
    r = add(base(), "E1", "RAW1")
    with pytest.raises(MembershipError):
        add(r, "E2", "RAW1")


def test_reject_unknown_raw():
    with pytest.raises(MembershipError):
        register_entity(base(), entity_id="E1", raw_ucids=["NOPE"], known_raw_ucids=["RAW1"], actor="reviewer")


def test_merge_and_reverse_preserve_members():
    r = add(add(base(), "E1", "RAW1"), "E2", "RAW2")
    merged = merge_entities(r, target_entity_id="E1", source_entity_ids=["E2"], actor="reviewer", known_raw_ucids=["RAW1", "RAW2"])
    assert approved_entity_ucids(merged, entity_id="E1") == ["RAW1", "RAW2"]
    assert "E2" not in merged["entities"]
    assert r["entities"]["E1"]["raw_ucids"] == ["RAW1"]
    undone = reverse_last_merge(merged, actor="reviewer")
    assert approved_entity_ucids(undone, entity_id="E1") == ["RAW1"]
    assert approved_entity_ucids(undone, entity_id="E2") == ["RAW2"]
    assert undone["revision"] == merged["revision"] + 1


def test_merge_must_be_approved():
    r = add(add(base(), "E1", "RAW1"), "E2", "RAW2", status="pending")
    with pytest.raises(MembershipError):
        merge_entities(r, target_entity_id="E1", source_entity_ids=["E2"], actor="reviewer", known_raw_ucids=["RAW1", "RAW2"])


def test_prevent_unrelated_reverse():
    r = add(base(), "E1", "RAW1")
    with pytest.raises(MembershipError):
        reverse_last_merge(r, actor="reviewer")


def test_corrupt_duplicate_registry_rejected():
    r = add(base(), "E1", "RAW1")
    r["entities"]["E2"] = {"status": "approved", "raw_ucids": ["RAW1"]}
    with pytest.raises(MembershipError):
        approved_entity_ucids(r, entity_id="E1")
