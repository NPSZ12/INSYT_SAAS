"""Read approved Cyber2 Mapped CSVs directly for Merge & Dedupe.

Does not generate or modify RAW Capture.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class MappedProcessingSetError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MappedProcessingSetError(message)


def _unique_headers(headers: list[str]) -> bool:
    normalized = [
        " ".join(value.strip().casefold().split())
        for value in headers
    ]
    return (
        all(normalized)
        and len(normalized) == len(set(normalized))
    )


def _stable_ucid(
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
    doc_id: str,
    source_row_number: int,
) -> str:
    identity = json.dumps(
        [
            workspace,
            client,
            project,
            header_set_id,
            doc_id,
            source_row_number,
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return "C2-" + digest


def load_cyber2_mapped_processing_set(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
    approved_mapping: dict[str, Any],
) -> dict[str, Any]:
    """Load one complete, approved Header Set without RAW writes."""

    from app.api.cyber2.schema_mapping import (
        _load_required_json,
        _mapped_csv_manifest_path,
        _mapped_csv_path,
        _read_csv_blob_rows,
    )
    from app.api.processing_center_azure import (
        _processing_container_client,
    )

    _require(
        approved_mapping.get("status") == "approved",
        "Header Set mapping is not approved",
    )

    scope = {
        "workspace": workspace,
        "client": client,
        "project": project,
        "header_set_id": header_set_id,
    }

    _require(
        all(approved_mapping.get(k) == v for k, v in scope.items()),
        "Approved mapping scope mismatch",
    )

    approved_docs = approved_mapping.get("documents")

    _require(
        isinstance(approved_docs, list) and bool(approved_docs),
        "Approved Header Set has no documents",
    )

    approved_ids = [
        str(doc.get("doc_id") or "")
        for doc in approved_docs
        if isinstance(doc, dict)
    ]

    _require(
        len(approved_ids) == len(approved_docs)
        and all(approved_ids)
        and len(set(approved_ids)) == len(approved_ids),
        "Invalid approved document membership",
    )

    manifest_path = _mapped_csv_manifest_path(
        workspace=workspace,
        client=client,
        project=project,
        header_set_id=header_set_id,
    )

    manifest = _load_required_json(
        manifest_path,
        description="Completed Mapped CSV Manifest",
    )

    _require(
        isinstance(manifest, dict),
        "Mapped CSV manifest is invalid",
    )
    _require(
        manifest.get("status") == "completed",
        "Mapped CSV generation is incomplete",
    )
    _require(
        all(manifest.get(k) == v for k, v in scope.items()),
        "Mapped CSV manifest scope mismatch",
    )
    _require(
        int(manifest.get("failed_document_count", -1)) == 0,
        "Mapped CSV manifest contains failures",
    )

    documents = manifest.get("documents")

    _require(
        isinstance(documents, list),
        "Mapped CSV document inventory is invalid",
    )

    mapped_by_id = {}

    for document in documents:
        _require(
            isinstance(document, dict),
            "Invalid mapped CSV document",
        )
        doc_id = str(document.get("doc_id") or "")

        _require(
            doc_id and doc_id not in mapped_by_id,
            "Duplicate or missing mapped document ID",
        )
        mapped_by_id[doc_id] = document

    _require(
        set(mapped_by_id) == set(approved_ids),
        "Mapped CSV documents differ from approved Header Set",
    )

    _require(
        int(manifest.get("generated_document_count", -1))
        == len(approved_ids),
        "Mapped CSV generation count mismatch",
    )

    container = _processing_container_client()
    records = []
    output_headers = []
    seen_ucids = set()

    for doc_id in approved_ids:
        document = mapped_by_id[doc_id]

        expected_path = _mapped_csv_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
            doc_id=doc_id,
        )

        _require(
            document.get("mapped_csv_path") == expected_path,
            "Mapped CSV path does not match approved project",
        )

        rows, _delimiter = _read_csv_blob_rows(
            container=container,
            blob_path=expected_path,
        )

        _require(
            isinstance(rows, list) and bool(rows),
            "Mapped CSV is empty",
        )

        headers = [str(h) for h in rows[0]]

        _require(
            _unique_headers(headers),
            "Mapped CSV contains duplicate or blank headers",
        )
        _require(
            headers == document.get("output_headers"),
            "Mapped CSV headers differ from manifest",
        )

        lineage = document.get("column_lineage")

        _require(
            isinstance(lineage, list)
            and len(lineage) == len(headers),
            "Mapped CSV column lineage is incomplete",
        )

        for index, entry in enumerate(lineage):
            _require(
                isinstance(entry, dict)
                and entry.get("output_column_index") == index
                and entry.get("output_header") == headers[index]
                and isinstance(entry.get("source_column_index"), int)
                and entry["source_column_index"] >= 0,
                "Mapped CSV column lineage mismatch",
            )

        data_rows = rows[1:]

        _require(
            len(data_rows) == int(document.get("mapped_row_count", -1)),
            "Mapped CSV row count differs from manifest",
        )

        header_status = str(
            document.get("header_status") or ""
        ).upper()

        for data_index, values in enumerate(data_rows):
            _require(
                len(values) == len(headers),
                "Mapped CSV contains a row-width mismatch",
            )

            source_row_number = (
                data_index + 2
                if header_status == "HEADER"
                else data_index + 1
            )

            ucid = _stable_ucid(
                workspace,
                client,
                project,
                header_set_id,
                doc_id,
                source_row_number,
            )

            _require(
                ucid not in seen_ucids,
                "Duplicate C2 record identity",
            )
            seen_ucids.add(ucid)

            metadata = dict(zip(headers, values))

            records.append({
                "ucid": ucid,
                "doc_id": doc_id,
                "metadata": metadata,
                "provenance": {
                    "capture_source": "cyber2_mapped_csv",
                    "header_set_id": header_set_id,
                    "source_row_number": source_row_number,
                    "source_csv_path": document.get(
                        "source_csv_path", ""
                    ),
                    "mapped_csv_path": expected_path,
                    "original_filename": document.get(
                        "original_filename", ""
                    ),
                    "original_workbook_name": document.get(
                        "original_workbook_name", ""
                    ),
                    "sheet_name": document.get("sheet_name", ""),
                    "column_lineage": lineage,
                },
            })

        for header in headers:
            if header not in output_headers:
                output_headers.append(header)

    _require(
        len(records) == int(manifest.get("total_mapped_rows", -1)),
        "Mapped CSV population count mismatch",
    )

    _require(
        len(records) <= 5000,
        "Processing set exceeds current 5000-record limit",
    )

    _require(
        all(
            any(r["doc_id"] == doc_id for r in records)
            for doc_id in approved_ids
        ),
        "Processing set contains a document without records",
    )

    return {
        "records": records,
        "output_headers": output_headers,
        "record_count": len(records),
        "document_count": len(approved_ids),
        "header_set_id": header_set_id,
    }
