"""Validate immutable completed sets for another Cyber2 dedupe pass.

Pure local logic. Does not read/write Azure, RAW, or memberships.
"""

class IterativeMergeInputError(ValueError):
    pass


def prepare_iterative_candidates(parent, merge_index):
    if not isinstance(parent, dict) or parent.get("status") != "completed":
        raise IterativeMergeInputError("Completed parent merge set required")

    headers = parent.get("approved_headers")
    records = parent.get("working_records")
    index = list(merge_index)

    if (
        not isinstance(headers, list)
        or not headers
        or len(headers) != len(set(headers))
        or not isinstance(records, list)
        or not records
        or not index
        or len(index) != len(set(index))
        or not set(index).issubset(headers)
    ):
        raise IterativeMergeInputError("Invalid approved Merge Index")

    if parent.get("working_record_count") != len(records):
        raise IterativeMergeInputError("Parent record count mismatch")

    candidates = []
    excluded = []
    seen_working = set()
    seen_source = set()

    for record in records:
        if not isinstance(record, dict):
            raise IterativeMergeInputError("Invalid parent working record")

        working_id = record.get("working_record_id")
        ucids = record.get("source_ucids")
        doc_ids = record.get("source_doc_ids")
        cells = record.get("cells")
        evidence = record.get("field_provenance")

        if (
            not isinstance(working_id, str)
            or not working_id
            or working_id in seen_working
            or not isinstance(ucids, list)
            or not ucids
            or any(not isinstance(u, str) or not u for u in ucids)
            or len(ucids) != len(set(ucids))
            or not isinstance(doc_ids, list)
            or not doc_ids
            or not isinstance(cells, dict)
            or set(cells) != set(headers)
            or not isinstance(evidence, dict)
            or set(evidence) != set(headers)
        ):
            raise IterativeMergeInputError("Invalid parent identity or fields")

        if any(u in seen_source for u in ucids):
            raise IterativeMergeInputError("Repeated original source identity")

        seen_working.add(working_id)
        seen_source.update(ucids)

        for field in headers:
            lineage = evidence[field]
            if (
                not isinstance(lineage, list)
                or len(lineage) != len(ucids)
                or any(not isinstance(p, dict) for p in lineage)
                or [str(p.get("ucid")) for p in lineage] != ucids
            ):
                raise IterativeMergeInputError("Original field lineage mismatch")

        key = []
        reason = None

        for field in index:
            values = set()

            for item in evidence[field]:
                value = item.get("original_value")
                if value is None:
                    continue
                if not isinstance(value, str):
                    reason = "non_text_identifier"
                    break
                value = value.strip()
                if value:
                    values.add(value)

            if reason:
                break

            if len(values) > 1:
                reason = "multiple_identifier_values"
                break

            if not values:
                reason = "missing_identifier"
                break

            key.append(next(iter(values)))

        identity = {
            "working_record_id": working_id,
            "source_ucids": list(ucids),
            "source_doc_ids": list(doc_ids),
        }

        if reason:
            excluded.append({**identity, "reason": reason})
        else:
            candidates.append({**identity, "key": tuple(key)})

    if parent.get("raw_record_count") != len(seen_source):
        raise IterativeMergeInputError("Original source count mismatch")

    return {
        "parent_merge_set_id": parent.get("merge_set_id"),
        "header_set_id": parent.get("header_set_id"),
        "merge_index": index,
        "input_working_record_count": len(records),
        "original_source_record_count": len(seen_source),
        "candidates": candidates,
        "excluded": excluded,
    }
