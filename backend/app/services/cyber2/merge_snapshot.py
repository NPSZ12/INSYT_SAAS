"""Cyber2 optimistic-concurrency fingerprint for exact merge previews.

The fingerprint is a change detector, not an authentication credential.
Never log the canonical payload or captured values.
"""

from __future__ import annotations

import hashlib
import json


class MergeSnapshotError(ValueError):
    pass


def merge_snapshot_fingerprint(
    *,
    approved_mapping,
    merge_index,
    raw_records,
):
    if not isinstance(approved_mapping, dict):
        raise MergeSnapshotError("Invalid approved mapping")

    if approved_mapping.get("status") != "approved":
        raise MergeSnapshotError("Mapping is not approved")

    headers = (
        approved_mapping.get("canonical_column_order")
        or approved_mapping.get("protocol_headers")
    )

    if (
        not isinstance(headers, list)
        or not headers
        or not all(isinstance(h, str) and h for h in headers)
        or len(set(headers)) != len(headers)
    ):
        raise MergeSnapshotError("Invalid approved protocol headers")

    index = list(merge_index)

    if (
        not index
        or len(set(index)) != len(index)
        or not set(index).issubset(headers)
    ):
        raise MergeSnapshotError("Invalid Merge Index")

    documents = approved_mapping.get("documents")

    if not isinstance(documents, list) or not documents:
        raise MergeSnapshotError("Missing approved documents")

    doc_ids = []

    for document in documents:
        if not isinstance(document, dict):
            raise MergeSnapshotError("Invalid approved document")

        doc_id = str(document.get("doc_id") or "")

        if not doc_id or doc_id in doc_ids:
            raise MergeSnapshotError("Duplicate or missing document")

        doc_ids.append(doc_id)

    header_set_id = str(
        approved_mapping.get("header_set_id") or ""
    )

    if not header_set_id:
        raise MergeSnapshotError("Missing Header Set")

    if not isinstance(raw_records, list):
        raise MergeSnapshotError("Invalid RAW source population")

    rows = []
    seen = set()

    for record in raw_records:
        if not isinstance(record, dict):
            raise MergeSnapshotError("Malformed RAW record")

        provenance = record.get("provenance") or {}

        if not isinstance(provenance, dict):
            raise MergeSnapshotError("Malformed provenance")

        if provenance.get("header_set_id") != header_set_id:
            continue

        ucid = str(record.get("ucid") or "")
        doc_id = str(record.get("doc_id") or "")
        metadata = record.get("metadata")

        if (
            not ucid
            or ucid in seen
            or doc_id not in doc_ids
            or not isinstance(metadata, dict)
        ):
            raise MergeSnapshotError("Invalid scoped RAW record")

        seen.add(ucid)

        rows.append({
            "ucid": ucid,
            "doc_id": doc_id,
            # Include every mapped column, including suffixed and
            # custom fields, in the optimistic-concurrency fingerprint.
            # Approved protocol headers still control the Merge Index.
            "metadata": dict(metadata),
            "provenance": provenance,
        })

    if not rows:
        raise MergeSnapshotError("No RAW records for Header Set")

    if set(doc_ids) != {row["doc_id"] for row in rows}:
        raise MergeSnapshotError("Approved document population incomplete")

    rows.sort(key=lambda item: item["ucid"])

    payload = {
        "schema_version": 1,
        "approved_mapping": approved_mapping,
        "merge_index": index,
        "raw_rows": rows,
    }

    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MergeSnapshotError(
            "RAW snapshot cannot be serialized deterministically"
        ) from exc

    return hashlib.sha256(canonical).hexdigest()
