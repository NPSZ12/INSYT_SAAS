from __future__ import annotations

import csv
import io

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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
    _utc_now,
    _write_processing_json_blob,
)

from app.services.batch_service import get_container_client


router = APIRouter(
    prefix="/api",
    tags=["cyber2-schema-mapping"],
)


class ColumnMappingDecision(BaseModel):
    column_index: int = Field(
        ...,
        ge=0,
    )

    disposition: Literal[
        "approve",
        "map",
        "keep",
        "rename",
        "delete",
    ]

    final_header: str = ""


class DocumentMappingDecision(BaseModel):
    doc_id: str

    columns: list[
        ColumnMappingDecision
    ] = []


class ApproveHeaderMappingRequest(
    BaseModel
):
    client: str
    project: str

    documents: list[
        DocumentMappingDecision
    ] = []

    approved_by: str = ""

class GenerateMappedCsvsRequest(
    BaseModel
):
    client: str
    project: str

    generated_by: str = ""

    overwrite_existing: bool = True

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


def _identification_path(
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


def _approved_mapping_path(
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
        f"approved_mapping.json"
    )

def _mapped_csv_folder_path(
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
        f"mapped_csv"
    )


def _mapped_csv_path(
    *,
    workspace: str,
    client: str,
    project: str,
    header_set_id: str,
    doc_id: str,
) -> str:

    folder_path = (
        _mapped_csv_folder_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    return (
        f"{folder_path}/"
        f"{doc_id}.csv"
    )


def _mapped_csv_manifest_path(
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
        f"mapped_csv_manifest.json"
    )

def _load_required_json(
    blob_path: str,
    *,
    description: str,
) -> dict[str, Any]:

    try:
        payload = (
            _read_processing_json_blob(
                blob_path
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{description} not found."
            ),
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                f"{description} is invalid."
            ),
        )

    return payload


def _load_protocol_library(
    *,
    workspace: str,
    client: str,
    project: str,
) -> dict[str, Any]:

    blob_service = (
        _get_live_source_blob_service_client()
    )

    container = get_container_client(workspace)

    library, source_blob = (
        get_protocol_header_library(
            container=container,
            workspace=workspace,
            project=project,
            client=client,
        )
    )

    if not isinstance(
        library,
        dict,
    ):
        library = {}

    return {
        "library": library,
        "source_blob": (
            source_blob
            or ""
        ),
    }


def _normalize_header(
    value: Any,
) -> str:

    return " ".join(
        str(
            value
            if value is not None
            else ""
        )
        .strip()
        .lower()
        .split()
    )

def _decode_csv_bytes(
    payload: bytes,
) -> str:

    if not payload:
        return ""

    try:
        return payload.decode(
            "utf-8-sig"
        )

    except UnicodeDecodeError:
        return payload.decode(
            "cp1252"
        )


def _detect_csv_delimiter(
    text: str,
) -> str:

    sample = text[:8192]

    try:
        dialect = (
            csv.Sniffer().sniff(
                sample,
                delimiters=",\t;|",
            )
        )

        delimiter = str(
            dialect.delimiter
            or ","
        )

        if delimiter:
            return delimiter

    except csv.Error:
        pass

    return ","


def _read_csv_blob_rows(
    *,
    container: Any,
    blob_path: str,
) -> tuple[list[list[str]], str]:

    blob_client = (
        container.get_blob_client(
            blob_path
        )
    )

    raw_bytes = (
        blob_client
        .download_blob()
        .readall()
    )

    text = (
        _decode_csv_bytes(
            raw_bytes
        )
    )

    delimiter = (
        _detect_csv_delimiter(
            text
        )
    )

    rows = list(
        csv.reader(
            io.StringIO(
                text
            ),
            delimiter=delimiter,
        )
    )

    return (
        rows,
        delimiter,
    )


def _write_csv_blob_rows(
    *,
    container: Any,
    blob_path: str,
    rows: list[list[Any]],
    overwrite: bool,
) -> None:

    output = (
        io.StringIO(
            newline=""
        )
    )

    writer = csv.writer(
        output,
        delimiter=",",
        lineterminator="\n",
    )

    for row in rows:
        writer.writerow(
            [
                ""
                if value is None
                else value
                for value in row
            ]
        )

    payload = (
        "\ufeff"
        + output.getvalue()
    ).encode(
        "utf-8"
    )

    blob_client = (
        container.get_blob_client(
            blob_path
        )
    )

    blob_client.upload_blob(
        payload,
        overwrite=overwrite,
    )
    
def _generate_mapped_document_rows(
    *,
    source_rows: list[list[str]],
    approved_document: dict[str, Any],
    protocol_headers: list[str],
) -> dict[str, Any]:

    header_status = str(
        approved_document.get(
            "header_status"
        )
        or ""
    ).strip().upper()

    approved_columns = (
        approved_document.get(
            "columns"
        )
        or []
    )

    if not isinstance(
        approved_columns,
        list,
    ):
        approved_columns = []

    #
    # HEADER:
    #   Row 1 is source metadata and is
    #   replaced by approved final headers.
    #
    # NO_HEADER / NEEDS_REVIEW:
    #   Row 1 remains data.
    #
    if header_status == "HEADER":
        data_rows = (
            source_rows[1:]
            if source_rows
            else []
        )

    else:
        data_rows = (
            source_rows
        )

    retained_columns: list[
        dict[str, Any]
    ] = []

    for column in approved_columns:

        if not isinstance(
            column,
            dict,
        ):
            continue

        if bool(
            column.get(
                "delete_column"
            )
        ):
            continue

        final_header = str(
            column.get(
                "final_header"
            )
            or ""
        ).strip()

        if not final_header:
            continue

        try:
            column_index = int(
                column.get(
                    "column_index"
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        retained_columns.append(
            {
                **column,
                "column_index":
                    column_index,
                "final_header":
                    final_header,
            }
        )

    #
    # Do not permit duplicate output
    # headers inside one mapped CSV.
    #
    duplicate_check: dict[
        str,
        list[int],
    ] = {}

    for column in retained_columns:

        normalized = (
            _normalize_header(
                column[
                    "final_header"
                ]
            )
        )

        duplicate_check.setdefault(
            normalized,
            [],
        ).append(
            int(
                column[
                    "column_index"
                ]
            )
        )

    duplicates = {
        key: indexes
        for key, indexes
        in duplicate_check.items()
        if key
        and len(indexes) > 1
    }

    if duplicates:
        raise ValueError(
            "Multiple source columns map "
            "to the same final output header: "
            f"{duplicates}"
        )

    protocol_order = {
        _normalize_header(
            header
        ): index
        for index, header
        in enumerate(
            protocol_headers
        )
    }

    retained_columns.sort(
        key=lambda column: (
            protocol_order.get(
                _normalize_header(
                    column[
                        "final_header"
                    ]
                ),
                1_000_000,
            ),

            int(
                column[
                    "column_index"
                ]
            ),
        )
    )

    output_headers = [
        str(
            column[
                "final_header"
            ]
        )
        for column
        in retained_columns
    ]

    output_rows: list[
        list[Any]
    ] = [
        output_headers
    ]

    for source_row in data_rows:

        output_row: list[
            Any
        ] = []

        for column in (
            retained_columns
        ):
            column_index = int(
                column[
                    "column_index"
                ]
            )

            value = (
                source_row[
                    column_index
                ]
                if column_index
                < len(
                    source_row
                )
                else ""
            )

            output_row.append(
                value
            )

        output_rows.append(
            output_row
        )

    protocol_headers_present = [
        header
        for header
        in output_headers
        if _normalize_header(
            header
        )
        in protocol_order
    ]

    custom_headers_retained = [
        header
        for header
        in output_headers
        if _normalize_header(
            header
        )
        not in protocol_order
    ]

    deleted_headers = [
        str(
            column.get(
                "source_header"
            )
            or ""
        ).strip()
        for column
        in approved_columns
        if isinstance(
            column,
            dict,
        )
        and bool(
            column.get(
                "delete_column"
            )
        )
    ]

    return {
        "rows": output_rows,

        "output_headers":
            output_headers,

        "protocol_headers_present":
            protocol_headers_present,

        "custom_headers_retained":
            custom_headers_retained,

        "deleted_headers":
            deleted_headers,

        "source_row_count": (
            len(
                data_rows
            )
        ),

        "mapped_row_count": (
            len(
                data_rows
            )
        ),

        "source_column_count": (
            max(
                (
                    len(row)
                    for row
                    in source_rows
                ),
                default=0,
            )
        ),

        "mapped_column_count": (
            len(
                output_headers
            )
        ),
    }

@router.get(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}/mapping"
)
def get_cyber2_header_mapping(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    identification_blob_path = (
        _identification_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    identification = (
        _load_required_json(
            identification_blob_path,
            description=(
                "Header Identification result"
            ),
        )
    )

    approved_blob_path = (
        _approved_mapping_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    approved_mapping = None

    try:
        approved_mapping = (
            _read_processing_json_blob(
                approved_blob_path
            )
        )

    except Exception:
        approved_mapping = None

    protocol = (
        _load_protocol_library(
            workspace=workspace,
            client=client,
            project=project,
        )
    )

    return {
        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "protocol_headers": list(
            (
                protocol.get(
                    "library"
                )
                or {}
            ).keys()
        ),

        "protocol_header_source": (
            protocol.get(
                "source_blob"
            )
            or ""
        ),

        "identification": (
            identification
        ),

        "approved_mapping": (
            approved_mapping
        ),

        "approved_mapping_exists": (
            isinstance(
                approved_mapping,
                dict,
            )
        ),

        "approved_mapping_path": (
            approved_blob_path
        ),
    }


@router.post(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}/mapping/approve"
)
def approve_cyber2_header_mapping(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    request: ApproveHeaderMappingRequest,
) -> dict[str, Any]:

    client = str(
        request.client or ""
    ).strip()

    project = str(
        request.project or ""
    ).strip()

    header_set_id = str(
        header_set_id or ""
    ).strip()

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not header_set_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Header Set ID is required."
            ),
        )

    if not request.documents:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one document "
                "mapping is required."
            ),
        )

    identification_blob_path = (
        _identification_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    identification = (
        _load_required_json(
            identification_blob_path,
            description=(
                "Header Identification result"
            ),
        )
    )

    identified_documents = (
        identification.get(
            "documents"
        )
        or []
    )

    if not isinstance(
        identified_documents,
        list,
    ):
        identified_documents = []

    identified_by_doc_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for document in (
        identified_documents
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

        if doc_id:
            identified_by_doc_id[
                doc_id
            ] = document

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

    protocol_lookup = {
        _normalize_header(
            header
        ): header
        for header
        in protocol_headers
        if str(
            header or ""
        ).strip()
    }

    approved_documents: list[
        dict[str, Any]
    ] = []

    validation_errors: list[
        dict[str, Any]
    ] = []

    total_keep_count = 0
    total_map_count = 0
    total_rename_count = 0
    total_delete_count = 0
    total_approve_count = 0

    for submitted_document in (
        request.documents
    ):
        doc_id = str(
            submitted_document.doc_id
            or ""
        ).strip()

        if not doc_id:
            validation_errors.append(
                {
                    "doc_id": "",
                    "error": (
                        "Document is missing "
                        "Doc ID."
                    ),
                }
            )

            continue

        identified_document = (
            identified_by_doc_id.get(
                doc_id
            )
        )

        if not identified_document:
            validation_errors.append(
                {
                    "doc_id": doc_id,
                    "error": (
                        "Document is not present "
                        "in Header Identification."
                    ),
                }
            )

            continue

        identified_columns = (
            identified_document.get(
                "columns"
            )
            or []
        )

        if not isinstance(
            identified_columns,
            list,
        ):
            identified_columns = []

        identified_columns_by_index: dict[
            int,
            dict[str, Any],
        ] = {}

        for column in (
            identified_columns
        ):
            if not isinstance(
                column,
                dict,
            ):
                continue

            try:
                column_index = int(
                    column.get(
                        "column_index"
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            identified_columns_by_index[
                column_index
            ] = column

        submitted_indexes: set[
            int
        ] = set()

        approved_columns: list[
            dict[str, Any]
        ] = []

        document_has_error = False

        for decision in (
            submitted_document.columns
        ):
            column_index = int(
                decision.column_index
            )

            if column_index in (
                submitted_indexes
            ):
                validation_errors.append(
                    {
                        "doc_id": doc_id,
                        "column_index": (
                            column_index
                        ),
                        "error": (
                            "Column was submitted "
                            "more than once."
                        ),
                    }
                )

                document_has_error = True
                continue

            submitted_indexes.add(
                column_index
            )

            identified_column = (
                identified_columns_by_index.get(
                    column_index
                )
            )

            if not identified_column:
                validation_errors.append(
                    {
                        "doc_id": doc_id,
                        "column_index": (
                            column_index
                        ),
                        "error": (
                            "Column is not present "
                            "in Header Identification."
                        ),
                    }
                )

                document_has_error = True
                continue

            disposition = str(
                decision.disposition
                or ""
            ).strip().lower()

            submitted_final_header = str(
                decision.final_header
                or ""
            ).strip()

            source_header = str(
                identified_column.get(
                    "source_header"
                )
                or (
                    f"Column "
                    f"{column_index + 1}"
                )
            ).strip()

            recommended_header = str(
                identified_column.get(
                    "recommended_protocol_header"
                )
                or ""
            ).strip()

            final_header = ""

            if disposition == "approve":
                #
                # Approve means accept the
                # INSYT recommendation.
                #
                final_header = (
                    submitted_final_header
                    or recommended_header
                )

                if not final_header:
                    validation_errors.append(
                        {
                            "doc_id": doc_id,
                            "column_index": (
                                column_index
                            ),
                            "error": (
                                "Approve requires "
                                "a recommended or "
                                "selected final header."
                            ),
                        }
                    )

                    document_has_error = True
                    continue

                normalized = (
                    _normalize_header(
                        final_header
                    )
                )

                if normalized not in (
                    protocol_lookup
                ):
                    validation_errors.append(
                        {
                            "doc_id": doc_id,
                            "column_index": (
                                column_index
                            ),
                            "error": (
                                "Approved header must "
                                "be a Project Protocol "
                                "header."
                            ),
                            "final_header": (
                                final_header
                            ),
                        }
                    )

                    document_has_error = True
                    continue

                final_header = (
                    protocol_lookup[
                        normalized
                    ]
                )

                total_approve_count += 1

            elif disposition == "map":
                #
                # Explicit reviewer choice from
                # Project Protocol dropdown.
                #
                if not submitted_final_header:
                    validation_errors.append(
                        {
                            "doc_id": doc_id,
                            "column_index": (
                                column_index
                            ),
                            "error": (
                                "Map requires a "
                                "Project Protocol "
                                "header."
                            ),
                        }
                    )

                    document_has_error = True
                    continue

                normalized = (
                    _normalize_header(
                        submitted_final_header
                    )
                )

                if normalized not in (
                    protocol_lookup
                ):
                    validation_errors.append(
                        {
                            "doc_id": doc_id,
                            "column_index": (
                                column_index
                            ),
                            "error": (
                                "Mapped header is not "
                                "a Project Protocol "
                                "header."
                            ),
                            "final_header": (
                                submitted_final_header
                            ),
                        }
                    )

                    document_has_error = True
                    continue

                final_header = (
                    protocol_lookup[
                        normalized
                    ]
                )

                total_map_count += 1

            elif disposition == "rename":
                #
                # Rename intentionally allows a
                # custom non-protocol header.
                #
                if not submitted_final_header:
                    validation_errors.append(
                        {
                            "doc_id": doc_id,
                            "column_index": (
                                column_index
                            ),
                            "error": (
                                "Rename requires "
                                "a new header name."
                            ),
                        }
                    )

                    document_has_error = True
                    continue

                final_header = (
                    submitted_final_header
                )

                total_rename_count += 1

            elif disposition == "keep":
                #
                # Preserve the source header.
                #
                final_header = (
                    submitted_final_header
                    or source_header
                )

                total_keep_count += 1

            elif disposition == "delete":
                #
                # Column will be removed only when
                # a future transformed working CSV
                # is generated.
                #
                final_header = ""

                total_delete_count += 1

            else:
                validation_errors.append(
                    {
                        "doc_id": doc_id,
                        "column_index": (
                            column_index
                        ),
                        "error": (
                            "Unsupported column "
                            "disposition."
                        ),
                    }
                )

                document_has_error = True
                continue

            approved_columns.append(
                {
                    "column_index": (
                        column_index
                    ),

                    "column_number": (
                        column_index + 1
                    ),

                    "source_header": (
                        source_header
                    ),

                    "recommended_protocol_header": (
                        recommended_header
                    ),

                    "recommendation_confidence": (
                        identified_column.get(
                            "mapping_confidence"
                        )
                    ),

                    "semantic_type": (
                        identified_column.get(
                            "semantic_type"
                        )
                    ),

                    "semantic_confidence": (
                        identified_column.get(
                            "semantic_confidence"
                        )
                    ),

                    "match_method": (
                        identified_column.get(
                            "match_method"
                        )
                    ),

                    "disposition": (
                        disposition
                    ),

                    "final_header": (
                        final_header
                    ),

                    "delete_column": (
                        disposition
                        == "delete"
                    ),

                    "mapped_to_protocol": (
                        disposition
                        in {
                            "approve",
                            "map",
                        }
                    ),
                }
            )

        expected_indexes = set(
            identified_columns_by_index.keys()
        )

        missing_indexes = sorted(
            expected_indexes
            - submitted_indexes
        )

        if missing_indexes:
            validation_errors.append(
                {
                    "doc_id": doc_id,
                    "error": (
                        "Every identified column "
                        "must receive a disposition."
                    ),
                    "missing_column_indexes": (
                        missing_indexes
                    ),
                }
            )

            document_has_error = True

        if document_has_error:
            continue

        approved_columns.sort(
            key=lambda column: int(
                column.get(
                    "column_index"
                )
                or 0
            )
        )

        approved_documents.append(
            {
                "doc_id": doc_id,

                "source_csv_path": (
                    identified_document.get(
                        "source_csv_path"
                    )
                    or ""
                ),

                "classification": (
                    identified_document.get(
                        "classification"
                    )
                    or ""
                ),

                "entity_types": (
                    identified_document.get(
                        "entity_types"
                    )
                    or []
                ),

                "header_status": (
                    identified_document.get(
                        "header_status"
                    )
                    or ""
                ),

                "header_confidence": (
                    identified_document.get(
                        "header_confidence"
                    )
                ),

                "column_count": len(
                    approved_columns
                ),

                "columns": (
                    approved_columns
                ),
                
                "canonical_output_headers": [
                    header
                    for header in protocol_headers
                    if any(
                        str(
                            column.get(
                                "final_header"
                            )
                            or ""
                        ).strip()
                        == header
                        and not bool(
                            column.get(
                                "delete_column"
                            )
                        )
                        for column
                        in approved_columns
                    )
                ]
                + [
                    str(
                        column.get(
                            "final_header"
                        )
                        or ""
                    ).strip()
                    for column
                    in approved_columns
                    if str(
                        column.get(
                            "final_header"
                        )
                        or ""
                    ).strip()
                    and str(
                        column.get(
                            "final_header"
                        )
                        or ""
                    ).strip()
                    not in protocol_headers
                    and not bool(
                        column.get(
                            "delete_column"
                        )
                    )
                ],
            }
        )

    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Header mapping approval "
                    "contains validation errors."
                ),
                "validation_errors": (
                    validation_errors
                ),
            },
        )

    identified_doc_ids = set(
        identified_by_doc_id.keys()
    )

    submitted_doc_ids = {
        str(
            document.doc_id
            or ""
        ).strip()
        for document
        in request.documents
        if str(
            document.doc_id
            or ""
        ).strip()
    }

    missing_document_ids = sorted(
        identified_doc_ids
        - submitted_doc_ids
    )

    if missing_document_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Every identified document "
                    "in the Header Set must be "
                    "reviewed before final approval."
                ),
                "missing_doc_ids": (
                    missing_document_ids
                ),
            },
        )

    approved_at = (
        _utc_now()
    )

    approved_mapping_blob_path = (
        _approved_mapping_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    approved_payload = {
        "schema_version": 1,

        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "status": (
            "approved"
        ),

        "approved_at": (
            approved_at
        ),

        "approved_by": str(
            request.approved_by
            or ""
        ).strip(),

        "identification_path": (
            identification_blob_path
        ),

        "approved_mapping_path": (
            approved_mapping_blob_path
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

        "canonical_column_order": (
            protocol_headers
        ),

        "canonical_order_source": (
            "project_protocol"
        ),

        "document_count": len(
            approved_documents
        ),

        "decision_counts": {
            "approve": (
                total_approve_count
            ),

            "map": (
                total_map_count
            ),

            "keep": (
                total_keep_count
            ),

            "rename": (
                total_rename_count
            ),

            "delete": (
                total_delete_count
            ),
        },

        "documents": (
            approved_documents
        ),

        #
        # Source safety:
        #
        # This approval file is metadata only.
        # No source CSV has been altered.
        #
        "source_csvs_modified": (
            False
        ),
    }

    _write_processing_json_blob(
        blob_path=(
            approved_mapping_blob_path
        ),
        payload=(
            approved_payload
        ),
        overwrite=True,
    )

    #
    # Update Header Set workflow status.
    #
    manifest_blob_path = (
        _header_set_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    manifest = (
        _load_required_json(
            manifest_blob_path,
            description=(
                "Header Set manifest"
            ),
        )
    )

    manifest[
        "status"
    ] = (
        "schema_mapping_approved"
    )

    manifest[
        "schema_mapping_approved_at"
    ] = approved_at

    manifest[
        "approved_mapping_path"
    ] = (
        approved_mapping_blob_path
    )

    manifest[
        "schema_mapping_decision_counts"
    ] = (
        approved_payload[
            "decision_counts"
        ]
    )

    _write_processing_json_blob(
        blob_path=(
            manifest_blob_path
        ),
        payload=manifest,
        overwrite=True,
    )

    return {
        "status": "approved",

        "message": (
            f"Header mapping approved "
            f"for {len(approved_documents)} "
            f"CSV(s)."
        ),

        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id": (
            header_set_id
        ),

        "approved_mapping_path": (
            approved_mapping_blob_path
        ),

        "document_count": len(
            approved_documents
        ),

        "decision_counts": (
            approved_payload[
                "decision_counts"
            ]
        ),

        "source_csvs_modified": (
            False
        ),
    }
    
@router.get(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}/"
    "mapping/mapped-csvs"
)
def get_cyber2_mapped_csvs(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    client: str = Query(...),
    project: str = Query(...),
) -> dict[str, Any]:

    manifest_blob_path = (
        _mapped_csv_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    mapped_manifest = None

    try:
        mapped_manifest = (
            _read_processing_json_blob(
                manifest_blob_path
            )
        )

    except Exception:
        mapped_manifest = None

    return {
        "workspace": workspace,
        "client": client,
        "project": project,

        "header_set_id":
            header_set_id,

        "mapped_csv_manifest_exists":
            isinstance(
                mapped_manifest,
                dict,
            ),

        "mapped_csv_manifest_path":
            manifest_blob_path,

        "mapped_csv_manifest":
            mapped_manifest,
    }    

@router.post(
    "/{workspace}/cyber2/"
    "header-sets/{header_set_id}/"
    "mapping/generate-mapped-csvs"
)

def generate_cyber2_mapped_csvs(
    workspace: Literal[
        "capture",
        "discovery",
        "summaries",
    ],
    header_set_id: str,
    request: GenerateMappedCsvsRequest,
) -> dict[str, Any]:

    client = str(
        request.client or ""
    ).strip()

    project = str(
        request.project or ""
    ).strip()

    header_set_id = str(
        header_set_id or ""
    ).strip()

    if not client:
        raise HTTPException(
            status_code=400,
            detail="Client is required.",
        )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project is required.",
        )

    if not header_set_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Header Set ID is required."
            ),
        )

    approved_mapping_blob_path = (
        _approved_mapping_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    approved_mapping = (
        _load_required_json(
            approved_mapping_blob_path,
            description=(
                "Approved Header Mapping"
            ),
        )
    )

    if (
        str(
            approved_mapping.get(
                "status"
            )
            or ""
        ).strip().lower()
        != "approved"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Header mapping must be "
                "approved before mapped CSVs "
                "can be generated."
            ),
        )

    protocol_headers = (
        approved_mapping.get(
            "canonical_column_order"
        )
        or approved_mapping.get(
            "protocol_headers"
        )
        or []
    )

    if not isinstance(
        protocol_headers,
        list,
    ):
        protocol_headers = []

    approved_documents = (
        approved_mapping.get(
            "documents"
        )
        or []
    )

    if not isinstance(
        approved_documents,
        list,
    ):
        approved_documents = []

    if not approved_documents:
        raise HTTPException(
            status_code=409,
            detail=(
                "Approved mapping contains "
                "no documents."
            ),
        )

    container = (
        get_container_client(
            workspace
        )
    )

    generated_at = (
        _utc_now()
    )

    generated_documents: list[
        dict[str, Any]
    ] = []

    failed_documents: list[
        dict[str, Any]
    ] = []

    total_source_rows = 0
    total_mapped_rows = 0

    for approved_document in (
        approved_documents
    ):

        if not isinstance(
            approved_document,
            dict,
        ):
            continue

        doc_id = str(
            approved_document.get(
                "doc_id"
            )
            or ""
        ).strip()

        source_csv_path = str(
            approved_document.get(
                "source_csv_path"
            )
            or ""
        ).strip()

        if (
            not doc_id
            or not source_csv_path
        ):
            failed_documents.append(
                {
                    "doc_id":
                        doc_id,

                    "source_csv_path":
                        source_csv_path,

                    "status":
                        "failed",

                    "error": (
                        "Doc ID or source CSV "
                        "path is missing."
                    ),
                }
            )

            continue

        mapped_csv_path = (
            _mapped_csv_path(
                workspace=workspace,
                client=client,
                project=project,
                header_set_id=(
                    header_set_id
                ),
                doc_id=doc_id,
            )
        )

        try:
            (
                source_rows,
                source_delimiter,
            ) = (
                _read_csv_blob_rows(
                    container=container,
                    blob_path=(
                        source_csv_path
                    ),
                )
            )

            transformed = (
                _generate_mapped_document_rows(
                    source_rows=(
                        source_rows
                    ),
                    approved_document=(
                        approved_document
                    ),
                    protocol_headers=(
                        protocol_headers
                    ),
                )
            )

            _write_csv_blob_rows(
                container=container,
                blob_path=(
                    mapped_csv_path
                ),
                rows=(
                    transformed[
                        "rows"
                    ]
                ),
                overwrite=(
                    request
                    .overwrite_existing
                ),
            )

            total_source_rows += int(
                transformed[
                    "source_row_count"
                ]
                or 0
            )

            total_mapped_rows += int(
                transformed[
                    "mapped_row_count"
                ]
                or 0
            )

            generated_documents.append(
                {
                    "doc_id":
                        doc_id,

                    "status":
                        "generated",

                    "source_csv_path":
                        source_csv_path,

                    "mapped_csv_path":
                        mapped_csv_path,

                    "header_status": (
                        approved_document.get(
                            "header_status"
                        )
                        or ""
                    ),

                    "source_delimiter":
                        source_delimiter,

                    "output_delimiter":
                        ",",

                    "source_row_count": (
                        transformed[
                            "source_row_count"
                        ]
                    ),

                    "mapped_row_count": (
                        transformed[
                            "mapped_row_count"
                        ]
                    ),

                    "source_column_count": (
                        transformed[
                            "source_column_count"
                        ]
                    ),

                    "mapped_column_count": (
                        transformed[
                            "mapped_column_count"
                        ]
                    ),

                    "output_headers": (
                        transformed[
                            "output_headers"
                        ]
                    ),

                    "protocol_headers_present": (
                        transformed[
                            "protocol_headers_present"
                        ]
                    ),

                    "custom_headers_retained": (
                        transformed[
                            "custom_headers_retained"
                        ]
                    ),

                    "deleted_headers": (
                        transformed[
                            "deleted_headers"
                        ]
                    ),

                    "generated_at":
                        generated_at,
                }
            )

        except Exception as exc:

            failed_documents.append(
                {
                    "doc_id":
                        doc_id,

                    "status":
                        "failed",

                    "source_csv_path":
                        source_csv_path,

                    "mapped_csv_path":
                        mapped_csv_path,

                    "error":
                        str(exc),
                }
            )

    manifest_blob_path = (
        _mapped_csv_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    if (
        generated_documents
        and not failed_documents
    ):
        manifest_status = (
            "completed"
        )

    elif generated_documents:
        manifest_status = (
            "completed_with_errors"
        )

    else:
        manifest_status = (
            "failed"
        )

    manifest_payload = {
        "schema_version": 1,

        "workspace":
            workspace,

        "client":
            client,

        "project":
            project,

        "header_set_id":
            header_set_id,

        "status":
            manifest_status,

        "generated_at":
            generated_at,

        "generated_by": str(
            request.generated_by
            or ""
        ).strip(),

        "approved_mapping_path": (
            approved_mapping_blob_path
        ),

        "mapped_csv_manifest_path": (
            manifest_blob_path
        ),

        "canonical_column_order": (
            protocol_headers
        ),

        "document_count": (
            len(
                approved_documents
            )
        ),

        "generated_document_count": (
            len(
                generated_documents
            )
        ),

        "failed_document_count": (
            len(
                failed_documents
            )
        ),

        "total_source_rows": (
            total_source_rows
        ),

        "total_mapped_rows": (
            total_mapped_rows
        ),

        "documents": (
            generated_documents
        ),

        "failed_documents": (
            failed_documents
        ),

        "source_csvs_modified":
            False,
    }

    _write_processing_json_blob(
        blob_path=(
            manifest_blob_path
        ),
        payload=(
            manifest_payload
        ),
        overwrite=True,
    )

    #
    # Update the Header Set but do not
    # destroy its prior approval state.
    #
    manifest_path = (
        _header_set_manifest_path(
            workspace=workspace,
            client=client,
            project=project,
            header_set_id=header_set_id,
        )
    )

    header_set_manifest = (
        _load_required_json(
            manifest_path,
            description=(
                "Header Set manifest"
            ),
        )
    )

    header_set_manifest[
        "mapped_csv_status"
    ] = manifest_status

    header_set_manifest[
        "mapped_csv_generated_at"
    ] = generated_at

    header_set_manifest[
        "mapped_csv_manifest_path"
    ] = manifest_blob_path

    header_set_manifest[
        "mapped_csv_generated_count"
    ] = len(
        generated_documents
    )

    header_set_manifest[
        "mapped_csv_failed_count"
    ] = len(
        failed_documents
    )

    _write_processing_json_blob(
        blob_path=(
            manifest_path
        ),
        payload=(
            header_set_manifest
        ),
        overwrite=True,
    )

    return {
        "status":
            manifest_status,

        "message": (
            f"Generated "
            f"{len(generated_documents)} "
            f"mapped CSV(s); "
            f"{len(failed_documents)} "
            f"failed."
        ),

        "workspace":
            workspace,

        "client":
            client,

        "project":
            project,

        "header_set_id":
            header_set_id,

        "mapped_csv_manifest_path": (
            manifest_blob_path
        ),

        "generated_document_count": (
            len(
                generated_documents
            )
        ),

        "failed_document_count": (
            len(
                failed_documents
            )
        ),

        "documents":
            generated_documents,

        "failed_documents":
            failed_documents,

        "source_csvs_modified":
            False,
    }
