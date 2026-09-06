from __future__ import annotations

import csv
import io

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.cyber_utility import (
    get_protocol_header_library,
)

from app.api.workspace_protocols import (
    get_live_source_container_client,
)

from app.api.processing_center_azure import (
    _get_live_source_blob_service_client,
    _live_source_container,
    _project_base_path,
    _read_processing_json_blob,
    _read_review_blob_bytes,
    _review_container,
    _utc_now,
    _write_processing_json_blob,
)

from app.services.cyber2.header_analysis import (
    analyze_csv_rows,
)
from app.services.ai.header_resolver import (
    resolve_header_with_ai,
    should_invoke_ai,
)


router = APIRouter(
    prefix="/api",
    tags=["cyber2-header-identification"],
)


def _header_set_manifest_path(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
) -> str:

    base_path = (
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    return (
        f"{base_path}/cyber2/"
        f"header_sets/"
        f"{header_set_id}.json"
    )


def _header_identification_path(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
) -> str:

    base_path = (
        _project_base_path(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    return (
        f"{base_path}/cyber2/"
        f"header_mapping/"
        f"{header_set_id}/"
        f"identification.json"
    )


def _decode_csv_bytes(
    data: bytes,
) -> str:

    if not data:
        return ""

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:
        try:
            return data.decode(
                encoding
            )
        except UnicodeDecodeError:
            continue

    return data.decode(
        "utf-8",
        errors="replace",
    )


def _detect_delimiter(
    text: str,
) -> str:

    sample = (
        text[:65536]
        if text
        else ""
    )

    if not sample:
        return ","

    try:
        dialect = (
            csv.Sniffer().sniff(
                sample,
                delimiters=[
                    ",",
                    "\t",
                    ";",
                    "|",
                ],
            )
        )

        delimiter = str(
            dialect.delimiter
            or ","
        )

        return delimiter

    except Exception:
        return ","


def _read_csv_rows(
    data: bytes,
    *,
    max_rows: int = 100,
) -> dict[str, Any]:

    text = (
        _decode_csv_bytes(
            data
        )
    )

    delimiter = (
        _detect_delimiter(
            text
        )
    )

    rows: list[
        list[str]
    ] = []

    reader = csv.reader(
        io.StringIO(
            text
        ),
        delimiter=delimiter,
    )

    for row in reader:
        rows.append(
            [
                str(
                    value
                    if value is not None
                    else ""
                ).strip()
                for value in row
            ]
        )

        if len(rows) >= max_rows:
            break

    return {
        "delimiter": delimiter,
        "rows": rows,
        "sample_row_count": len(
            rows
        ),
    }


def _load_protocol_library(
    *,
    workspace: str,
    client: str,
    project: str,
) -> dict[str, Any]:

    container = (
        get_live_source_container_client(
            workspace
        )
    )

    library, source_blob = (
        get_protocol_header_library(
            container=container,
            workspace=workspace,
            project=project,
            client=client,
        )
    )

    return {
        "library": (
            library
            if isinstance(
                library,
                dict,
            )
            else {}
        ),
        "source_blob": (
            source_blob
            or ""
        ),
    }


def _load_header_set(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
) -> dict[str, Any]:

    manifest_path = (
        _header_set_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    try:
        manifest = (
            _read_processing_json_blob(
                manifest_path
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Header Set not found: "
                f"{header_set_id}"
            ),
        ) from exc

    if not isinstance(
        manifest,
        dict,
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "Header Set manifest is invalid."
            ),
        )

    return manifest


@router.get(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}"
)
def get_cyber2_header_set(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    manifest = (
        _load_header_set(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    identification_path = (
        _header_identification_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    identification = None

    try:
        identification = (
            _read_processing_json_blob(
                identification_path
            )
        )

    except Exception:
        identification = None

    return {
        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "manifest": (
            manifest
        ),

        "identification": (
            identification
        ),

        "identification_exists": (
            isinstance(
                identification,
                dict,
            )
        ),

        "identification_path": (
            identification_path
        ),
    }


@router.post(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}/identify"
)
def identify_cyber2_header_set(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    header_set_id = str(
        header_set_id
        or ""
    ).strip()

    if not header_set_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "header_set_id is required."
            ),
        )

    manifest = (
        _load_header_set(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    manifest_documents = (
        manifest.get(
            "documents"
        )
        or []
    )

    if not isinstance(
        manifest_documents,
        list,
    ):
        manifest_documents = []

    if not manifest_documents:
        raise HTTPException(
            status_code=400,
            detail=(
                "Header Set contains no CSV documents."
            ),
        )

    protocol = (
        _load_protocol_library(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    protocol_library = (
        protocol.get(
            "library"
        )
        or {}
    )

    protocol_headers = list(
        protocol_library.keys()
    )

    if not protocol_headers:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "No Project Protocol headers "
                    "are available for Header "
                    "Identification."
                ),
                "client": client,
                "project": project,
                "workspace": workspace,
            },
        )

    analyzed_documents: list[
        dict[str, Any]
    ] = []

    header_count = 0
    no_header_count = 0
    needs_review_count = 0

    review_container_name = (
        _review_container(
            workspace
        )
    )

    for document in (
        manifest_documents
    ):
        if not isinstance(
            document,
            dict,
        ):
            continue

        doc_id = str(
            document.get(
                "doc_id"
            )
            or ""
        ).strip()

        source_csv_path = str(
            document.get(
                "source_csv_path"
            )
            or ""
        ).strip()

        if (
            not doc_id
            or not source_csv_path
        ):
            analyzed_documents.append(
                {
                    **document,

                    "identification_status": (
                        "ERROR"
                    ),

                    "identification_error": (
                        "Missing Doc ID or "
                        "source CSV path."
                    ),
                }
            )

            continue

        csv_bytes = (
            _read_review_blob_bytes(
                container_name=(
                    review_container_name
                ),
                blob_path=(
                    source_csv_path
                ),
            )
        )

        if csv_bytes is None:
            analyzed_documents.append(
                {
                    **document,

                    "identification_status": (
                        "ERROR"
                    ),

                    "identification_error": (
                        "Referenced staged CSV "
                        "could not be read."
                    ),
                }
            )

            continue

        parsed = (
            _read_csv_rows(
                csv_bytes,
                max_rows=100,
            )
        )

        analysis = (
            analyze_csv_rows(
                rows=(
                    parsed.get(
                        "rows"
                    )
                    or []
                ),

                protocol_library=(
                    protocol_library
                ),
            )
        )

        header_presence = (
            analysis.get(
                "header_presence"
            )
            or {}
        )

        header_status = str(
            header_presence.get(
                "status"
            )
            or "NEEDS_REVIEW"
        ).upper()

        if header_status == "HEADER":
            header_count += 1

        elif (
            header_status
            == "NO_HEADER"
        ):
            no_header_count += 1

        else:
            needs_review_count += 1
            
        analyzed_columns = (
            analysis.get(
                "columns"
            )
            or []
        )

        ai_review_column_count = 0

        for column in analyzed_columns:
            if not isinstance(
                column,
                dict,
            ):
                continue

            mapping_confidence = float(
                column.get(
                    "mapping_confidence"
                )
                or 0.0
            )

            matched = bool(
                column.get(
                    "matched"
                )
            )

            ai_review_required = (
                should_invoke_ai(
                    mapping_confidence=(
                        mapping_confidence
                    ),
                    matched=matched,
                )
            )

            column[
                "ai_review_required"
            ] = ai_review_required

            if ai_review_required:
                ai_review_column_count += 1

                ai_result = (
                    resolve_header_with_ai(
                        source_header=str(
                            column.get(
                                "source_header"
                            )
                            or ""
                        ),
                        sample_values=[
                            str(value)
                            for value in (
                                column.get(
                                    "sample_values"
                                )
                                or []
                            )
                        ],
                        semantic_type=str(
                            column.get(
                                "semantic_type"
                            )
                            or ""
                        ),
                        deterministic_recommendation=str(
                            column.get(
                                "recommended_protocol_header"
                            )
                            or ""
                        ),
                        deterministic_confidence=(
                            mapping_confidence
                        ),
                        protocol_headers=(
                            protocol_headers
                        ),
                    )
                )

                column.update(
                    ai_result
                )

                ai_recommendation = str(
                    ai_result.get(
                        "ai_recommendation"
                    )
                    or ""
                ).strip()

                ai_confidence = (
                    ai_result.get(
                        "ai_confidence"
                    )
                )

                if (
                    ai_recommendation
                    and ai_confidence is not None
                    and float(
                        ai_confidence
                    ) >= 0.70
                ):
                    column[
                        "recommended_protocol_header"
                    ] = (
                        ai_recommendation
                    )

                    column[
                        "mapping_confidence"
                    ] = float(
                        ai_confidence
                    )

                    column[
                        "matched"
                    ] = True

                    column[
                        "match_method"
                    ] = (
                        "ai_assisted"
                    )

            else:
                column[
                    "ai_invoked"
                ] = False

                column[
                    "ai_status"
                ] = "not_required"

                column[
                    "ai_recommendation"
                ] = ""

                column[
                    "ai_confidence"
                ] = None

        analyzed_documents.append(
            {
                **document,

                "identification_status": (
                    "COMPLETED"
                ),

                "delimiter": (
                    parsed.get(
                        "delimiter"
                    )
                    or ","
                ),

                "sample_row_count": (
                    parsed.get(
                        "sample_row_count"
                    )
                    or 0
                ),

                "header_presence": (
                    header_presence
                ),

                "header_status": (
                    header_status
                ),

                "header_confidence": (
                    header_presence.get(
                        "confidence"
                    )
                ),

                "column_count": (
                    analysis.get(
                        "column_count"
                    )
                    or 0
                ),

                "matched_column_count": (
                    analysis.get(
                        "matched_column_count"
                    )
                    or 0
                ),

                "unmatched_column_count": (
                    analysis.get(
                        "unmatched_column_count"
                    )
                    or 0
                ),

                "ai_review_column_count": (
                    ai_review_column_count
                ),

                "columns": (
                    analyzed_columns
                ),
            }
        )

    completed_count = sum(
        1
        for document
        in analyzed_documents
        if document.get(
            "identification_status"
        )
        == "COMPLETED"
    )

    error_count = sum(
        1
        for document
        in analyzed_documents
        if document.get(
            "identification_status"
        )
        == "ERROR"
    )

    identification_path = (
        _header_identification_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    identified_at = (
        _utc_now()
    )

    identification_payload = {
        "schema_version": 1,

        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "status": (
            "completed"
            if error_count == 0
            else "completed_with_errors"
        ),

        "analysis_engine": (
            "insyt_header_analysis_v1"
        ),

        "analysis_mode": (
            "deterministic_semantic_protocol"
        ),

        "ai_status": (
            "completed_with_errors"
            if any(
                str(
                    column.get(
                        "ai_status"
                    )
                    or ""
                ).strip().lower()
                == "error"
                for document
                in analyzed_documents
                if isinstance(
                    document,
                    dict,
                )
                for column
                in (
                    document.get(
                        "columns"
                    )
                    or []
                )
                if isinstance(
                    column,
                    dict,
                )
            )
            else (
                "completed"
                if any(
                    bool(
                        column.get(
                            "ai_invoked"
                        )
                    )
                    for document
                    in analyzed_documents
                    if isinstance(
                        document,
                        dict,
                    )
                    for column
                    in (
                        document.get(
                            "columns"
                        )
                        or []
                    )
                    if isinstance(
                        column,
                        dict,
                    )
                )
                else (
                    "provider_not_configured"
                    if any(
                        str(
                            column.get(
                                "ai_status"
                            )
                            or ""
                        ).strip().lower()
                        == "provider_not_configured"
                        for document
                        in analyzed_documents
                        if isinstance(
                            document,
                            dict,
                        )
                        for column
                        in (
                            document.get(
                                "columns"
                            )
                            or []
                        )
                        if isinstance(
                            column,
                            dict,
                        )
                    )
                    else (
                        "disabled"
                        if any(
                            str(
                                column.get(
                                    "ai_status"
                                )
                                or ""
                            ).strip().lower()
                            == "disabled"
                            for document
                            in analyzed_documents
                            if isinstance(
                                document,
                                dict,
                            )
                            for column
                            in (
                                document.get(
                                    "columns"
                                )
                                or []
                            )
                            if isinstance(
                                column,
                                dict,
                            )
                        )
                        else "not_required"
                    )
                )
            )
        ),

        "identified_at": (
            identified_at
        ),

        "protocol_header_source": (
            protocol.get(
                "source_blob"
            )
            or ""
        ),

        "protocol_headers": (
            protocol_headers
        ),

        "protocol_header_count": (
            len(
                protocol_headers
            )
        ),

        "document_count": len(
            analyzed_documents
        ),

        "completed_document_count": (
            completed_count
        ),

        "error_document_count": (
            error_count
        ),

        "header_presence_counts": {
            "headers_in_row_1": (
                header_count
            ),

            "no_headers_in_row_1": (
                no_header_count
            ),

            "needs_review": (
                needs_review_count
            ),
        },

        "documents": (
            analyzed_documents
        ),

        "identification_path": (
            identification_path
        ),
    }

    _write_processing_json_blob(
        blob_path=(
            identification_path
        ),
        payload=(
            identification_payload
        ),
        overwrite=True,
    )

    #
    # Update only Header Set processing metadata.
    # CSV references themselves remain unchanged.
    #
    manifest["status"] = (
        "header_identification_complete"
        if error_count == 0
        else "header_identification_complete_with_errors"
    )

    manifest[
        "header_identification_at"
    ] = identified_at

    manifest[
        "header_identification_path"
    ] = identification_path

    manifest[
        "header_presence_counts"
    ] = (
        identification_payload[
            "header_presence_counts"
        ]
    )

    manifest[
        "protocol_header_source"
    ] = (
        protocol.get(
            "source_blob"
        )
        or ""
    )

    manifest_path = (
        _header_set_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    _write_processing_json_blob(
        blob_path=(
            manifest_path
        ),
        payload=manifest,
        overwrite=True,
    )

    return {
        "status": (
            identification_payload[
                "status"
            ]
        ),

        "message": (
            f"Header Identification "
            f"completed for "
            f"{completed_count} CSV(s)."
        ),

        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "identification_path": (
            identification_path
        ),

        "protocol_header_source": (
            protocol.get(
                "source_blob"
            )
            or ""
        ),

        "protocol_header_count": (
            len(
                protocol_headers
            )
        ),

        "document_count": len(
            analyzed_documents
        ),

        "completed_document_count": (
            completed_count
        ),

        "error_document_count": (
            error_count
        ),

        "header_presence_counts": (
            identification_payload[
                "header_presence_counts"
            ]
        ),

        "documents": (
            analyzed_documents
        ),
    }