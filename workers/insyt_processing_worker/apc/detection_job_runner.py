from __future__ import annotations

import json
import os
import re

from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from .db import LedgerDB
from .stages.pii_phi_detection import run_pii_phi_detection
from .util import json_dumps, new_id, utc_now


def _processing_account() -> str:
    return os.getenv(
        "INSYT_PROCESSING_STORAGE_ACCOUNT",
        "insytprodstorage",
    )


def _processing_container() -> str:
    return os.getenv(
        "INSYT_PROCESSING_CONTAINER",
        "insyt-processing",
    )


def _review_account() -> str:
    return os.getenv(
        "INSYT_REVIEW_STORAGE_ACCOUNT",
        "insytreviewstorage",
    )


def _review_container(workspace: str) -> str:
    workspace_key = str(
        workspace or "capture"
    ).strip().lower()

    return (
        os.getenv(
            f"INSYT_REVIEW_CONTAINER_{workspace_key.upper()}"
        )
        or os.getenv("INSYT_REVIEW_CONTAINER")
        or f"insyt-{workspace_key}"
    )


def _processing_blob_service() -> BlobServiceClient:
    connection_string = os.getenv(
        "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(
            connection_string
        )

    return BlobServiceClient(
        account_url=(
            f"https://{_processing_account()}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _review_blob_service() -> BlobServiceClient:
    connection_string = os.getenv(
        "INSYT_REVIEW_STORAGE_CONNECTION_STRING"
    )

    if connection_string:
        return BlobServiceClient.from_connection_string(
            connection_string
        )

    return BlobServiceClient(
        account_url=(
            f"https://{_review_account()}"
            ".blob.core.windows.net"
        ),
        credential=DefaultAzureCredential(),
    )


def _write_processing_json(
    blob_path: str,
    payload: Any,
) -> dict[str, Any]:
    container = (
        _processing_blob_service()
        .get_container_client(_processing_container())
    )

    blob_client = container.get_blob_client(blob_path)

    data = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(
            content_type="application/json; charset=utf-8"
        ),
    )

    return {
        "storage_account": _processing_account(),
        "container": _processing_container(),
        "blob_path": blob_path,
        "bytes": len(data),
    }


def _download_detection_text(
    *,
    workspace: str,
    blob_path: str,
    destination: Path,
) -> None:
    container = (
        _review_blob_service()
        .get_container_client(
            _review_container(workspace)
        )
    )

    blob_client = container.get_blob_client(blob_path)

    data = blob_client.download_blob().readall()

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_bytes(data)


def _seed_source_job(
    db: LedgerDB,
    *,
    source_job_id: str,
    matter_id: str,
    client_id: str,
    workspace: str,
) -> None:
    existing = db.query_one(
        """
        SELECT job_id
        FROM processing_job
        WHERE job_id=?
        """,
        (source_job_id,),
    )

    if existing:
        return

    db.execute(
        """
        INSERT INTO processing_job (
            job_id,
            matter_id,
            client_id,
            created_at,
            status,
            metadata_json
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            source_job_id,
            matter_id,
            client_id,
            utc_now(),
            "detection_source",
            json_dumps(
                {
                    "workspace": workspace,
                    "purpose": (
                        "data_element_detection_source"
                    ),
                }
            ),
        ),
    )


def _seed_detection_document(
    db: LedgerDB,
    *,
    source_job_id: str,
    matter_id: str,
    doc: dict[str, Any],
    local_text_path: Path,
) -> str:
    doc_id = str(
        doc.get("doc_id") or ""
    ).strip()

    file_id = (
        str(doc.get("file_id") or "").strip()
        or new_id("DETFILE")
    )

    native_blob_path = str(
        doc.get("native_staged_blob_path") or ""
    )

    original_name = (
        native_blob_path.rsplit("/", 1)[-1]
        if native_blob_path
        else f"{doc_id}.bin"
    )

    extension = ""

    if "." in original_name:
        extension = (
            original_name.rsplit(".", 1)[-1]
            .strip()
            .lower()
        )

    existing = db.query_one(
        """
        SELECT file_id
        FROM file_processing_metrics
        WHERE job_id=? AND doc_id=?
        """,
        (
            source_job_id,
            doc_id,
        ),
    )

    if existing:
        return str(existing["file_id"])

    db.execute(
        """
        INSERT INTO file_processing_metrics (
            file_id,
            matter_id,
            job_id,
            original_path,
            normalized_path,
            extension,
            source_bytes,
            expanded_bytes,
            is_container,
            is_extracted,
            page_count,
            text_bytes,
            has_native_text,
            requires_ocr,
            is_duplicate,
            is_denisted,
            doc_id,
            text_output_path,
            stage_status_json,
            exception_json,
            created_at,
            updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            file_id,
            matter_id,
            source_job_id,
            native_blob_path or original_name,
            original_name,
            extension,
            int(doc.get("source_bytes") or 0),
            int(doc.get("source_bytes") or 0),
            0,
            0,
            int(doc.get("page_count") or 0),
            int(local_text_path.stat().st_size),
            1,
            0,
            0,
            0,
            doc_id,
            str(local_text_path),
            json_dumps(
                {
                    "detection_staging": {
                        "status": "ready",
                        "source_text_blob_path": (
                            doc.get(
                                "text_staged_blob_path"
                            )
                        ),
                    }
                }
            ),
            "[]",
            utc_now(),
            utc_now(),
        ),
    )

    return file_id

_GENERIC_IDENTIFIER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[A-Za-z0-9]"
    r"[A-Za-z0-9._/\-]{4,38}"
    r"[A-Za-z0-9]"
    r"(?![A-Za-z0-9])"
)

