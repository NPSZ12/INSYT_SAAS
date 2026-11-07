from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionContinuationPlan:
    selected_units: tuple[str, ...]
    remaining_units: tuple[str, ...]
    completed_count: int
    total_count: int
    job_complete: bool

    @property
    def requires_continuation(self) -> bool:
        return not self.job_complete


def plan_detection_continuation(
    *,
    all_unit_ids: list[str],
    completed_unit_ids: set[str],
    max_units_per_invocation: int,
) -> DetectionContinuationPlan:
    """
    Plan bounded detection work using verified checkpoints.

    Completed IDs must come from independently verified
    durable storage, never status.json.

    The plan is a snapshot, not a work claim.
    Recalculate it after the selected units execute.
    """
    if (
        type(max_units_per_invocation) is not int
        or max_units_per_invocation < 1
    ):
        raise ValueError(
            "max_units_per_invocation must be positive."
        )

    if not all_unit_ids:
        raise ValueError("Detection work population is empty.")

    if any(
        not isinstance(unit_id, str)
        or not unit_id.strip()
        for unit_id in all_unit_ids
    ):
        raise ValueError("Invalid detection work-unit ID.")

    if len(set(all_unit_ids)) != len(all_unit_ids):
        raise ValueError("Duplicate detection work-unit IDs.")

    if not isinstance(completed_unit_ids, set):
        raise TypeError("Completed work units must be a set.")

    completed = set(completed_unit_ids)
    population = set(all_unit_ids)

    if not completed.issubset(population):
        raise ValueError(
            "Completed checkpoints contain unknown work units."
        )

    unfinished = tuple(
        unit_id
        for unit_id in all_unit_ids
        if unit_id not in completed
    )

    selected = unfinished[:max_units_per_invocation]
    remaining = unfinished[max_units_per_invocation:]

    return DetectionContinuationPlan(
        selected_units=selected,
        remaining_units=remaining,
        completed_count=len(completed),
        total_count=len(all_unit_ids),
        job_complete=(len(unfinished) == 0),
    )