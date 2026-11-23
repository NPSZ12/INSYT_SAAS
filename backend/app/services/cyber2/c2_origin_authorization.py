"""Fail-closed C2 origin policy.

Caller must supply an independently authorized server-side receipt.
This function does not authenticate the caller or verify the Merge Set
digest; those are mandatory responsibilities of the integrating API.
No Azure reads or writes occur here.
"""

import re
from collections.abc import Mapping


class C2OriginAuthorizationError(ValueError):
    pass


def require_c2_origin_authorization(
    merge_set, approved_mapping, authorization
):
    def require(condition, message):
        if not condition:
            raise C2OriginAuthorizationError(message)

    require(
        isinstance(merge_set, Mapping)
        and isinstance(approved_mapping, Mapping)
        and isinstance(authorization, Mapping),
        "Invalid authorization inputs",
    )

    require(
        merge_set.get("status") == "completed"
        and approved_mapping.get("status") == "approved",
        "Completed Merge Set and approved mapping required",
    )

    digest = merge_set.get("integrity_sha256")
    require(
        isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "Merge Set digest unavailable",
    )

    keys = (
        "workspace", "client", "project", "header_set_id"
    )

    require(
        all(
            isinstance(merge_set.get(key), str)
            and bool(merge_set[key])
            and merge_set[key] == approved_mapping.get(key)
            and merge_set[key] == authorization.get(key)
            for key in keys
        ),
        "Authorization scope mismatch",
    )

    require(
        isinstance(merge_set.get("merge_set_id"), str)
        and authorization.get("merge_set_id")
            == merge_set["merge_set_id"]
        and authorization.get("merge_integrity_sha256") == digest,
        "Authorization Merge Set binding mismatch",
    )

    require(
        authorization.get("decision") == "approved_non_ai",
        "Non-AI origin authorization required",
    )

    require(
        isinstance(authorization.get("authorized_by"), str)
        and bool(authorization["authorized_by"].strip())
        and isinstance(authorization.get("authorized_at"), str)
        and bool(authorization["authorized_at"].strip()),
        "Audited authorization identity required",
    )

    approved_docs = approved_mapping.get("documents")
    authorized_docs = authorization.get("documents")

    require(
        isinstance(approved_docs, list)
        and bool(approved_docs)
        and isinstance(authorized_docs, list)
        and bool(authorized_docs),
        "Source document inventory required",
    )

    def inventory(documents, *, authorized):
        result = {}

        for doc in documents:
            require(isinstance(doc, Mapping), "Invalid document")

            doc_id = doc.get("doc_id")
            source_kind = doc.get("source_kind")
            # A known AI-origin marker cannot be overridden by
            # administrator non-AI attestation.
            require(
                not any(
                    isinstance(doc.get(key), str)
                    and doc[key].strip().casefold().replace("-", "_")
                    in {
                        "ai",
                        "ai_generated",
                        "ai_extracted",
                        "ai_assisted",
                        "ai_output",
                        "ai_capture",
                        "ai_extraction",
                    }
                    for key in (
                        "source_kind",
                        "source_origin",
                        "capture_method",
                        "extraction_method",
                    )
                ),
                "Known AI-origin source is ineligible for C2",
            )


            require(
                isinstance(doc_id, str)
                and bool(doc_id.strip())
                and doc_id not in result,
                "Incomplete or duplicate source identity",
            )

            if source_kind == "native_json":
                # Existing approved native identity is authoritative.
                # The JSON alias may be absent from old approvals.
                native_path = doc.get("source_native_path")
                json_path = doc.get("source_json_path")
                digest = doc.get("source_sha256")

                require(
                    isinstance(native_path, str)
                    and bool(native_path.strip())
                    and native_path.lower().endswith(
                        (".json", ".jsonl", ".ndjson")
                    )
                    and isinstance(digest, str)
                    and re.fullmatch(
                        r"[0-9a-fA-F]{64}", digest
                    ) is not None,
                    "Incomplete native JSON source identity",
                )

                if authorized:
                    require(
                        isinstance(json_path, str)
                        and json_path == native_path,
                        "Authorized JSON alias does not match native source",
                    )
                elif json_path is not None:
                    require(
                        json_path == native_path,
                        "Approved JSON alias does not match native source",
                    )

                identity = (
                    "native_json",
                    native_path,
                    digest.lower(),
                )

            else:
                # Preserve the original CSV source requirement.
                source_path = doc.get("source_csv_path")

                require(
                    isinstance(source_path, str)
                    and bool(source_path.strip()),
                    "Incomplete or duplicate source identity",
                )

                identity = source_path

            if authorized:
                require(
                    doc.get("capture_method")
                        == "non_ai_structured_source",
                    "Manual, AI, or unknown source rejected",
                )

                if source_kind == "native_json":
                    require(
                        doc.get("source_kind") == "native_json",
                        "Authorized JSON source kind mismatch",
                    )

            result[doc_id] = identity

        return result

    approved_inventory = inventory(
        approved_docs, authorized=False
    )
    authorized_inventory = inventory(
        authorized_docs, authorized=True
    )

    require(
        approved_inventory == authorized_inventory,
        "Authorized source inventory mismatch",
    )

    return {
        "origin_authorized": True,
        "merge_set_id": merge_set["merge_set_id"],
        "header_set_id": merge_set["header_set_id"],
        "authorized_document_count": len(approved_inventory),
    }
