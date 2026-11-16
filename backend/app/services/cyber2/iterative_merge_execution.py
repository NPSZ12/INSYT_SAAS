"""Pure Cyber2 iterative merge-set execution.

Derives an immutable child population from a completed parent.
No Azure, RAW, membership, or storage operations.
"""

from copy import deepcopy
import re

from app.services.cyber2.iterative_merge_input import (
    IterativeMergeInputError,
)
from app.services.cyber2.iterative_merge_preview import (
    preview_iterative_merge,
)
from app.services.cyber2.merge_execution import _combine


def build_iterative_child(parent, merge_index, conflict_headers):
    if not isinstance(parent, dict):
        raise IterativeMergeInputError("Invalid parent")

    parent_id = parent.get("merge_set_id")

    if not isinstance(parent_id, str) or not re.fullmatch(
        r"MSET-[0-9A-F]{32}", parent_id
    ):
        raise IterativeMergeInputError("Invalid parent Merge Set ID")

    previous_pass = parent.get("pass_number", 1)

    if (
        type(previous_pass) is not int
        or previous_pass < 1
        or previous_pass >= 1000
    ):
        raise IterativeMergeInputError("Invalid parent pass number")

    # Recalculate server-side from the immutable parent.
    preview = preview_iterative_merge(
        parent, merge_index, conflict_headers
    )

    source_records = {
        row["working_record_id"]: row
        for row in parent["working_records"]
    }

    headers = list(parent["approved_headers"])
    assigned = set()
    results = []

    def append_group(members, classification, merge):
        ids = [item["working_record_id"] for item in members]

        if (
            not ids
            or len(ids) != len(set(ids))
            or any(
                identifier not in source_records or
                identifier in assigned
                for identifier in ids
            )
        ):
            raise IterativeMergeInputError(
                "Repeated or invalid parent working record"
            )

        assigned.update(ids)

        if merge:
            if len(ids) < 2:
                raise IterativeMergeInputError(
                    "Merge requires multiple parent working records"
                )

            originals = [source_records[key] for key in ids]

            ucids = []
            documents = []
            cells = {}
            provenance = {}

            for row in originals:
                ucids.extend(row["source_ucids"])

                for doc_id in row["source_doc_ids"]:
                    if doc_id not in documents:
                        documents.append(doc_id)

            for field in headers:
                lineage = []

                for row in originals:
                    lineage.extend(
                        deepcopy(row["field_provenance"][field])
                    )

                provenance[field] = lineage

                # Original source values are authoritative.
                # Never parse a semicolon-concatenated display cell
                # back into identifiers.
                cells[field] = _combine([
                    entry.get("original_value")
                    for entry in lineage
                ])

            results.append({
                "working_record_id": "",
                "classification": "exact_merged",
                "source_ucids": ucids,
                "source_doc_ids": documents,
                "cells": cells,
                "field_provenance": provenance,
            })
        else:
            for identifier in ids:
                copy = deepcopy(source_records[identifier])
                copy["classification"] = classification
                results.append(copy)

    for group in preview["groups"]:
        append_group(group["members"], "exact_merged", True)

    for group in preview["conflicts"]:
        append_group(group["members"], "qc_conflict", False)

    for item in preview["unmatched"]:
        append_group([item], "unmatched", False)

    for item in preview["excluded"]:
        append_group([item], "excluded", False)

    if assigned != set(source_records):
        raise IterativeMergeInputError(
            "Incomplete parent working population"
        )

    # IDs are scoped to the new child snapshot, not globally.
    for number, record in enumerate(results, start=1):
        record["working_record_id"] = f"WORK-{number:06d}"

    source_ucids = [
        ucid
        for record in results
        for ucid in record["source_ucids"]
    ]

    if (
        len(source_ucids) != len(set(source_ucids))
        or len(source_ucids) != parent["raw_record_count"]
        or len(results) != preview["projected_working_record_count"]
    ):
        raise IterativeMergeInputError(
            "Child source population conservation failed"
        )

    return {
        "status": "derived_not_persisted",
        "header_set_id": parent["header_set_id"],
        "parent_merge_set_id": parent_id,
        "pass_number": previous_pass + 1,
        "merge_index": list(merge_index),
        "approved_headers": headers,
        "raw_record_count": len(source_ucids),
        "input_working_record_count": len(source_records),
        "working_record_count": len(results),
        "merged_group_count": preview["duplicate_group_count"],
        "conflict_group_count": preview["conflict_group_count"],
        "working_records": results,
    }
