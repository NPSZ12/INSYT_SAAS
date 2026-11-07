from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .detection_continuation_plan import (
    plan_detection_continuation,
)


@dataclass(frozen=True)
class BoundedInvocationResult:
    executed_units: tuple[str, ...]
    completed_count: int
    total_count: int
    job_complete: bool
    continuation_enqueued: bool


def execute_bounded_invocation(
    *,
    all_unit_ids: list[str],
    max_units_per_invocation: int,
    verified_completed: Callable[[], set[str]],
    execute_unit: Callable[[str], None],
    enqueue_continuation: Callable[[], None],
    finalize_job: Callable[[], None],
) -> BoundedInvocationResult:
    """
    Coordinate one bounded detection invocation.

    Completion is based on fresh durable verification,
    not on the number of attempted work units.

    This is an orchestration primitive, not yet a
    distributed scheduler or production worker entry point.
    """
    for name, callback in (
        ("verified_completed", verified_completed),
        ("execute_unit", execute_unit),
        ("enqueue_continuation", enqueue_continuation),
        ("finalize_job", finalize_job),
    ):
        if not callable(callback):
            raise TypeError(f"{name} must be callable.")

    before = plan_detection_continuation(
        all_unit_ids=all_unit_ids,
        completed_unit_ids=verified_completed(),
        max_units_per_invocation=max_units_per_invocation,
    )

    executed = []

    for unit_id in before.selected_units:
        execute_unit(unit_id)

        # Fail closed if a unit returns without
        # producing a verified durable checkpoint.
        if unit_id not in verified_completed():
            raise RuntimeError(
                f"Work unit not durably completed: {unit_id}"
            )

        executed.append(unit_id)

    after = plan_detection_continuation(
        all_unit_ids=all_unit_ids,
        completed_unit_ids=verified_completed(),
        max_units_per_invocation=max_units_per_invocation,
    )

    if after.job_complete:
        finalize_job()

        return BoundedInvocationResult(
            executed_units=tuple(executed),
            completed_count=after.completed_count,
            total_count=after.total_count,
            job_complete=True,
            continuation_enqueued=False,
        )

    # Enqueue before returning successfully.
    # If enqueue raises, propagate the failure so
    # the current queue invocation is not acknowledged.
    enqueue_continuation()

    return BoundedInvocationResult(
        executed_units=tuple(executed),
        completed_count=after.completed_count,
        total_count=after.total_count,
        job_complete=False,
        continuation_enqueued=True,
    )