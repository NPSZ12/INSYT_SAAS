"""Validate a complete, unambiguous Cyber2 iterative Merge Set chain.

This is a pure pre-transfer validation; no Azure access or writes.
The caller must use verified, project-scoped completed-set records.
"""


class C2MergeLineageError(ValueError):
    pass


def require_complete_c2_lineage(
    completed_sets,
    *,
    header_set_id,
    merge_set_id,
):
    if not isinstance(completed_sets, list):
        raise C2MergeLineageError("Invalid Merge Set inventory")

    # list_completed currently has a bounded listing.
    # Never infer a complete chain from a potentially truncated result.
    if len(completed_sets) >= 1000:
        raise C2MergeLineageError(
            "Merge Set inventory may be incomplete"
        )

    if not isinstance(header_set_id, str) or not header_set_id:
        raise C2MergeLineageError("Missing Header Set identity")

    if not isinstance(merge_set_id, str) or not merge_set_id:
        raise C2MergeLineageError("Missing selected Merge Set")

    all_ids = set()
    for item in completed_sets:
        if not isinstance(item, dict):
            raise C2MergeLineageError("Invalid completed-set record")

        item_id = item.get("merge_set_id")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in all_ids
        ):
            raise C2MergeLineageError(
                "Duplicate or invalid completed-set identity"
            )
        all_ids.add(item_id)

    members = {
        item["merge_set_id"]: item
        for item in completed_sets
        if item.get("header_set_id") == header_set_id
        and item.get("status") == "completed"
    }

    if merge_set_id not in members:
        raise C2MergeLineageError(
            "Selected Merge Set is not completed in this Header Set"
        )

    children = {key: [] for key in members}
    roots = []

    for item_id, item in members.items():
        parent_id = item.get("parent_merge_set_id")

        if parent_id in (None, ""):
            roots.append(item_id)
            continue

        if (
            not isinstance(parent_id, str)
            or parent_id not in members
            or parent_id == item_id
        ):
            raise C2MergeLineageError(
                "Missing or invalid same-Header-Set parent"
            )

        children[parent_id].append(item_id)

    if len(roots) != 1:
        raise C2MergeLineageError(
            "Merge Set lineage has multiple or missing roots"
        )

    terminals = [
        key for key, descendants in children.items()
        if not descendants
    ]

    if len(terminals) != 1 or terminals[0] != merge_set_id:
        raise C2MergeLineageError(
            "Selected Merge Set is not the unique terminal"
        )

    visited = set()
    current = merge_set_id

    while current is not None:
        if current in visited:
            raise C2MergeLineageError("Cyclic Merge Set lineage")

        visited.add(current)
        parent = members[current].get("parent_merge_set_id")
        current = parent if parent else None

    if visited != set(members):
        raise C2MergeLineageError(
            "Disconnected or forked Merge Set lineage"
        )

    return {
        "lineage_verified": True,
        "header_set_id": header_set_id,
        "merge_set_id": merge_set_id,
        "pass_count": len(visited),
    }
