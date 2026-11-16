"""Validate C2 Merge Set source conservation without authorizing transfer.

This module never reads or writes Azure, RAW, or captured entities.
Capture-origin authorization is a separate mandatory gate.
"""

from collections.abc import Mapping


class C2TransferValidationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise C2TransferValidationError(message)


def validate_c2_merge_population(
    merge_set,
    mapped_records,
    *,
    workspace,
    client,
    project,
):
    """Audit a completed Merge Set against verified mapped CSV records.

    Returns counts only; does not authorize or perform C2 transfer.
    """
    _require(isinstance(merge_set, dict), "Invalid Merge Set")
    _require(isinstance(mapped_records, list), "Invalid source population")

    scope = {
        "workspace": workspace,
        "client": client,
        "project": project,
    }
    _require(
        all(merge_set.get(k) == v for k, v in scope.items()),
        "Merge Set project scope mismatch",
    )
    _require(
        merge_set.get("status") == "completed",
        "Completed Merge Set required",
    )
    _require(
        isinstance(merge_set.get("integrity_sha256"), str)
        and len(merge_set["integrity_sha256"]) == 64,
        "Verified Merge Set digest required",
    )

    header_set_id = merge_set.get("header_set_id")
    headers = merge_set.get("approved_headers")
    working = merge_set.get("working_records")

    _require(
        isinstance(header_set_id, str) and bool(header_set_id),
        "Missing Header Set identity",
    )
    _require(
        isinstance(headers, list) and bool(headers)
        and all(isinstance(h, str) and h for h in headers)
        and len(headers) == len(set(headers)),
        "Invalid working schema",
    )
    _require(
        isinstance(working, list) and bool(working),
        "Missing working records",
    )
    _require(
        merge_set.get("working_record_count") == len(working),
        "Working-record count mismatch",
    )
    _require(
        merge_set.get("raw_record_count") == len(mapped_records),
        "Original source count mismatch",
    )

    sources = {}
    for record in mapped_records:
        _require(isinstance(record, Mapping), "Invalid mapped source")
        ucid = record.get("ucid")
        evidence = record.get("provenance")
        metadata = record.get("metadata")

        _require(
            isinstance(ucid, str) and bool(ucid)
            and ucid not in sources,
            "Invalid or duplicate source UCID",
        )
        _require(
            isinstance(evidence, Mapping)
            and isinstance(metadata, Mapping)
            and isinstance(record.get("doc_id"), str),
            "Incomplete mapped-source evidence",
        )
        _require(
            evidence.get("header_set_id") == header_set_id,
            "Mapped-source Header Set mismatch",
        )
        _require(
            evidence.get("capture_source") == "cyber2_mapped_csv",
            "Source is not from the verified mapped-CSV route",
        )
        sources[ucid] = record

    seen = set()
    working_ids = set()

    for row in working:
        _require(isinstance(row, Mapping), "Invalid working record")

        working_id = row.get("working_record_id")
        ucids = row.get("source_ucids")
        doc_ids = row.get("source_doc_ids")
        cells = row.get("cells")
        provenance = row.get("field_provenance")

        _require(
            isinstance(working_id, str) and bool(working_id)
            and working_id not in working_ids,
            "Duplicate or invalid working identity",
        )
        working_ids.add(working_id)

        _require(
            isinstance(ucids, list) and bool(ucids)
            and len(ucids) == len(set(ucids))
            and all(u in sources and u not in seen for u in ucids),
            "Missing, repeated, or unknown source UCID",
        )
        _require(
            isinstance(cells, Mapping)
            and isinstance(provenance, Mapping)
            and set(cells) == set(headers)
            and set(provenance) == set(headers),
            "Incomplete working field schema",
        )

        expected_docs = list(dict.fromkeys(
            sources[u]["doc_id"] for u in ucids
        ))
        _require(
            doc_ids == expected_docs,
            "Working source-document membership mismatch",
        )

        for field in headers:
            lineage = provenance[field]
            _require(
                isinstance(lineage, list)
                and len(lineage) == len(ucids),
                "Field provenance count mismatch",
            )

            for ucid, item in zip(ucids, lineage):
                source = sources[ucid]
                _require(
                    isinstance(item, Mapping)
                    and item.get("ucid") == ucid
                    and item.get("doc_id") == source["doc_id"]
                    and item.get("source_row_number")
                    == source["provenance"].get("source_row_number")
                    and item.get("output_header") == field
                    and item.get("original_value")
                    == source["metadata"].get(field),
                    "Field provenance differs from mapped source",
                )

        seen.update(ucids)

    _require(
        seen == set(sources),
        "Incomplete original source conservation",
    )

    return {
        "header_set_id": header_set_id,
        "working_record_count": len(working),
        "original_source_record_count": len(sources),
        "source_conservation_verified": True,
        "capture_origin_authorized": False,
        "transfer_authorized": False,
    }