_GENERIC_IDENTIFIER_SPACED_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z0-9]{1,8}[ \t]+){1,3}"
    r"[A-Za-z0-9]{1,8}"
    r"(?![A-Za-z0-9])"
)

_GENERIC_IDENTIFIER_LABEL_RE = re.compile(
    r"\b("
    r"account|acct|claim|case|member|patient|customer|cust|"
    r"reference|ref|record|policy|invoice|inv|order|ticket|"
    r"authorization|auth|confirmation|confirm|tracking|"
    r"identifier|identification|id|number|no|key|token"
    r")\b",
    re.IGNORECASE,
)


def _span_overlaps_known_hit(
    start: int,
    end: int,
    known_spans: list[tuple[int, int]],
) -> bool:
    for known_start, known_end in known_spans:
        if start < known_end and end > known_start:
            return True

    return False


def _identifier_shape(value: str) -> str:
    shape_parts: list[str] = []

    for char in value:
        if char.isalpha():
            shape_parts.append("A")
        elif char.isdigit():
            shape_parts.append("N")
        else:
            shape_parts.append(char)

    return "".join(shape_parts)


def _compress_shape(shape: str) -> str:
    if not shape:
        return ""

    result: list[str] = []
    current = shape[0]
    count = 1

    def flush(token: str, token_count: int) -> None:
        if token in {"A", "N"}:
            result.append(
                token if token_count == 1
                else f"{token}{token_count}"
            )
        else:
            result.extend(token for _ in range(token_count))

    for char in shape[1:]:
        if char == current:
            count += 1
            continue

        flush(current, count)
        current = char
        count = 1

    flush(current, count)

    return "".join(result)

def _normalize_spaced_identifier(
    value: str,
) -> str:
    parts = [
        part
        for part in re.split(
            r"[ \t]+",
            str(value or "").strip(),
        )
        if part
    ]

    return "_".join(parts)

def _generic_identifier_context(
    text: str,
    start: int,
    end: int,
    *,
    before_chars: int = 48,
    after_chars: int = 32,
) -> tuple[str, str]:
    before = text[
        max(0, start - before_chars):start
    ]

    after = text[
        end:min(len(text), end + after_chars)
    ]

    return (
        " ".join(before.split()),
        " ".join(after.split()),
    )

