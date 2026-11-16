"""Read-only resolution of C2 record source membership.

The caller supplies identities, never a storage path.
The approved mapping supplies the path after verification.
"""


class C2SourceResolutionError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise C2SourceResolutionError(message)


def resolve_c2_source_document(
    snapshot,
    mapping,
    *,
    record_id,
    doc_id,
):
    _require(isinstance(snapshot, dict), "Invalid C2 snapshot")
    _require(
        snapshot.get("status") == "transferred",
        "C2 source is not transferred",
    )
    _require(
        isinstance(record_id, str) and bool(record_id)
        and isinstance(doc_id, str) and bool(doc_id),
        "Invalid source identity",
    )

    projection = snapshot.get("projection")
    _require(
        isinstance(projection, dict)
        and isinstance(projection.get("records"), list),
        "C2 source membership unavailable",
    )

    records = [
        record for record in projection["records"]
        if isinstance(record, dict)
        and record.get("c2_record_id") == record_id
    ]
    _require(len(records) == 1, "C2 record not found or ambiguous")

    record = records[0]
    _require(
        record.get("merge_set_id") == snapshot.get("merge_set_id"),
        "C2 record transfer binding mismatch",
    )

    doc_ids = record.get("source_doc_ids")
    _require(
        isinstance(doc_ids, list)
        and bool(doc_ids)
        and all(isinstance(value, str) and value for value in doc_ids)
        and len(set(doc_ids)) == len(doc_ids),
        "Invalid source Doc ID membership",
    )
    _require(doc_id in doc_ids, "Doc ID not in selected C2 record")

    _require(
        isinstance(mapping, dict)
        and mapping.get("status") == "approved"
        and isinstance(mapping.get("documents"), list),
        "Approved source mapping unavailable",
    )

    matched = [
        item for item in mapping["documents"]
        if isinstance(item, dict)
        and item.get("doc_id") == doc_id
    ]
    _require(len(matched) == 1, "Approved source Doc ID is ambiguous")

    source_path = matched[0].get("source_csv_path")
    _require(
        isinstance(source_path, str)
        and bool(source_path.strip())
        and source_path.lower().endswith(".csv"),
        "Approved CSV source path unavailable",
    )

    return {
        "record_id": record_id,
        "doc_id": doc_id,
        "doc_ids": list(doc_ids),
        "doc_index": doc_ids.index(doc_id),
        "doc_count": len(doc_ids),
        "source_path": source_path,
    }
