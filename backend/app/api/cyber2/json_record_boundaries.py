"""Read-only record boundary candidates from existing JSON evidence.

No native source mutation, approval, AI invocation or CSV generation.
Candidates require existing backend validation before CSV construction.
"""

def discover_record_boundaries(columns):
    """Return candidate record boundaries without definitive row counts."""

    if not isinstance(columns, list):
        raise ValueError("Invalid JSON column evidence.")

    evidence = {}

    for column in columns:

        if not isinstance(column, dict):
            raise ValueError("Invalid JSON field evidence.")

        pointer = column.get("json_pointer")
        kind = column.get("json_kind") or column.get("kind")

        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("Missing JSON pointer evidence.")

        if pointer in evidence:
            raise ValueError("Duplicate JSON pointer evidence.")

        evidence[pointer] = kind

    candidates = [
        {
            "selection_id": "root",
            "label": "Original JSON record structure",
            "record_array_path": None,
        }
    ]

    for pointer, kind in sorted(evidence.items()):

        if kind != "array":
            continue

        # Existing generator supports arrays reached through
        # object properties, not arbitrary nested array expansion.
        parts = pointer[1:].split("/")

        if any(not part or part == "[]" for part in parts):
            continue

        # Exclude primitive arrays and mixed record populations.
        if evidence.get(pointer + "/[]") != "object":
            continue

        candidates.append({
            "selection_id": pointer,
            "label": pointer[1:].replace("/", "."),
            "record_array_path": pointer,
        })

    return candidates


def matched_record_boundary_options(
    approved_document,
    identified_document,
):
    """Reuse structural evidence without changing approved decisions."""

    if not isinstance(approved_document, dict):
        raise ValueError("Invalid approved JSON document.")

    if not isinstance(identified_document, dict):
        raise ValueError("JSON identification evidence missing.")

    for document in (approved_document, identified_document):
        if document.get("source_kind") != "native_json":
            raise ValueError("Native JSON source required.")

    if identified_document.get("identification_status") != "COMPLETED":
        raise ValueError("JSON identification is incomplete.")

    for key in (
        "doc_id",
        "source_sha256",
        "source_native_path",
        "source_format",
    ):
        value = approved_document.get(key)

        if (
            not isinstance(value, str)
            or not value
            or identified_document.get(key) != value
        ):
            raise ValueError("Approved JSON source identity mismatch.")

    source_hash = approved_document["source_sha256"]

    if (
        len(source_hash) != 64
        or any(c not in "0123456789abcdef" for c in source_hash)
    ):
        raise ValueError("Invalid JSON source hash.")

    approved_columns = approved_document.get("columns")
    identified_columns = identified_document.get("columns")
    structural_fields = identified_document.get("structural_fields")

    if not (
        isinstance(approved_columns, list)
        and approved_columns
        and isinstance(identified_columns, list)
        and identified_columns
        and isinstance(structural_fields, list)
    ):
        raise ValueError("Complete JSON structural evidence required.")

    def scalar_identity(columns):
        identities = set()

        for column in columns:
            if not isinstance(column, dict):
                raise ValueError("Invalid JSON scalar evidence.")

            pointer = column.get("json_pointer")
            index = column.get("column_index")

            if (
                not isinstance(pointer, str)
                or not pointer.startswith("/")
                or column.get("json_kind") != "scalar"
                or not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
            ):
                raise ValueError("Invalid JSON scalar identity.")

            identity = (index, pointer)

            if identity in identities:
                raise ValueError("Duplicate JSON scalar identity.")

            identities.add(identity)

        if len({item[0] for item in identities}) != len(identities):
            raise ValueError("Duplicate JSON column index.")

        return identities

    if scalar_identity(approved_columns) != scalar_identity(
        identified_columns
    ):
        raise ValueError("Approved JSON field population differs.")

    for field in structural_fields:
        if (
            not isinstance(field, dict)
            or field.get("json_kind") not in {
                "array", "object", "mixed"
            }
        ):
            raise ValueError("Invalid JSON structural evidence.")

    candidates = discover_record_boundaries(
        identified_columns + structural_fields
    )

    # Do not offer unsupported root transformations when
    # retained nested array fields require explicit boundaries.
    if any(
        "/[]/" in column["json_pointer"]
        for column in approved_columns
        if not column.get("delete_column")
    ):
        candidates = [
            option for option in candidates
            if option["selection_id"] != "root"
        ]

    if not candidates:
        raise ValueError("No supported JSON record boundary available.")

    return candidates


def approved_record_boundary_options(
    approved_mapping,
    identification,
):
    """Join approved documents to existing identification evidence."""

    if approved_mapping is None:
        return {}

    if not isinstance(approved_mapping, dict):
        raise ValueError("Invalid approved mapping.")

    documents = approved_mapping.get("documents")

    if not isinstance(documents, list):
        raise ValueError("Approved document inventory missing.")

    if not isinstance(identification, dict):
        raise ValueError("Identification evidence missing.")

    identified_documents = identification.get("documents")

    if not isinstance(identified_documents, list):
        raise ValueError("Identification document inventory missing.")

    identified = {}

    for document in identified_documents:
        if not isinstance(document, dict):
            raise ValueError("Invalid identification document.")

        doc_id = document.get("doc_id")

        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("Identification document identity missing.")

        if doc_id in identified:
            raise ValueError("Duplicate identification document.")

        identified[doc_id] = document

    result = {}

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Invalid approved document.")

        if document.get("source_kind") != "native_json":
            continue

        doc_id = document.get("doc_id")

        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("Approved document identity missing.")

        if doc_id in result:
            raise ValueError("Duplicate approved document.")

        try:
            options = matched_record_boundary_options(
                document,
                identified.get(doc_id),
            )

            result[doc_id] = {
                "status": "available",
                "options": options,
            }

        except ValueError as exc:
            result[doc_id] = {
                "status": "needs_review",
                "options": [],
                "error": str(exc),
            }

    return result
