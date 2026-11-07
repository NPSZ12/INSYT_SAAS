import pytest

from apc.detection_bounded_coordinator import (
    execute_bounded_invocation,
)


def harness():
    state = {
        "completed": set(),
        "executed": [],
        "enqueued": 0,
        "finalized": 0,
    }

    def verified():
        return set(state["completed"])

    def execute(unit):
        state["executed"].append(unit)
        state["completed"].add(unit)

    def enqueue():
        state["enqueued"] += 1

    def finalize():
        state["finalized"] += 1

    callbacks = {
        "verified_completed": verified,
        "execute_unit": execute,
        "enqueue_continuation": enqueue,
        "finalize_job": finalize,
    }

    return state, callbacks


def invoke(callbacks, *, limit=2):
    return execute_bounded_invocation(
        all_unit_ids=["a", "b", "c", "d", "e"],
        max_units_per_invocation=limit,
        **callbacks,
    )


def test_first_invocation_is_bounded():
    state, callbacks = harness()

    result = invoke(callbacks)

    assert result.executed_units == ("a", "b")
    assert result.completed_count == 2
    assert result.continuation_enqueued is True
    assert result.job_complete is False
    assert state["enqueued"] == 1
    assert state["finalized"] == 0


def test_three_invocations_finish_one_job():
    state, callbacks = harness()

    first = invoke(callbacks)
    second = invoke(callbacks)
    third = invoke(callbacks)

    assert first.job_complete is False
    assert second.job_complete is False
    assert third.job_complete is True

    assert state["executed"] == [
        "a", "b", "c", "d", "e"
    ]
    assert state["enqueued"] == 2
    assert state["finalized"] == 1


def test_duplicate_invocation_skips_completed_units():
    state, callbacks = harness()

    state["completed"].update({"a", "c"})

    result = invoke(callbacks)

    assert result.executed_units == ("b", "d")
    assert "a" not in state["executed"]
    assert "c" not in state["executed"]


def test_unverified_work_cannot_advance():
    state, callbacks = harness()

    callbacks["execute_unit"] = (
        lambda unit: state["executed"].append(unit)
    )

    with pytest.raises(
        RuntimeError,
        match="not durably completed",
    ):
        invoke(callbacks)

    assert state["enqueued"] == 0
    assert state["finalized"] == 0


def test_enqueue_failure_propagates():
    state, callbacks = harness()

    def fail_enqueue():
        raise RuntimeError("Synthetic queue failure")

    callbacks["enqueue_continuation"] = fail_enqueue

    with pytest.raises(
        RuntimeError,
        match="Synthetic queue failure",
    ):
        invoke(callbacks)

    assert state["completed"] == {"a", "b"}
    assert state["finalized"] == 0


def test_already_completed_job_requires_no_execution():
    state, callbacks = harness()

    state["completed"].update(
        {"a", "b", "c", "d", "e"}
    )

    result = invoke(callbacks)

    assert result.job_complete is True
    assert result.executed_units == ()
    assert state["enqueued"] == 0
    assert state["finalized"] == 1