def _infer_generic_identifier_label(
    context_before: str,
) -> tuple[str, float]:
    """
    Infer a nearby human-readable identifier label.

    Examples:
        "Internal File Key:" -> "Internal File Key"
        "Matter Token:" -> "Matter Token"
        "Custom Reference:" -> "Custom Reference"

    Only alphabetic label words are accepted here so an
    earlier identifier value is not accidentally absorbed
    into the inferred label.
    """

    value = str(
        context_before or ""
    ).strip()

    if not value:
        return "", 0.0

    match = re.search(
        r"("
        r"(?:[A-Za-z][A-Za-z_-]*\s+){0,3}"
        r"[A-Za-z][A-Za-z_-]*"
        r")"
        r"\s*[:#\-]\s*$",
        value,
    )

    if not match:
        return "", 0.0

    label = " ".join(
        str(match.group(1) or "").split()
    ).strip()

    if not label:
        return "", 0.0

    #
    # Directly adjacent labeled values are strong evidence.
    #
    confidence = 0.88

    if _GENERIC_IDENTIFIER_LABEL_RE.search(
        label
    ):
        confidence = 0.95

    return label, confidence

def _looks_like_generic_identifier(
    value: str,
    context_before: str,
    context_after: str,
) -> tuple[bool, float]:
    stripped = value.strip()

    if len(stripped) < 6 or len(stripped) > 40:
        return False, 0.0

    has_alpha = any(char.isalpha() for char in stripped)
    has_digit = any(char.isdigit() for char in stripped)

    if not has_digit:
        return False, 0.0

    label_context = (
        f"{context_before} {context_after}"
    )

    has_identifier_label = bool(
        _GENERIC_IDENTIFIER_LABEL_RE.search(
            label_context
        )
    )

    # Conservative V1:
    # mixed alpha/numeric identifiers may qualify
    # without a nearby label.
    #
    # Purely numeric candidates require contextual
    # evidence so ordinary numbers are not flooded
    # into the candidate population.
    if not has_alpha and not has_identifier_label:
        return False, 0.0

    score = 0.50

    if has_alpha and has_digit:
        score += 0.20

    if any(
        separator in stripped
        for separator in ("-", "/", "_", ".")
    ):
        score += 0.08

    if has_identifier_label:
        score += 0.17

    transitions = 0
    previous_class = ""

    for char in stripped:
        if char.isalpha():
            current_class = "A"
        elif char.isdigit():
            current_class = "N"
        else:
            current_class = "S"

        if (
            previous_class
            and current_class != previous_class
        ):
            transitions += 1

        previous_class = current_class

    if transitions >= 1:
        score += 0.05

    return True, min(score, 0.99)


