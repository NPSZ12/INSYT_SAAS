import pytest

from apc.detection_continuation_plan import (
    plan_detection_continuation,
)


def _plan(completed=(), limit=2):
    return plan_detection_continuation(
        all_unit_ids=["a", "b", "c", "d", "e"],
        completed_unit_ids=set(completed),
        max_units_per_invocation=limit,
    )


def test_initial_batch_is_bounded():
    plan = _plan()

    assert plan.selected_units == ("a", "b")
    assert plan.remaining_units == ("c", "d", "e")
    assert plan.job_complete is False
    assert plan.requires_continuation is True


def test_restart_skips_completed_units():
    plan = _plan(completed={"a", "b"})

    assert plan.selected_units == ("c", "d")
    assert plan.remaining_units == ("e",)


def test_out_of_order_completion_is_supported():
    plan = _plan(completed={"a", "c", "e"})

    assert plan.selected_units == ("b", "d")
    assert plan.remaining_units == ()
    assert plan.job_complete is False


def test_job_completes_only_when_every_unit_verified():
    plan = _plan(
        completed={"a", "b", "c", "d", "e"}
    )

    assert plan.selected_units == ()
    assert plan.remaining_units == ()
    assert plan.job_complete is True
    assert plan.requires_continuation is False


def test_unknown_completed_checkpoint_is_rejected():
    with pytest.raises(ValueError):
        _plan(completed={"unknown"})


def test_duplicate_units_are_rejected():
    with pytest.raises(ValueError):
        plan_detection_continuation(
            all_unit_ids=["a", "a"],
            completed_unit_ids=set(),
            max_units_per_invocation=1,
        )


def test_invalid_batch_limits_are_rejected():
    for limit in (0, -1, True):
        with pytest.raises(ValueError):
            _plan(limit=limit)


def test_planning_is_deterministic():
    first = _plan(completed={"a"})
    second = _plan(completed={"a"})

    assert first == second


def test_current_batch_is_not_completion():
    plan = _plan(
        completed={"a", "b", "c"},
        limit=2,
    )

    assert plan.selected_units == ("d", "e")
    assert plan.remaining_units == ()
    assert plan.job_complete is False

    # Completion is established only after verifying
    # the newly completed units and replanning.
    final = _plan(
        completed={"a", "b", "c", "d", "e"}
    )

    assert final.job_complete is True

def test_selected_final_batch_still_requires_continuation():
    plan = _plan(
        completed={"a", "b", "c"},
        limit=2,
    )

    assert plan.selected_units == ("d", "e")
    assert plan.remaining_units == ()
    assert plan.job_complete is False

    # Selecting the final batch is not completing it.
    assert plan.requires_continuation is True

    verified = _plan(
        completed={"a", "b", "c", "d", "e"}
    )

    assert verified.job_complete is True
    assert verified.requires_continuation is False