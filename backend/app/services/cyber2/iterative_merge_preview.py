"""Pure second-pass exact grouping of verified Cyber2 working records.

No Azure reads/writes. Never changes a parent completed merge set.
"""

from collections import defaultdict

from app.services.cyber2.iterative_merge_input import (
    IterativeMergeInputError,
    prepare_iterative_candidates,
)


def preview_iterative_merge(parent, merge_index, conflict_headers):
    prepared = prepare_iterative_candidates(parent, merge_index)
    headers = parent["approved_headers"]

    if (
        not isinstance(conflict_headers, (list, tuple))
        or len(conflict_headers) != len(set(conflict_headers))
        or any(field not in headers for field in conflict_headers)
    ):
        raise IterativeMergeInputError("Invalid conflict headers")

    records = {
        record["working_record_id"]: record
        for record in parent["working_records"]
    }

    groups_by_key = defaultdict(list)

    for candidate in prepared["candidates"]:
        groups_by_key[candidate["key"]].append(candidate)

    exact = []
    conflicts = []
    unmatched = []

    def field_values(record, field):
        values = set()
        missing = False

        for evidence in record["field_provenance"][field]:
            value = evidence.get("original_value")

            if value is None or (
                isinstance(value, str) and not value.strip()
            ):
                missing = True
            elif isinstance(value, str):
                values.add(value.strip())
            else:
                raise IterativeMergeInputError(
                    "Unsupported strong identifier value"
                )

        return values, missing

    for members in groups_by_key.values():
        if len(members) == 1:
            unmatched.append(members[0])
            continue

        flagged = []

        for field in conflict_headers:
            combined = set()
            any_missing = False
            any_present = False

            for member in members:
                record = records[member["working_record_id"]]
                values, missing = field_values(record, field)

                combined.update(values)
                any_present = any_present or bool(values)
                any_missing = any_missing or missing or not values

            if len(combined) > 1 or (
                any_present and any_missing
            ):
                flagged.append(field)

        output_members = [
            {
                "working_record_id": member["working_record_id"],
                "source_ucids": list(member["source_ucids"]),
                "source_doc_ids": list(member["source_doc_ids"]),
            }
            for member in members
        ]

        group = {
            "member_count": len(members),
            "members": output_members,
        }

        if flagged:
            conflicts.append({
                **group,
                "conflict_fields": flagged,
                "reason": "conflicting_or_incomplete_evidence",
            })
        else:
            exact.append(group)

    projected = (
        len(exact)
        + sum(group["member_count"] for group in conflicts)
        + len(unmatched)
        + len(prepared["excluded"])
    )

    return {
        "status": "iterative_preview",
        "parent_merge_set_id": prepared["parent_merge_set_id"],
        "header_set_id": prepared["header_set_id"],
        "merge_index": list(merge_index),
        "input_working_record_count": (
            prepared["input_working_record_count"]
        ),
        "original_source_record_count": (
            prepared["original_source_record_count"]
        ),
        "duplicate_group_count": len(exact),
        "conflict_group_count": len(conflicts),
        "projected_working_record_count": projected,
        "groups": exact,
        "conflicts": conflicts,
        "unmatched": unmatched,
        "excluded": prepared["excluded"],
        "execution_enabled": False,
    }