def _find_generic_identifier_candidates(
    text: str,
    known_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known_spans: list[tuple[int, int]] = []

    for hit in known_hits:
        try:
            known_start = int(
                hit.get("start_offset")
            )
            known_end = int(
                hit.get("end_offset")
            )
        except (TypeError, ValueError):
            continue

        if known_end <= known_start:
            continue

        known_spans.append(
            (known_start, known_end)
        )

    candidates: list[dict[str, Any]] = []

    for match in _GENERIC_IDENTIFIER_TOKEN_RE.finditer(
        text
    ):
        start = match.start()
        end = match.end()
        value = match.group(0)

        if _span_overlaps_known_hit(
            start,
            end,
            known_spans,
        ):
            continue

        context_before, context_after = (
            _generic_identifier_context(
                text,
                start,
                end,
            )
        )
        
        inferred_label, inferred_label_confidence = (
            _infer_generic_identifier_label(
                context_before
            )
        )

        accepted, candidate_score = (
            _looks_like_generic_identifier(
                value,
                context_before,
                context_after,
            )
        )

        if not accepted:
            continue

        shape = _identifier_shape(value)
        normalized_shape = _compress_shape(
            shape
        )

        candidates.append(
            {
                "detected_value": value,
                "normalized_value": value.upper(),
                "start_offset": start,
                "end_offset": end,
                "shape": shape,
                "normalized_shape": (
                    normalized_shape
                ),
                "context_before": context_before,
                "context_after": context_after,
                "candidate_score": round(
                    candidate_score,
                    4,
                ),
                "detector": (
                    "insyt_fsm_generic_identifier"
                ),
                "detector_version": "v1",
                "candidate_type": (
                    "generic_identifier"
                ),
                "inferred_label": inferred_label,
                "inferred_label_confidence": round(
                    inferred_label_confidence,
                    4,
                ),
            }
        )
        
    existing_candidate_spans = [
        (
            int(candidate.get("start_offset") or 0),
            int(candidate.get("end_offset") or 0),
        )
        for candidate in candidates
    ]

    for match in _GENERIC_IDENTIFIER_SPACED_RE.finditer(
        text
    ):
        start = match.start()
        end = match.end()
        value = match.group(0).strip()

        if _span_overlaps_known_hit(
            start,
            end,
            existing_candidate_spans,
        ):
            continue

        if _span_overlaps_known_hit(
            start,
            end,
            known_spans,
        ):
            continue

        context_before, context_after = (
            _generic_identifier_context(
                text,
                start,
                end,
            )
        )
        
        inferred_label, inferred_label_confidence = (
            _infer_generic_identifier_label(
                context_before
            )
        )

        normalized_value = (
            _normalize_spaced_identifier(
                value
            )
        )

        accepted, candidate_score = (
            _looks_like_generic_identifier(
                normalized_value,
                context_before,
                context_after,
            )
        )

        if not accepted:
            continue

        #
        # Require stronger context for OCR-spaced
        # identifiers so ordinary prose is not
        # accidentally treated as an identifier.
        #
        label_context = (
            f"{context_before} {context_after}"
        )

        if not _GENERIC_IDENTIFIER_LABEL_RE.search(
            label_context
        ):
            continue

        shape = _identifier_shape(
            normalized_value
        )

        normalized_shape = _compress_shape(
            shape
        )

        candidates.append(
            {
                "detected_value": value,
                "normalized_value": (
                    normalized_value.upper()
                ),
                "start_offset": start,
                "end_offset": end,
                "shape": shape,
                "normalized_shape": (
                    normalized_shape
                ),
                "context_before": (
                    context_before
                ),
                "context_after": (
                    context_after
                ),
                "candidate_score": round(
                    min(
                        candidate_score,
                        0.95,
                    ),
                    4,
                ),
                "detector": (
                    "insyt_fsm_generic_identifier"
                ),
                "detector_version": "v1",
                "candidate_type": (
                    "generic_identifier"
                ),
                "ocr_reconstructed": True,
                "reconstruction_method": (
                    "space_to_separator"
                ),
                "inferred_label": inferred_label,
                "inferred_label_confidence": round(
                    inferred_label_confidence,
                    4,
                ),
            }
        )

    return candidates


def _build_generic_identifier_clusters(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clusters: dict[
        str,
        dict[str, Any],
    ] = {}

    for candidate in candidates:
        normalized_shape = str(
            candidate.get("normalized_shape")
            or ""
        ).strip()

        if not normalized_shape:
            continue

        cluster_key = normalized_shape

        cluster = clusters.setdefault(
            cluster_key,
            {
                "cluster_key": cluster_key,
                "normalized_shape": normalized_shape,
                "occurrence_count": 0,
                "document_ids": set(),
                "examples": [],
                "context_samples": [],
                "label_counts": {},
                "label_confidence_totals": {},
            },
        )

        cluster["occurrence_count"] += 1

        doc_id = str(
            candidate.get("doc_id") or ""
        ).strip()

        if doc_id:
            cluster["document_ids"].add(
                doc_id
            )

        detected_value = str(
            candidate.get("detected_value")
            or ""
        ).strip()

        if (
            detected_value
            and detected_value
            not in cluster["examples"]
            and len(cluster["examples"]) < 10
        ):
            cluster["examples"].append(
                detected_value
            )

        context_before = str(
            candidate.get("context_before")
            or ""
        ).strip()

        if (
            context_before
            and context_before
            not in cluster["context_samples"]
            and len(
                cluster["context_samples"]
            ) < 10
        ):
            cluster[
                "context_samples"
            ].append(context_before)
            
        inferred_label = str(
            candidate.get("inferred_label")
            or ""
        ).strip()

        try:
            inferred_label_confidence = float(
                candidate.get(
                    "inferred_label_confidence"
                )
                or 0.0
            )
        except (TypeError, ValueError):
            inferred_label_confidence = 0.0

        if inferred_label:
            cluster["label_counts"][
                inferred_label
            ] = (
                cluster["label_counts"].get(
                    inferred_label,
                    0,
                )
                + 1
            )

            cluster[
                "label_confidence_totals"
            ][inferred_label] = (
                cluster[
                    "label_confidence_totals"
                ].get(
                    inferred_label,
                    0.0,
                )
                + inferred_label_confidence
            )

    results: list[dict[str, Any]] = []

    for cluster in clusters.values():
        document_ids = sorted(
            cluster["document_ids"]
        )
        
        label_counts = dict(
            cluster.get("label_counts")
            or {}
        )

        suggested_label = ""
        suggested_label_confidence = 0.0
        suggested_label_occurrences = 0

        if label_counts:
            suggested_label = max(
                label_counts,
                key=lambda label: (
                    int(label_counts[label]),
                    float(
                        cluster[
                            "label_confidence_totals"
                        ].get(
                            label,
                            0.0,
                        )
                    ),
                ),
            )

            suggested_label_occurrences = int(
                label_counts.get(
                    suggested_label,
                    0,
                )
            )

            total_label_confidence = float(
                cluster[
                    "label_confidence_totals"
                ].get(
                    suggested_label,
                    0.0,
                )
            )

            if suggested_label_occurrences:
                average_label_confidence = (
                    total_label_confidence
                    / suggested_label_occurrences
                )

                agreement_ratio = (
                    suggested_label_occurrences
                    / max(
                        1,
                        int(
                            cluster[
                                "occurrence_count"
                            ]
                        ),
                    )
                )

                suggested_label_confidence = (
                    average_label_confidence
                    * agreement_ratio
                )

        results.append(
            {
                "cluster_key": (
                    cluster["cluster_key"]
                ),
                "normalized_shape": (
                    cluster["normalized_shape"]
                ),
                "occurrence_count": int(
                    cluster[
                        "occurrence_count"
                    ]
                ),
                "document_count": len(
                    document_ids
                ),
                "document_ids": document_ids,
                "examples": (
                    cluster["examples"]
                ),
                "context_samples": (
                    cluster[
                        "context_samples"
                    ]
                ),
                "suggested_label": (
                    suggested_label
                ),
                "suggested_label_confidence": round(
                    suggested_label_confidence,
                    4,
                ),
                "suggested_label_occurrences": (
                    suggested_label_occurrences
                ),
            }
        )

    results.sort(
        key=lambda item: (
            -int(
                item.get(
                    "document_count",
                    0,
                )
            ),
            -int(
                item.get(
                    "occurrence_count",
                    0,
                )
            ),
            str(
                item.get(
                    "normalized_shape",
                    "",
                )
            ),
        )
    )

    return results

def run_data_element_detection_job(
    *,
    db: LedgerDB,
    payload: dict[str, Any],
) -> dict[str, Any]:
    detection_job_id = str(
        payload.get("detection_job_id")
        or payload.get("job_id")
        or ""
    ).strip()

    if not detection_job_id:
        raise RuntimeError(
            "Detection queue payload is missing "
            "detection_job_id."
        )

    workspace = str(
        payload.get("workspace") or "capture"
    ).strip().lower()

    client_id = str(
        payload.get("client") or ""
    ).strip()

    project = str(
        payload.get("project") or ""
    ).strip()

    source_job_id = str(
        payload.get("source_job_id") or ""
    ).strip()

    if not client_id:
        raise RuntimeError(
            "Detection queue payload is missing client."
        )

    if not project:
        raise RuntimeError(
            "Detection queue payload is missing project."
        )

    if not source_job_id:
        raise RuntimeError(
            "Detection queue payload is missing "
            "source_job_id."
        )

    matter_id = str(
        payload.get("matter_id")
        or project
        or source_job_id
    ).strip()

    documents = payload.get("documents") or []

    if not isinstance(documents, list):
        raise RuntimeError(
            "Detection queue payload documents "
            "must be a list."
        )

    if not documents:
        raise RuntimeError(
            "Detection queue payload contains no documents."
        )

    db.init_schema()

    _seed_source_job(
        db,
        source_job_id=source_job_id,
        matter_id=matter_id,
        client_id=client_id,
        workspace=workspace,
    )

    local_root = (
        Path(
            os.getenv(
                "APC_DETECTION_ROOT",
                "/tmp/apc_detection_runs",
            )
        )
        / detection_job_id
    )

    text_dir = local_root / "text"

    downloaded_docs: list[dict[str, Any]] = []

    for doc in documents:
        if not isinstance(doc, dict):
            continue

        doc_id = str(
            doc.get("doc_id") or ""
        ).strip()

        text_blob_path = str(
            doc.get("text_staged_blob_path") or ""
        ).strip()

        if not doc_id or not text_blob_path:
            continue

        local_text_path = (
            text_dir / f"{doc_id}.txt"
        )

        _download_detection_text(
            workspace=workspace,
            blob_path=text_blob_path,
            destination=local_text_path,
        )

        file_id = _seed_detection_document(
            db,
            source_job_id=source_job_id,
            matter_id=matter_id,
            doc=doc,
            local_text_path=local_text_path,
        )

        downloaded_docs.append(
            {
                **doc,
                "file_id": file_id,
                "local_text_path": str(
                    local_text_path
                ),
            }
        )

    if not downloaded_docs:
        raise RuntimeError(
            "No staged detection text files could "
            "be prepared."
        )

    result = run_pii_phi_detection(
        db,
        source_job_id=source_job_id,
        matter_id=matter_id,
        client_id=client_id,
        workspace=workspace,
        protocol_name=payload.get(
            "protocol_name"
        ),
        protocol_version=payload.get(
            "protocol_version"
        ),
        include_phi=bool(
            payload.get("include_phi", True)
        ),
    )

    detection_run_id = str(
        result.get("detection_run_id") or ""
    )

    document_rows = [
        dict(row)
        for row in db.query(
            """
            SELECT *
            FROM processing_detection_document
            WHERE detection_run_id=?
            ORDER BY doc_id
            """,
            (detection_run_id,),
        )
    ]

    entity_rows = [
        dict(row)
        for row in db.query(
            """
            SELECT *
            FROM processing_detection_entity
            WHERE detection_run_id=?
            ORDER BY doc_id, start_offset
            """,
            (detection_run_id,),
        )
    ]

    entity_counts_rows = db.query(
        """
        SELECT
            entity_type,
            count(*) AS hit_count,
            count(DISTINCT doc_id) AS document_count
        FROM processing_detection_entity
        WHERE detection_run_id=?
        GROUP BY entity_type
        ORDER BY document_count DESC,
                 hit_count DESC,
                 entity_type
        """,
        (detection_run_id,),
    )

    entity_counts = [
        {
            "entity_type": row["entity_type"],
            "hit_count": int(
                row["hit_count"] or 0
            ),
            "document_count": int(
                row["document_count"] or 0
            ),
        }
        for row in entity_counts_rows
    ]

    project_base = (
        f"{client_id}/{workspace}/"
        f"{project.replace(' ', '_')}"
    )

    result_prefix = (
        f"{project_base}/processing_center/"
        f"detection/jobs/{detection_job_id}/results"
    )

    summary_payload = {
        **result,
        "job_type": "data_element_detection",
        "detection_job_id": detection_job_id,
        "workspace": workspace,
        "client": client_id,
        "project": project,
        "source_job_id": source_job_id,
        "protocol_name": payload.get(
            "protocol_name"
        ),
        "protocol_version": payload.get(
            "protocol_version"
        ),
        "include_phi": bool(
            payload.get("include_phi", True)
        ),
        "entity_type_counts": entity_counts,
        "completed_at": utc_now(),
    }

    summary_upload = _write_processing_json(
        f"{result_prefix}/summary.json",
        summary_payload,
    )

    documents_upload = _write_processing_json(
        f"{result_prefix}/documents.json",
        document_rows,
    )

    entities_upload = _write_processing_json(
        f"{result_prefix}/entities.json",
        entity_rows,
    )
    
    document_index_prefix = (
        f"{project_base}/processing_center/"
        f"detection/documents"
    )

    document_index_uploads: list[dict[str, Any]] = []

    entities_by_doc_id: dict[str, list[dict[str, Any]]] = {}

    for entity in entity_rows:
        entity_doc_id = str(
            entity.get("doc_id") or ""
        ).strip()

        if not entity_doc_id:
            continue

        entities_by_doc_id.setdefault(
            entity_doc_id,
            [],
        ).append(entity)
        
    local_text_paths_by_doc_id: dict[
        str,
        str,
    ] = {
        str(doc.get("doc_id") or "").strip(): str(
            doc.get("local_text_path") or ""
        ).strip()
        for doc in downloaded_docs
        if str(
            doc.get("doc_id") or ""
        ).strip()
    }

    all_generic_identifier_candidates: list[
        dict[str, Any]
    ] = []

    for document_row in document_rows:
        doc_id = str(
            document_row.get("doc_id") or ""
        ).strip()

        if not doc_id:
            continue

        document_entities = entities_by_doc_id.get(
            doc_id,
            [],
        )

        entity_type_counts: dict[str, int] = {}

        normalized_hits: list[dict[str, Any]] = []

        for entity in document_entities:
            entity_type = str(
                entity.get("entity_type")
                or entity.get("category")
                or ""
            ).strip()

            if entity_type:
                entity_type_counts[entity_type] = (
                    entity_type_counts.get(entity_type, 0) + 1
                )

            start_offset = entity.get("start_offset")

            if start_offset is None:
                start_offset = entity.get("offset")

            end_offset = entity.get("end_offset")
            length = entity.get("length")

            try:
                normalized_start = int(start_offset)
            except (TypeError, ValueError):
                continue

            if end_offset is not None:
                try:
                    normalized_end = int(end_offset)
                except (TypeError, ValueError):
                    continue

            elif length is not None:
                try:
                    normalized_end = (
                        normalized_start + int(length)
                    )
                except (TypeError, ValueError):
                    continue

            else:
                detected_value = str(
                    entity.get("detected_value")
                    or entity.get("text")
                    or ""
                )

                if not detected_value:
                    continue

                normalized_end = (
                    normalized_start + len(detected_value)
                )

            if normalized_start < 0:
                continue

            if normalized_end <= normalized_start:
                continue

            confidence_raw = (
                entity.get("confidence")
                if entity.get("confidence") is not None
                else entity.get("confidence_score")
            )

            try:
                confidence = (
                    float(confidence_raw)
                    if confidence_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                confidence = None

            normalized_hits.append(
                {
                    "entity_type": entity_type,
                    "entity_subtype": str(
                        entity.get("entity_subtype")
                        or entity.get("subcategory")
                        or ""
                    ).strip(),
                    "detected_value": str(
                        entity.get("detected_value")
                        or entity.get("text")
                        or ""
                    ),
                    "normalized_value": entity.get(
                        "normalized_value"
                    ),
                    "masked_value": entity.get(
                        "masked_value"
                    ),
                    "confidence": confidence,
                    "start_offset": normalized_start,
                    "end_offset": normalized_end,
                    "page_number": (
                        entity.get("page_number")
                        or entity.get("page")
                    ),
                    "detector": (
                        entity.get("detector")
                        or entity.get("detector_name")
                        or "azure_language"
                    ),
                    "detector_version": entity.get(
                        "detector_version"
                    ),
                    "rule_id": entity.get("rule_id"),
                    "protocol": (
                        entity.get("protocol")
                        or entity.get("protocol_name")
                        or payload.get("protocol_name")
                        or ""
                    ),
                    "protocol_version": (
                        entity.get("protocol_version")
                        or payload.get("protocol_version")
                        or ""
                    ),
                    "reportability": (
                        entity.get("reportability")
                        or "UNCLASSIFIED"
                    ),
                }
            )

        normalized_hits.sort(
            key=lambda hit: (
                int(hit.get("start_offset") or 0),
                int(hit.get("end_offset") or 0),
            )
        )
        
        local_text_path = (
            local_text_paths_by_doc_id.get(
                doc_id,
                "",
            )
        )

        generic_identifier_candidates: list[
            dict[str, Any]
        ] = []

        if local_text_path:
            try:
                detection_text = Path(
                    local_text_path
                ).read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

                generic_identifier_candidates = (
                    _find_generic_identifier_candidates(
                        detection_text,
                        normalized_hits,
                    )
                )

            except OSError:
                generic_identifier_candidates = []

        for candidate in generic_identifier_candidates:
            all_generic_identifier_candidates.append(
                {
                    **candidate,
                    "doc_id": doc_id,
                }
            )

        document_index_payload = {
            "schema_version": 1,
            "workspace": workspace,
            "client": client_id,
            "project": project,
            "doc_id": doc_id,
            "classification": (
                document_row.get("classification")
                or "PENDING"
            ),
            "detection_status": (
                document_row.get("status")
                or document_row.get("detection_status")
                or ""
            ),
            "hit_count": len(normalized_hits),
            "entity_type_counts": entity_type_counts,
            "source_job_id": source_job_id,
            "latest_detection_job_id": detection_job_id,
            "detection_run_id": detection_run_id,
            "protocol_name": payload.get(
                "protocol_name"
            ),
            "protocol_version": payload.get(
                "protocol_version"
            ),
            "include_phi": bool(
                payload.get("include_phi", True)
            ),
            "text_source": (
                document_row.get("text_source")
                or document_row.get("source_text_type")
                or ""
            ),
            "text_path": (
                document_row.get("text_path")
                or document_row.get("text_output_path")
                or ""
            ),
            "detected_at": (
                document_row.get("completed_at")
                or document_row.get("updated_at")
                or summary_payload.get("completed_at")
            ),
            "hits": normalized_hits,
            "generic_identifier_candidate_count": (
                len(generic_identifier_candidates)
            ),
            "generic_identifier_candidates": (
                generic_identifier_candidates
            ),
        }

        document_index_uploads.append(
            _write_processing_json(
                f"{document_index_prefix}/{doc_id}.json",
                document_index_payload,
            )
        )
        
    generic_identifier_clusters = (
        _build_generic_identifier_clusters(
            all_generic_identifier_candidates
        )
    )

    generic_identifier_clusters_upload = (
        _write_processing_json(
            (
                f"{result_prefix}/"
                "generic_identifier_clusters.json"
            ),
            {
                "schema_version": 1,
                "workspace": workspace,
                "client": client_id,
                "project": project,
                "detection_job_id": (
                    detection_job_id
                ),
                "detection_run_id": (
                    detection_run_id
                ),
                "candidate_count": len(
                    all_generic_identifier_candidates
                ),
                "cluster_count": len(
                    generic_identifier_clusters
                ),
                "clusters": (
                    generic_identifier_clusters
                ),
            },
        )
    )

    return {
        **summary_payload,
        "message": (
            "Data Element Detection completed."
        ),
        "result_prefix": result_prefix,
        "summary_blob_path": (
            summary_upload["blob_path"]
        ),
        "documents_blob_path": (
            documents_upload["blob_path"]
        ),
        "entities_blob_path": (
            entities_upload["blob_path"]
        ),
        "document_index_prefix": document_index_prefix,
        "document_index_count": len(document_index_uploads),
        "document_index_uploads": document_index_uploads,
        "documents": document_rows,
        "entity_type_counts": entity_counts,
        "generic_identifier_candidate_count": len(
            all_generic_identifier_candidates
        ),
        "generic_identifier_cluster_count": len(
            generic_identifier_clusters
        ),
        "generic_identifier_clusters_blob_path": (
            generic_identifier_clusters_upload[
                "blob_path"
            ]
        ),
        "generic_identifier_clusters": (
            generic_identifier_clusters
        ),
    }