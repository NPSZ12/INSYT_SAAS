"""Pure C2 projection of an already verified completed Merge Set.

The caller must perform authenticated project authorization,
Cyber2MergeSetStore.load(), source conservation, and trusted
origin authorization before invoking this builder.

This module never reads or writes Azure or Capture records.
"""

from copy import deepcopy


class C2ProjectionError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise C2ProjectionError(message)


def build_c2_projection(
    merge_set,
    approved_mapping,
    conservation_result,
    origin_result,
):
    """Build display rows and lossless provenance payload."""
    _require(
        isinstance(merge_set, dict)
        and isinstance(approved_mapping, dict)
        and isinstance(conservation_result, dict)
        and isinstance(origin_result, dict),
        "Invalid C2 projection input",
    )

    _require(
        merge_set.get("status") == "completed"
        and approved_mapping.get("status") == "approved",
        "Completed Merge Set and approved mapping required",
    )

    for key in ("workspace", "client", "project", "header_set_id"):
        _require(
            isinstance(merge_set.get(key), str)
            and bool(merge_set[key])
            and merge_set[key] == approved_mapping.get(key),
            "C2 project or Header Set scope mismatch",
        )

    merge_id = merge_set.get("merge_set_id")
    header_id = merge_set["header_set_id"]

    _require(
        isinstance(merge_id, str) and bool(merge_id),
        "Missing Merge Set identity",
    )

    _require(
        conservation_result.get("source_conservation_verified") is True
        and conservation_result.get("header_set_id") == header_id
        and conservation_result.get("working_record_count")
            == merge_set.get("working_record_count")
        and conservation_result.get("original_source_record_count")
            == merge_set.get("raw_record_count"),
        "Source conservation not established",
    )

    _require(
        origin_result.get("origin_authorized") is True
        and origin_result.get("merge_set_id") == merge_id
        and origin_result.get("header_set_id") == header_id,
        "C2 origin authorization not established",
    )

    protocol_headers = approved_mapping.get("protocol_headers")
    working_headers = merge_set.get("approved_headers")
    working = merge_set.get("working_records")

    _require(
        isinstance(protocol_headers, list)
        and bool(protocol_headers)
        and all(isinstance(h, str) and h for h in protocol_headers)
        and len(set(protocol_headers)) == len(protocol_headers),
        "Invalid approved Project Protocol",
    )

    _require(
        isinstance(working_headers, list)
        and bool(working_headers)
        and all(isinstance(h, str) and h for h in working_headers)
        and len(set(working_headers)) == len(working_headers),
        "Invalid Merge Set working schema",
    )

    _require(
        isinstance(working, list)
        and bool(working)
        and len(working) == merge_set.get("working_record_count"),
        "Invalid Merge Set working population",
    )

    display = []
    retained = []
    seen_ids = set()
    seen_ucids = set()

    for record in working:
        _require(isinstance(record, dict), "Invalid working record")

        working_id = record.get("working_record_id")
        cells = record.get("cells")
        field_provenance = record.get("field_provenance")
        source_ucids = record.get("source_ucids")
        source_docs = record.get("source_doc_ids")

        _require(
            isinstance(working_id, str)
            and bool(working_id)
            and working_id not in seen_ids,
            "Invalid or duplicate working identity",
        )

        _require(
            isinstance(cells, dict)
            and isinstance(field_provenance, dict)
            and set(cells) == set(working_headers)
            and set(field_provenance) == set(working_headers),
            "Incomplete Merge Set working fields",
        )

        _require(
            isinstance(source_ucids, list)
            and bool(source_ucids)
            and all(isinstance(u, str) and u for u in source_ucids)
            and len(source_ucids) == len(set(source_ucids))
            and not any(u in seen_ucids for u in source_ucids),
            "Duplicate or missing source UCID",
        )

        _require(
            isinstance(source_docs, list)
            and bool(source_docs)
            and all(isinstance(d, str) and d for d in source_docs),
            "Missing original source documents",
        )

        seen_ids.add(working_id)
        seen_ucids.update(source_ucids)

        c2_id = f"{merge_id}:{working_id}"

        row = {
            "id": c2_id,
            "Doc ID": "; ".join(source_docs),
        }

        for header in protocol_headers:
            value = cells.get(header, "")
            row[header] = "" if value is None else str(value)

        display.append(row)

        retained.append({
            "c2_record_id": c2_id,
            "merge_set_id": merge_id,
            "working_record_id": working_id,
            "classification": record.get("classification"),
            "source_ucids": deepcopy(source_ucids),
            "source_doc_ids": deepcopy(source_docs),
            "cells": deepcopy(cells),
            "field_provenance": deepcopy(field_provenance),
        })

    _require(
        len(seen_ucids) == merge_set.get("raw_record_count"),
        "C2 projection source count mismatch",
    )

    return {
        "schema_version": 1,
        "workspace": merge_set["workspace"],
        "client": merge_set["client"],
        "project": merge_set["project"],
        "merge_set_id": merge_id,
        "merge_integrity_sha256": merge_set["integrity_sha256"],
        "header_set_id": header_id,
        "headers": ["Doc ID"] + [
            h for h in protocol_headers if h != "Doc ID"
        ],
        "working_record_count": len(retained),
        "original_source_record_count": len(seen_ucids),
        "rows": display,
        "records": retained,
    }
