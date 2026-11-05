"""Pure INSYT Cyber2 exact-match set preview.

Consumes approved protocol headers, processing-set document IDs, and
immutable RAW records. Never writes, merges memberships, or alters RAW.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


class ExactDedupeError(ValueError):
    pass


def _required_ids(values: Iterable[str], label: str) -> list[str]:
    if isinstance(values, (str, bytes)) or values is None:
        raise ExactDedupeError(f"Invalid {label}")
    result = list(values)
    if (
        not result
        or any(not isinstance(x, str) or not x.strip() for x in result)
        or len(result) != len(set(result))
    ):
        raise ExactDedupeError(f"Missing or duplicate {label}")
    return result


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ExactDedupeError("Unsupported mapped cell type")
    return value.strip()


def preview_exact_dedupe(
    raw_records: Iterable[Mapping[str, Any]],
    *,
    set_doc_ids: Iterable[str],
    approved_headers: Iterable[str],
    merge_index: Iterable[str],
    conflict_headers: Iterable[str] = (),
) -> dict[str, Any]:
    """Return proposed exact groups, never persist consolidated identities.

    Header names must be supplied by an independently verified approved
    protocol mapping. Document IDs must come from a verified processing set.
    """
    documents = _required_ids(set_doc_ids, "set document IDs")
    approved = _required_ids(approved_headers, "approved headers")
    index = _required_ids(merge_index, "Merge Index")
    conflicts_to_check = list(conflict_headers)

    if any(field not in approved for field in index):
        raise ExactDedupeError("Merge Index contains unapproved headers")

    if (
        len(conflicts_to_check) != len(set(conflicts_to_check))
        or any(field not in approved for field in conflicts_to_check)
    ):
        raise ExactDedupeError("Invalid or unapproved conflict headers")

    selected_docs = set(documents)
    seen_ucids: set[str] = set()
    observed_docs: set[str] = set()
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    excluded: list[dict[str, str]] = []
    selected_metadata: dict[str, Mapping[str, Any]] = {}

    for record in raw_records:
        if not isinstance(record, Mapping):
            raise ExactDedupeError("Malformed RAW population")

        doc_id = record.get("doc_id")
        if doc_id not in selected_docs:
            continue

        ucid = record.get("ucid")
        metadata = record.get("metadata")
        provenance = record.get("provenance")

        if not isinstance(ucid, str) or not ucid.strip():
            raise ExactDedupeError("Selected RAW record lacks UCID")
        if ucid in seen_ucids:
            raise ExactDedupeError("Duplicate RAW UCID")
        if not isinstance(metadata, Mapping) or not isinstance(provenance, Mapping):
            raise ExactDedupeError("Selected RAW record lacks metadata or provenance")

        seen_ucids.add(ucid)
        observed_docs.add(doc_id)
        selected_metadata[ucid] = metadata

        member = {"ucid": ucid, "doc_id": doc_id}
        key = tuple(_cell(metadata.get(field)) for field in index)

        if any(not value for value in key):
            excluded.append({**member, "reason": "missing_merge_index_value"})
            continue

        # Exact means exact mapped text after edge-whitespace trimming.
        # No fuzzy, nicknames, or implicit case/date/address transformations.
        groups[key].append(member)

    if observed_docs != selected_docs:
        raise ExactDedupeError("Processing set has missing RAW source documents")

    duplicates = []
    singles = []
    conflicts = []

    for members in groups.values():
        if len(members) <= 1:
            singles.extend(members)
            continue

        flagged_fields = []

        for field in conflicts_to_check:
            values = [
                _cell(selected_metadata[item["ucid"]].get(field))
                for item in members
            ]
            nonblank = {value for value in values if value}

            if len(nonblank) > 1:
                flagged_fields.append(field)
            elif nonblank and any(not value for value in values):
                flagged_fields.append(field)

        if flagged_fields:
            conflicts.append({
                "member_count": len(members),
                "members": members,
                "conflict_fields": flagged_fields,
                "reason": "conflicting_or_incomplete_evidence",
            })
        else:
            duplicates.append({
                "member_count": len(members),
                "members": members,
            })

    return {
        "mode": "exact_preview",
        "merge_index": index,
        "document_count": len(documents),
        "raw_record_count": len(seen_ucids),
        "duplicate_group_count": len(duplicates),
        "duplicate_record_count": sum(
            group["member_count"] for group in duplicates
        ),
        "working_record_count": (
            len(duplicates)
            + len(singles)
            + len(excluded)
            + sum(group["member_count"] for group in conflicts)
        ),
        "conflict_group_count": len(conflicts),
        "groups": duplicates,
        "conflicts": conflicts,
        "unmatched": singles,
        "excluded": excluded,
    }