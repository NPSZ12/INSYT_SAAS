"""Pure, provenance-preserving Cyber2 exact merge execution.

No Azure, database, RAW, or identity-registry writes occur here.
"""

from copy import deepcopy

from .identity_comparison import normalize_identity_comparison


class MergeExecutionError(ValueError):
    pass


def _value_key(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _combine(values):
    unique = []
    seen = set()

    for value in values:
        key = _value_key(value)
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(deepcopy(value))

    if not unique:
        return ""

    if len(unique) == 1:
        return unique[0]

    return "; ".join(
        value if isinstance(value, str) else str(value)
        for value in unique
    )


def build_merged_working_population(
    *,
    header_set_id,
    approved_headers,
    approved_doc_ids,
    merge_index,
    raw_records,
    preview,
    conflict_headers=(),
):
    """Create derived records without mutating any source population."""

    headers = list(approved_headers)
    index = list(merge_index)
    allowed_docs = set(approved_doc_ids)

    if (
        not header_set_id
        or not headers
        or len(set(headers)) != len(headers)
        or not index
        or len(set(index)) != len(index)
        or not set(index).issubset(headers)
        or not allowed_docs
    ):
        raise MergeExecutionError("Invalid approved merge configuration")

    if preview.get("header_set_id") != header_set_id:
        raise MergeExecutionError("Preview Header Set mismatch")

    if list(preview.get("merge_index", [])) != index:
        raise MergeExecutionError("Preview Merge Index mismatch")

    source = {}

    for record in raw_records:
        if not isinstance(record, dict):
            continue

        provenance = record.get("provenance") or {}

        if provenance.get("header_set_id") != header_set_id:
            continue

        doc_id = str(record.get("doc_id") or "")

        if doc_id not in allowed_docs:
            raise MergeExecutionError("Unexpected Header Set source document")

        ucid = str(record.get("ucid") or "")

        if not ucid or ucid in source:
            raise MergeExecutionError("Missing or duplicate RAW UCID")

        if not isinstance(record.get("metadata"), dict):
            raise MergeExecutionError("Invalid RAW metadata")

        source[ucid] = record

    if not source:
        raise MergeExecutionError("No RAW records for Header Set")

    units = []
    assigned = set()

    def append_unit(members, classification, *, allow_merge):
        ucids = []

        for member in members:
            ucid = str(member.get("ucid") or "")
            doc_id = str(member.get("doc_id") or "")

            if ucid not in source or ucid in assigned:
                raise MergeExecutionError("Invalid or repeated preview member")

            if str(source[ucid]["doc_id"]) != doc_id:
                raise MergeExecutionError("Preview document mismatch")

            ucids.append(ucid)
            assigned.add(ucid)

        if not ucids:
            raise MergeExecutionError("Empty preview group")

        if allow_merge:
            if len(ucids) < 2:
                raise MergeExecutionError("Exact group requires two members")

            for field in index:
                values = [
                    _value_key(source[u]["metadata"].get(field))
                    for u in ucids
                ]
                if None in values or len(set(values)) != 1:
                    raise MergeExecutionError("Merge Index values disagree")

            for field in conflict_headers:
                if field in index:
                    continue

                values = [
                    _value_key(source[u]["metadata"].get(field))
                    for u in ucids
                ]

                values = [
                    normalize_identity_comparison(field, value)
                    if value is not None else None
                    for value in values
                ]

                present = [value for value in values if value is not None]

                if len(set(present)) > 1 or (
                    present and len(present) != len(values)
                ):
                    raise MergeExecutionError(
                        "Conflicting strong identifiers prevent merge"
                    )

            units.append((ucids, "exact_merged"))
        else:
            for ucid in ucids:
                units.append(([ucid], classification))

    for group in preview.get("groups", []):
        append_unit(
            group["members"],
            "exact_merged",
            allow_merge=True,
        )

    for group in preview.get("conflicts", []):
        append_unit(
            group["members"],
            "qc_conflict",
            allow_merge=False,
        )

    append_unit(
        preview.get("unmatched", []),
        "unmatched",
        allow_merge=False,
    ) if preview.get("unmatched") else None

    append_unit(
        preview.get("excluded", []),
        "excluded",
        allow_merge=False,
    ) if preview.get("excluded") else None

    if assigned != set(source):
        raise MergeExecutionError("Incomplete preview source population")

    working = []

    for number, (ucids, classification) in enumerate(units, start=1):
        members = [source[ucid] for ucid in ucids]
        cells = {}
        field_provenance = {}

        for field in headers:
            values = []
            lineage = []

            for record in members:
                value = deepcopy(record["metadata"].get(field))
                values.append(value)

                source_provenance = record.get("provenance") or {}
                column_matches = [
                    column
                    for column in source_provenance.get(
                        "column_lineage", []
                    )
                    if isinstance(column, dict)
                    and column.get("output_header") == field
                ]

                if len(column_matches) > 1:
                    raise MergeExecutionError(
                        "Ambiguous source-column lineage"
                    )

                column_source = (
                    column_matches[0] if column_matches else {}
                )

                lineage.append({
                    "ucid": str(record["ucid"]),
                    "doc_id": str(record["doc_id"]),
                    "source_row_number": source_provenance.get(
                        "source_row_number"
                    ),
                    "source_column_index": column_source.get(
                        "source_column_index"
                    ),
                    "source_header": column_source.get(
                        "source_header"
                    ),
                    "canonical_header": column_source.get(
                        "canonical_header", field
                    ),
                    "output_header": field,
                    "original_value": value,
                })

            # Date-only DOB in derived working cells.
            # Original source values remain in field provenance.
            display_values = [
                normalize_identity_comparison(field, value)
                if isinstance(value, str) else value
                for value in values
            ]
            cells[field] = _combine(display_values)
            field_provenance[field] = lineage

        working.append({
            "working_record_id": f"WORK-{number:06d}",
            "classification": classification,
            "source_ucids": list(ucids),
            "source_doc_ids": list(dict.fromkeys(
                str(record["doc_id"]) for record in members
            )),
            "cells": cells,
            "field_provenance": field_provenance,
        })

    return {
        "status": "derived_not_persisted",
        "header_set_id": header_set_id,
        "merge_index": index,
        "approved_headers": headers,
        "raw_record_count": len(source),
        "working_record_count": len(working),
        "merged_group_count": sum(
            row["classification"] == "exact_merged"
            for row in working
        ),
        "working_records": working,
    }
