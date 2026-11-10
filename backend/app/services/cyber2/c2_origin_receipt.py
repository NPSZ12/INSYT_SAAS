"""Immutable administrator-attested C2 source-origin receipts.

The API must authenticate the administrator and verify the completed
Merge Set before calling this service. An attestation records a human
review decision; it is not automatic proof of source creation method.
"""

import hashlib
import json
import re
from datetime import datetime, timezone

from app.services.cyber2.c2_origin_authorization import (
    require_c2_origin_authorization,
)


class C2OriginReceiptError(ValueError):
    pass


def _encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _require(condition, message):
    if not condition:
        raise C2OriginReceiptError(message)


def _path(base, merge_id):
    _require(
        isinstance(base, str) and bool(base.strip())
        and not base.startswith("/")
        and ".." not in base.split("/"),
        "Invalid project storage base",
    )
    _require(
        isinstance(merge_id, str)
        and re.fullmatch(r"MSET-[0-9A-F]{32}", merge_id) is not None,
        "Invalid Merge Set ID",
    )
    return (
        f"{base.rstrip('/')}/cyber2/c2/origin_approvals/"
        f"{merge_id}/authorization.json"
    )


def _load(blob):
    try:
        document = json.loads(
            blob.download_blob().readall().decode("utf-8")
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise

    _require(isinstance(document, dict), "Invalid stored approval")

    digest = document.get("integrity_sha256")
    unsigned = {
        key: value for key, value in document.items()
        if key != "integrity_sha256"
    }

    _require(
        isinstance(digest, str) and digest == _digest(unsigned),
        "Stored origin approval integrity failed",
    )
    return document


def save_c2_origin_approval(
    *,
    container,
    project_base_path,
    merge_set,
    approved_mapping,
    reviewed_doc_ids,
    reviewer,
    attested_non_ai,
    content_settings_factory=None,
):
    """Create one audited, immutable origin-approval receipt.

    The reviewed source inventory is reconstructed from the approved
    mapping, not from client-supplied CSV paths or origin labels.
    """
    _require(
        container is not None
        and isinstance(merge_set, dict)
        and isinstance(approved_mapping, dict),
        "Missing server-side approval inputs",
    )
    _require(
        attested_non_ai is True,
        "Explicit non-AI administrator attestation required",
    )
    _require(
        isinstance(reviewer, str) and bool(reviewer.strip()),
        "Authenticated administrator identity required",
    )

    docs = approved_mapping.get("documents")
    _require(
        isinstance(docs, list) and bool(docs),
        "Approved source inventory unavailable",
    )

    inventory = {}
    for doc in docs:
        _require(isinstance(doc, dict), "Invalid approved document")
        doc_id = doc.get("doc_id")
        path = doc.get("source_csv_path")
        _require(
            isinstance(doc_id, str) and bool(doc_id)
            and doc_id not in inventory
            and isinstance(path, str) and bool(path),
            "Invalid or duplicate approved source document",
        )
        inventory[doc_id] = path

    _require(
        isinstance(reviewed_doc_ids, list)
        and len(reviewed_doc_ids) == len(inventory)
        and all(
            isinstance(doc_id, str) and bool(doc_id)
            for doc_id in reviewed_doc_ids
        )
        and len(set(reviewed_doc_ids)) == len(reviewed_doc_ids)
        and set(reviewed_doc_ids) == set(inventory),
        "Reviewed documents do not match approved source inventory",
    )

    scope_keys = (
        "workspace", "client", "project", "header_set_id"
    )
    _require(
        all(
            isinstance(merge_set.get(k), str)
            and bool(merge_set[k])
            and merge_set[k] == approved_mapping.get(k)
            for k in scope_keys
        ),
        "Origin approval project scope mismatch",
    )

    receipt = {
        "schema_version": 1,
        **{key: merge_set[key] for key in scope_keys},
        "merge_set_id": merge_set.get("merge_set_id"),
        "merge_integrity_sha256":
            merge_set.get("integrity_sha256"),
        "decision": "approved_non_ai",
        "authorized_by": reviewer.strip(),
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "approval_basis": "administrator_source_review",
        "documents": [
            {
                "doc_id": doc_id,
                "source_csv_path": inventory[doc_id],
                "capture_method": "non_ai_structured_source",
            }
            for doc_id in sorted(inventory)
        ],
    }

    require_c2_origin_authorization(
        merge_set, approved_mapping, receipt
    )

    blob = container.get_blob_client(
        _path(project_base_path, receipt["merge_set_id"])
    )

    document = dict(receipt)
    document["integrity_sha256"] = _digest(receipt)

    try:
        settings = (
            content_settings_factory()
            if content_settings_factory is not None
            else None
        )
        if settings is None and content_settings_factory is None:
            from azure.storage.blob import ContentSettings
            settings = ContentSettings(content_type="application/json")

        blob.upload_blob(
            _encode(document),
            overwrite=False,
            content_settings=settings,
        )
        status = "approved"
        stored = document

    except Exception as exc:
        if getattr(exc, "status_code", None) not in (409, 412):
            raise

        stored = _load(blob)
        _require(
            stored is not None,
            "Concurrent origin authorization unavailable",
        )

        # An approval is immutable. A replay may not change the actor,
        # source inventory, Merge Set, or authorization decision.
        previous = {
            key: value for key, value in stored.items()
            if key not in ("integrity_sha256", "authorized_at")
        }
        submitted = {
            key: value for key, value in document.items()
            if key not in ("integrity_sha256", "authorized_at")
        }
        _require(
            previous == submitted,
            "A different origin authorization already exists",
        )
        status = "already_approved"

    return {
        "status": status,
        "merge_set_id": receipt["merge_set_id"],
        "header_set_id": receipt["header_set_id"],
        "reviewed_document_count": len(inventory),
        "authorized_by": stored["authorized_by"],
    }
