"""Pure approval tests; no Azure clients, network, or database required."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.cyber2.entity_membership import (
    MembershipError, approved_entity_ucids, merge_entities,
    new_registry, register_entity,
)
from app.services.cyber2.membership_approval import approve_entity


def pending():
    base = new_registry(workspace="capture", client="TEST", project="P1")
    return register_entity(
        base, entity_id="E1", raw_ucids=["R1", "R2"],
        known_raw_ucids=["R1", "R2", "R3"], actor="analyst", status="pending",
    )


def test_approval_preserves_raw_and_original_snapshot():
    before = pending()
    after = approve_entity(before, entity_id="E1", actor="reviewer1", note="Confirmed")
    assert before["entities"]["E1"]["status"] == "pending"
    assert after["entities"]["E1"]["status"] == "approved"
    assert approved_entity_ucids(after, entity_id="E1") == ["R1", "R2"]
    assert after["revision"] == before["revision"] + 1


def test_approval_appends_audit_event():
    before = pending()
    after = approve_entity(before, entity_id="E1", actor="reviewer1")
    assert after["history"][:-1] == before["history"]
    event = after["history"][-1]
    assert event["operation"] == "approve"
    assert event["actor"] == "reviewer1"
    assert event["before_entities"]["E1"]["status"] == "pending"
    assert event["after_entities"]["E1"]["status"] == "approved"


def test_reject_double_approval():
    approved = approve_entity(pending(), entity_id="E1", actor="reviewer1")
    with pytest.raises(MembershipError):
        approve_entity(approved, entity_id="E1", actor="reviewer2")


def test_reject_unknown_entity():
    with pytest.raises(MembershipError):
        approve_entity(pending(), entity_id="DOES_NOT_EXIST", actor="reviewer1")


def test_reject_blank_actor():
    with pytest.raises(MembershipError):
        approve_entity(pending(), entity_id="E1", actor="")


def test_reject_duplicate_raw_membership_in_corrupt_registry():
    corrupted = pending()
    corrupted["entities"]["E2"] = {"status": "pending", "raw_ucids": ["R1"]}
    with pytest.raises(MembershipError):
        approve_entity(corrupted, entity_id="E1", actor="reviewer1")


def test_approved_entity_can_enter_existing_merge_workflow():
    approved = approve_entity(pending(), entity_id="E1", actor="reviewer1")
    approved = register_entity(
        approved, entity_id="E2", raw_ucids=["R3"],
        known_raw_ucids=["R1", "R2", "R3"], actor="analyst", status="approved",
    )
    merged = merge_entities(
        approved, target_entity_id="E1", source_entity_ids=["E2"],
        known_raw_ucids=["R1", "R2", "R3"], actor="reviewer1",
    )
    assert approved_entity_ucids(merged, entity_id="E1") == ["R1", "R2", "R3"]
