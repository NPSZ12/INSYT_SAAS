"""Read approved Cyber2 Mapped CSVs directly for Merge & Dedupe.

Does not generate or modify RAW Capture.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def _validated_native_json_pointers(
    document: dict[str, Any],
    approved_document: dict[str, Any],
    row_count: int,
) -> list[str] | None:
    """Verify manifest JSON pointers against approved source identity.

    Ordinary CSV documents retain their existing provenance.
    """
    approved_kind = approved_document.get("source_kind")
    manifest_kind = document.get("source_kind")

    if approved_kind != "native_json":
        _require(
            manifest_kind != "native_json",
            "Unapproved native JSON provenance",
        )
        return None

    _require(
        manifest_kind == "native_json",
        "Native JSON manifest source kind mismatch",
    )

    for key in ("source_native_path", "source_sha256"):
        value = approved_document.get(key)
        _require(
            isinstance(value, str)
            and bool(value)
            and document.get(key) == value,
            "Native JSON source identity mismatch",
        )

    _require(
        re.fullmatch(
            r"[0-9a-fA-F]{64}",
            document["source_sha256"],
        ) is not None,
        "Invalid native JSON source hash",
    )

    _require(
        "record_array_path" in document,
        "Native JSON record boundary is missing",
    )

    boundary = document["record_array_path"]
    pointers = document.get("row_source_pointers")

    _require(
        boundary is None
        or (
            isinstance(boundary, str)
            and boundary.startswith("/")
            and boundary != "/"
            and not boundary.endswith("/")
        ),
        "Native JSON record boundary is invalid",
    )

    _require(
        isinstance(pointers, list)
        and len(pointers) == row_count,
        "Native JSON row pointer count mismatch",
    )

    # Root record structures retain the existing converter's
    # sequential source pointers. Do not accept mixed prefixes.

    if boundary is None:
        source_format = approved_document.get("source_format")

        _require(
            source_format in {"json", "jsonl", "ndjson"}
            and document.get("source_format") == source_format,
            "Native JSON source format mismatch",
        )

        prefix = ""

        if (
            source_format == "json"
            and pointers
            and pointers[0] == "/records/0"
        ):
            prefix = "/records"

    else:
        prefix = boundary

        # Preserve existing single-parent record pointers.
        if all(
            isinstance(pointer, str)
            and pointer == f"{boundary}/{index}"
            for index, pointer in enumerate(pointers)
        ):
            return pointers

        # Multi-parent record pointers produced by the
        # existing native JSON converter.
        source_format = approved_document.get("source_format")

        _require(
            source_format in {"json", "jsonl", "ndjson"}
            and document.get("source_format") == source_format,
            "Native JSON source format mismatch",
        )

        pattern = re.compile(
            r"(/records)?/(0|[1-9][0-9]*)"
            + re.escape(boundary)
            + r"/(0|[1-9][0-9]*)"
        )

        previous_parent = -1
        previous_child = -1
        container_prefix = None

        for pointer in pointers:
            _require(
                isinstance(pointer, str),
                "Invalid native JSON row pointer",
            )

            match = pattern.fullmatch(pointer)

            _require(
                match is not None,
                "Native JSON row pointer mismatch",
            )

            current_prefix = match.group(1) or ""

            _require(
                not current_prefix or source_format == "json",
                "Native JSON container prefix mismatch",
            )

            if container_prefix is None:
                container_prefix = current_prefix

            _require(
                container_prefix == current_prefix,
                "Mixed native JSON container prefixes",
            )

            parent = int(match.group(2))
            child = int(match.group(3))

            if parent == previous_parent:
                _require(
                    child == previous_child + 1,
                    "Native JSON child record order mismatch",
                )
            else:
                _require(
                    parent > previous_parent and child == 0,
                    "Native JSON parent record order mismatch",
                )

            previous_parent = parent
            previous_child = child

        return pointers

    for index, pointer in enumerate(pointers):
        _require(
            isinstance(pointer, str)
            and pointer == f"{prefix}/{index}",
            "Native JSON row pointer mismatch",
        )

    return pointers


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

    approved_by_id = {
        str(doc["doc_id"]): doc for doc in approved_docs
    }

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
        approved_document = approved_by_id[doc_id]

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

        native_pointers = _validated_native_json_pointers(
            document,
            approved_document,
            len(data_rows),
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
                    **({
                        "source_kind": "native_json",
                        "source_native_path": document["source_native_path"],
                        "source_sha256": document["source_sha256"],
                        "record_array_path": document["record_array_path"],
                        "native_record_pointer": native_pointers[data_index],
                    } if native_pointers is not None else {}),
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
