"""INSYT Cyber2 approved Header Set exact-dedupe adapter.

Pure read-only service. No storage access or RAW mutation.
The API must load trusted mapping and RAW evidence.
"""

from collections.abc import Mapping
from typing import Any

from .exact_dedupe import ExactDedupeError, preview_exact_dedupe


def preview_header_set_dedupe(
    *,
    header_set_id: str,
    approved_mapping: Mapping[str, Any],
    raw_records: list[dict[str, Any]],
    merge_index: list[str],
    conflict_headers: list[str],
) -> dict[str, Any]:

    if not isinstance(header_set_id, str) or not header_set_id.strip():
        raise ExactDedupeError("Header Set ID required")

    if not isinstance(approved_mapping, Mapping):
        raise ExactDedupeError("Approved mapping unavailable")

    if approved_mapping.get("status") != "approved":
        raise ExactDedupeError("Header mapping is not approved")

    if approved_mapping.get("header_set_id") != header_set_id:
        raise ExactDedupeError("Header Set mapping mismatch")

    headers = (
        approved_mapping.get("canonical_column_order")
        or approved_mapping.get("protocol_headers")
    )

    if not isinstance(headers, list) or not headers:
        raise ExactDedupeError("Approved protocol headers unavailable")

    if (
        any(not isinstance(h, str) or not h.strip() for h in headers)
        or len(headers) != len(set(headers))
    ):
        raise ExactDedupeError("Invalid approved protocol headers")

    documents = approved_mapping.get("documents")

    if not isinstance(documents, list) or not documents:
        raise ExactDedupeError("Approved documents unavailable")

    doc_ids = []

    for document in documents:
        if not isinstance(document, Mapping):
            raise ExactDedupeError("Invalid approved document")

        doc_id = document.get("doc_id")

        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ExactDedupeError("Approved document missing ID")

        doc_ids.append(doc_id)

    if len(doc_ids) != len(set(doc_ids)):
        raise ExactDedupeError("Duplicate approved document IDs")

    selected_docs = set(doc_ids)
    scoped_records = []

    for record in raw_records:
        if not isinstance(record, Mapping):
            raise ExactDedupeError("Malformed RAW record")

        provenance = record.get("provenance")

        if not isinstance(provenance, Mapping):
            raise ExactDedupeError("RAW provenance unavailable")

        record_set = provenance.get("header_set_id")
        doc_id = record.get("doc_id")

        if record_set == header_set_id:
            if doc_id not in selected_docs:
                raise ExactDedupeError(
                    "RAW record outside approved document membership"
                )
            scoped_records.append(record)

        elif doc_id in selected_docs:
            raise ExactDedupeError(
                "Document contains RAW records from another Header Set"
            )

    result = preview_exact_dedupe(
        scoped_records,
        set_doc_ids=doc_ids,
        approved_headers=headers,
        merge_index=merge_index,
        conflict_headers=conflict_headers,
    )

    return {
        **result,
        "header_set_id": header_set_id,
        "approved_mapping_status": "approved",
    }