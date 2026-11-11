"""Verify every stored Merge Set in a completed C2 lineage.

Uses Cyber2MergeSetStore.load(), which verifies each saved
Merge Set's SHA-256 integrity. No writes are performed.
"""

from app.services.cyber2.c2_merge_lineage import (
    C2MergeLineageError,
    require_complete_c2_lineage,
)


def verify_c2_stored_lineage(
    store,
    completed_sets,
    *,
    workspace,
    client,
    project,
    header_set_id,
    merge_set_id,
):
    result = require_complete_c2_lineage(
        completed_sets,
        header_set_id=header_set_id,
        merge_set_id=merge_set_id,
    )

    summaries = {
        item["merge_set_id"]: item
        for item in completed_sets
        if item.get("header_set_id") == header_set_id
        and item.get("status") == "completed"
    }

    verified = {}
    current = merge_set_id

    while current is not None:
        if current in verified or current not in summaries:
            raise C2MergeLineageError(
                "Invalid or cyclic stored Merge Set lineage"
            )

        try:
            # Existing load() independently checks SHA-256 integrity.
            document = store.load(current)
        except Exception as exc:
            raise C2MergeLineageError(
                "Stored ancestor Merge Set could not be verified"
            ) from exc

        if not isinstance(document, dict):
            raise C2MergeLineageError(
                "Invalid stored ancestor Merge Set"
            )

        expected = {
            "workspace": workspace,
            "client": client,
            "project": project,
            "header_set_id": header_set_id,
            "merge_set_id": current,
            "status": "completed",
        }

        if any(
            document.get(key) != value
            for key, value in expected.items()
        ):
            raise C2MergeLineageError(
                "Stored ancestor identity or project scope mismatch"
            )

        summary = summaries[current]

        if (
            document.get("parent_merge_set_id") or None
        ) != (
            summary.get("parent_merge_set_id") or None
        ):
            raise C2MergeLineageError(
                "Stored parent differs from completed-set inventory"
            )

        for field in (
            "raw_record_count",
            "working_record_count",
        ):
            if document.get(field) != summary.get(field):
                raise C2MergeLineageError(
                    "Stored ancestor counts differ from inventory"
                )

        # Original first-pass Merge Sets were persisted without
        # pass_number. list_completed() represents them as pass 1.
        # Only a true root may use this legacy representation.
        # Iterative passes must retain explicit, matching numbers.
        stored_pass = document.get("pass_number")
        parent_id = document.get("parent_merge_set_id") or None

        if stored_pass is None and parent_id is None:
            stored_pass = 1

        inventory_pass = summary.get("pass_number")

        if (
            type(stored_pass) is not int
            or type(inventory_pass) is not int
            or stored_pass < 1
            or stored_pass != inventory_pass
            or (parent_id is not None and stored_pass < 2)
            or (parent_id is None and stored_pass != 1)
        ):
            raise C2MergeLineageError(
                "Stored ancestor pass number mismatch"
            )

        verified[current] = document
        current = document.get("parent_merge_set_id") or None

    if len(verified) != result["pass_count"]:
        raise C2MergeLineageError(
            "Stored Merge Set lineage is incomplete"
        )

    return {
        "stored_lineage_verified": True,
        "merge_set_id": merge_set_id,
        "header_set_id": header_set_id,
        "verified_pass_count": len(verified),
    }
