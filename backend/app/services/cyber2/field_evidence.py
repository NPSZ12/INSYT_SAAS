"""Pure field-level provenance lookup for Cyber² RAW Capture.

No cloud clients, routing, persistence, identity matching, or source mutation.
Callers must provide the RAW UCIDs belonging to an already-reviewed entity.
The output is restricted to evidence for one requested mapped field (and,
optionally, an exact normalized value) within that entity's RAW population.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


class FieldEvidenceError(ValueError):
    """Invalid or incomplete evidence linkage; fail closed rather than guess."""


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise FieldEvidenceError(f"Missing {name} in RAW evidence record")
    return result


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def find_field_evidence(
    raw_records: Iterable[Mapping[str, Any]],
    *,
    entity_raw_ucids: Iterable[str],
    field: str,
    value: str | None = None,
    field_aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select exact provenance-backed occurrences and documents for an entity.

    `entity_raw_ucids` is a trusted, previously approved entity-to-RAW linkage.
    This function NEVER decides whether two people are the same person.

    `field_aliases` maps original column names to canonical field names; it
    must come from an approved header/schema mapping, not fuzzy guesses.
    Values are compared exactly as strings after trimming whitespace; callers
    must not rely on this lookup for implicit fuzzy/value equivalence.

    RAW metadata is not changed. Sensitive values are returned to the caller
    only; an API layer must enforce access, masking, and audit requirements.
    """
    requested_field = _required(field, "field")
    selected_ucids = {_text(ucid) for ucid in entity_raw_ucids if _text(ucid)}
    aliases = dict(field_aliases or {})
    requested_value = _text(value) if value is not None else None
    occurrences: list[dict[str, Any]] = []
    seen_ucids: set[str] = set()

    for record in raw_records:
        ucid = _required(record.get("ucid"), "ucid")
        if ucid not in selected_ucids:
            continue
        if ucid in seen_ucids:
            raise FieldEvidenceError(f"Duplicate RAW UCID in supplied population: {ucid}")
        seen_ucids.add(ucid)
        doc_id = _required(record.get("doc_id"), "doc_id")
        metadata = record.get("metadata")
        provenance = record.get("provenance")
        if not isinstance(metadata, Mapping) or not isinstance(provenance, Mapping):
            raise FieldEvidenceError(f"RAW UCID {ucid} lacks metadata or provenance")

        for source_field, original_value in metadata.items():
            source_field = str(source_field)
            if source_field.upper().startswith("INSYT_") or source_field.upper() == "UCID":
                continue
            canonical_field = aliases.get(source_field, source_field)
            if canonical_field != requested_field:
                continue
            if original_value is None or isinstance(original_value, (dict, list)):
                # Unsupported cell types require an explicit adapter mapping.
                if original_value is None:
                    continue
                raise FieldEvidenceError(f"Unmapped composite value in {ucid}/{source_field}")
            original_text = _text(original_value)
            if not original_text:
                continue
            if requested_value is not None and original_text != requested_value:
                continue
            occurrences.append({
                "raw_ucid": ucid,
                "source_doc_id": doc_id,
                "source_record_id": _text(metadata.get("INSYT_Source_Record_ID") or provenance.get("source_record_id")),
                "source_field": source_field,
                "canonical_field": canonical_field,
                "original_value": original_text,
                "source_row_number": provenance.get("source_row_number"),
                "source_filename": _text(provenance.get("original_filename") or metadata.get("INSYT_Source_Filename")),
                "source_csv_path": _text(provenance.get("source_csv_path")),
                "mapped_csv_path": _text(provenance.get("mapped_csv_path")),
                "source_pointer": _text(metadata.get("INSYT_Source_Pointer") or provenance.get("source_pointer")),
            })

    # A selected UCID missing from the passed RAW collection means lookup is
    # incomplete; never claim the returned subset is exhaustive.
    missing_ucids = sorted(selected_ucids - seen_ucids)
    if missing_ucids:
        raise FieldEvidenceError(
            "Incomplete RAW evidence population; missing UCIDs: " + ", ".join(missing_ucids)
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence["source_doc_id"]].append(occurrence)

    documents = [
        {"source_doc_id": doc_id, "occurrences": docs}
        for doc_id, docs in sorted(grouped.items())
    ]
    return {
        "field": requested_field,
        "value_filter": requested_value,
        "entity_raw_record_count": len(selected_ucids),
        "matching_document_count": len(documents),
        "matching_occurrence_count": len(occurrences),
        "documents": documents,
    }
