from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .db import LedgerDB
from .util import bytes_to_gb


SMALL_SAMPLE_GB_THRESHOLD = 0.25


def latest_job_id(db: LedgerDB) -> str | None:
    row = db.query_one("SELECT job_id FROM processing_job ORDER BY created_at DESC LIMIT 1")
    return row["job_id"] if row else None


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def job_report_data(db: LedgerDB, job_id: str) -> dict[str, Any]:
    job = db.query_one("SELECT * FROM processing_job WHERE job_id=?", (job_id,))
    if job is None:
        raise ValueError(f"job not found: {job_id}")

    stage_rows = db.query(
        """
        SELECT stage_name, status, duration_ms, files_in, files_out, bytes_in, bytes_out,
               pages_in, pages_out, exceptions, retry_count, estimated_cost_usd, metrics_json
        FROM processing_stage_run
        WHERE job_id=?
        ORDER BY started_at
        """,
        (job_id,),
    )
    cost_rows = db.query(
        """
        SELECT azure_service, meter_name, unit_of_measure,
               sum(quantity) AS quantity, max(unit_price_usd) AS unit_price_usd,
               sum(estimated_cost_usd) AS estimated_cost_usd,
               min(confidence) AS confidence, cost_type
        FROM cost_event
        WHERE job_id=?
        GROUP BY azure_service, meter_name, unit_of_measure, cost_type
        ORDER BY estimated_cost_usd DESC
        """,
        (job_id,),
    )
    ocr = db.query_one(
        """
        SELECT count(*) AS candidate_files, coalesce(sum(page_count),0) AS pages,
               coalesce(sum(source_bytes),0) AS bytes
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND requires_ocr=1
        """,
        (job_id,),
    )
    container_rows = db.query(
        """
        SELECT container_path, original_container_path, container_depth, compressed_bytes,
               extracted_bytes, extracted_file_count, nested_container_count, status, exception_json
        FROM container_expansion_event
        WHERE job_id=?
        ORDER BY container_depth, container_path
        """,
        (job_id,),
    )
    promotion_rows = db.query(
        """
        SELECT doc_id, original_path, native_output_path, text_output_path, status, text_source, exception_json
        FROM review_promotion_event
        WHERE job_id=?
        ORDER BY doc_id
        """,
        (job_id,),
    )

    files = db.query(
        """
        SELECT doc_id, original_path, normalized_path, extension, source_bytes, expanded_bytes,
               page_count, text_bytes, has_native_text, requires_ocr, is_duplicate, duplicate_of_file_id,
               is_denisted, is_container, is_extracted, source_container_file_id, container_depth,
               container_path, family_id, parent_file_id, promoted_to_review, native_output_path, text_output_path, review_export_status, stage_status_json, md5, sha1, sha256
        FROM file_processing_metrics
        WHERE job_id=?
        ORDER BY doc_id, normalized_path
        """,
        (job_id,),
    )

    file_dicts = _rows_to_dicts(files)
    ocr_reason_counts: dict[str, int] = {}
    for f in file_dicts:
        try:
            status = json.loads(f.get("stage_status_json") or "{}")
            reason = status.get("ocr_preflight", {}).get("reason")
            if reason:
                ocr_reason_counts[reason] = ocr_reason_counts.get(reason, 0) + 1
        except Exception:
            pass

    promoted_docs = len([r for r in promotion_rows if r["status"] == "promoted"])
    promotion_failures = len([r for r in promotion_rows if r["status"] != "promoted"])

    source_bytes = int(job["source_bytes"] or 0)
    source_gb = bytes_to_gb(source_bytes)
    unique_docs = int(job["unique_doc_count"] or 0)
    duplicate_docs = int(job["duplicate_doc_count"] or 0)
    denist_docs = int(job["denist_suppressed_count"] or 0)
    source_file_count = int(job["source_file_count"] or 0)
    ocr_pages = int(ocr["pages"] or 0) if ocr else 0
    ocr_candidate_files = int(ocr["candidate_files"] or 0) if ocr else 0
    ocr_candidate_bytes = int(ocr["bytes"] or 0) if ocr else 0
    total_cost = float(job["estimated_azure_cost_usd"] or 0)

    ocr_cost = float(
        db.scalar(
            """
            SELECT coalesce(sum(estimated_cost_usd),0)
            FROM cost_event
            WHERE job_id=? AND lower(azure_service) LIKE '%document%' AND lower(meter_name) LIKE '%read%'
            """,
            (job_id,),
        )
        or 0
    )
    non_ocr_cost = max(0.0, total_cost - ocr_cost)
    duplicate_pct = duplicate_docs / max(1, unique_docs + duplicate_docs) * 100
    denist_pct = denist_docs / max(1, source_file_count) * 100
    ocr_pages_per_gb = ocr_pages / source_gb if source_gb > 0 else 0
    ocr_cost_pct = ocr_cost / total_cost * 100 if total_cost > 0 else 0
    ocr_candidate_gb = bytes_to_gb(ocr_candidate_bytes)
    expanded_bytes = int(job["expanded_bytes"] or 0)
    expanded_gb = bytes_to_gb(expanded_bytes)
    expanded_file_count = int(job["expanded_file_count"] or 0)
    container_file_count = int(job["container_file_count"] or 0)
    extracted_file_count = int(job["extracted_file_count"] or 0)
    container_exception_count = int(job["container_exception_count"] or 0)
    max_container_depth = int(job["max_container_depth"] or 0)
    expansion_ratio = float(job["expansion_ratio"] or 1.0)
    cost_per_expanded_gb = total_cost / expanded_gb if expanded_gb > 0 else 0
    ocr_pages_per_expanded_gb = ocr_pages / expanded_gb if expanded_gb > 0 else 0

    # Simple default pricing guidance. This is intentionally a starting range, not a quote.
    # For compressed container matters, expanded GB is usually a more stable OCR-density basis.
    base_processing_low = 25.0
    base_processing_high = 35.0
    pricing_density = ocr_pages_per_expanded_gb if expansion_ratio > 2.0 and expanded_gb > 0 else ocr_pages_per_gb
    pricing_basis = "expanded GB" if expansion_ratio > 2.0 and expanded_gb > 0 else "source GB"
    if pricing_density >= 5000:
        recommended_low, recommended_high = 45.0, 65.0
        pricing_note = f"OCR-heavy profile based on OCR pages per {pricing_basis}."
    elif pricing_density >= 1000:
        recommended_low, recommended_high = 35.0, 50.0
        pricing_note = f"Mixed OCR profile based on OCR pages per {pricing_basis}."
    else:
        recommended_low, recommended_high = base_processing_low, base_processing_high
        pricing_note = f"Low-OCR profile based on OCR pages per {pricing_basis}."

    return {
        "job": dict(job),
        "source": {
            "source_gb": source_gb,
            "duplicate_pct": duplicate_pct,
            "denist_pct": denist_pct,
            "small_sample_warning": source_gb < SMALL_SAMPLE_GB_THRESHOLD,
        },
        "containers": {
            "container_file_count": container_file_count,
            "extracted_file_count": extracted_file_count,
            "expanded_file_count": expanded_file_count,
            "expanded_bytes": expanded_bytes,
            "expanded_gb": expanded_gb,
            "expansion_ratio": expansion_ratio,
            "container_exception_count": container_exception_count,
            "max_container_depth": max_container_depth,
            "events": _rows_to_dicts(container_rows),
        },
        "ocr": {
            "candidate_files": ocr_candidate_files,
            "estimated_pages": ocr_pages,
            "candidate_bytes": ocr_candidate_bytes,
            "candidate_gb": ocr_candidate_gb,
            "pages_per_source_gb": ocr_pages_per_gb,
            "pages_per_expanded_gb": ocr_pages_per_expanded_gb,
            "reason_counts": ocr_reason_counts,
            "estimated_cost_usd": ocr_cost,
            "cost_pct_of_total": ocr_cost_pct,
            "cost_per_page": (ocr_cost / ocr_pages) if ocr_pages > 0 else 0,
        },
        "cost": {
            "total_estimated_azure_cost_usd": total_cost,
            "non_ocr_estimated_cost_usd": non_ocr_cost,
            "cost_per_source_gb": float(job["effective_cost_per_source_gb"] or 0),
            "cost_per_expanded_gb": cost_per_expanded_gb,
            "cost_per_unique_doc": float(job["effective_cost_per_unique_doc"] or 0),
            "cost_per_ocr_page": float(job["effective_cost_per_ocr_page"] or 0),
        },
        "review_promotion": {
            "promoted_docs": promoted_docs,
            "promotion_failures": promotion_failures,
            "events": _rows_to_dicts(promotion_rows),
        },
        "pricing_guidance": {
            "recommended_client_low_per_source_gb": recommended_low,
            "recommended_client_high_per_source_gb": recommended_high,
            "note": pricing_note,
        },
        "stages": _rows_to_dicts(stage_rows),
        "cost_events_by_meter": _rows_to_dicts(cost_rows),
        "files": file_dicts,
    }


def job_cost_report(db: LedgerDB, job_id: str) -> str:
    data = job_report_data(db, job_id)
    job = data["job"]
    source = data["source"]
    containers = data["containers"]
    ocr = data["ocr"]
    cost = data["cost"]
    promotion = data["review_promotion"]
    pricing = data["pricing_guidance"]

    lines = []
    lines.append("Azure Processing Center Job Cost Report")
    lines.append(f"Job: {job['job_id']}")
    lines.append(f"Matter: {job['matter_id']}")
    lines.append(f"Client: {job['client_id']}")
    lines.append(f"Status: {job['status']}")
    if source["small_sample_warning"]:
        lines.append("Sample warning: source data is under 0.25 GB, so per-GB metrics may be volatile.")
    lines.append("")
    lines.append("Source Data")
    lines.append(f"- Source files: {int(job['source_file_count']):,}")
    lines.append(f"- Source bytes: {int(job['source_bytes']):,} ({source['source_gb']:.6f} GB)")
    lines.append(f"- Unique docs: {int(job['unique_doc_count']):,}")
    lines.append(f"- Duplicate docs: {int(job['duplicate_doc_count']):,} ({source['duplicate_pct']:.2f}%)")
    lines.append(f"- deNIST suppressed: {int(job['denist_suppressed_count']):,} ({source['denist_pct']:.2f}%)")
    lines.append(f"- Exceptions: {int(job['exception_count']):,}")
    lines.append("")
    lines.append("Container Expansion")
    lines.append(f"- Container files expanded: {containers['container_file_count']:,}")
    lines.append(f"- Extracted files: {containers['extracted_file_count']:,}")
    lines.append(f"- Expanded leaf files: {containers['expanded_file_count']:,}")
    lines.append(f"- Expanded bytes: {containers['expanded_bytes']:,} ({containers['expanded_gb']:.6f} GB)")
    lines.append(f"- Expansion ratio: {containers['expansion_ratio']:.2f}x")
    lines.append(f"- Max container depth: {containers['max_container_depth']:,}")
    lines.append(f"- Container exceptions: {containers['container_exception_count']:,}")
    lines.append("")
    lines.append("OCR")
    lines.append(f"- OCR candidate files: {ocr['candidate_files']:,}")
    lines.append(f"- OCR estimated pages: {ocr['estimated_pages']:,}")
    lines.append(f"- OCR candidate bytes: {ocr['candidate_bytes']:,} ({ocr['candidate_gb']:.6f} GB)")
    lines.append(f"- OCR pages / source GB: {ocr['pages_per_source_gb']:,.2f}")
    lines.append(f"- OCR pages / expanded GB: {ocr['pages_per_expanded_gb']:,.2f}")
    lines.append(f"- OCR estimated cost: ${ocr['estimated_cost_usd']:,.6f}")
    lines.append(f"- OCR % of Azure estimate: {ocr['cost_pct_of_total']:.2f}%")
    if ocr["reason_counts"]:
        lines.append("- OCR reason counts:")
        for reason, count in sorted(ocr["reason_counts"].items()):
            lines.append(f"  - {reason}: {count:,}")
    lines.append("")
    lines.append("Azure Hard-Cost Estimate")
    lines.append(f"- Total estimated Azure cost: ${cost['total_estimated_azure_cost_usd']:,.6f}")
    lines.append(f"- Non-OCR estimated Azure cost: ${cost['non_ocr_estimated_cost_usd']:,.6f}")
    lines.append(f"- Cost / source GB: ${cost['cost_per_source_gb']:,.6f}")
    lines.append(f"- Cost / expanded GB: ${cost['cost_per_expanded_gb']:,.6f}")
    lines.append(f"- Cost / unique doc: ${cost['cost_per_unique_doc']:,.6f}")
    lines.append(f"- Cost / OCR page: ${cost['cost_per_ocr_page']:,.6f}")
    lines.append("")
    lines.append("Review-Ready Promotion")
    lines.append(f"- Promoted docs: {promotion['promoted_docs']:,}")
    lines.append(f"- Promotion failures: {promotion['promotion_failures']:,}")
    if promotion["events"]:
        first = promotion["events"][0]
        lines.append(f"- Example native output: {first['native_output_path']}")
        lines.append(f"- Example text output: {first['text_output_path']}")
    lines.append("")
    lines.append("Client Pricing Guidance")
    lines.append(
        f"- Recommended range: ${pricing['recommended_client_low_per_source_gb']:,.2f}"
        f"–${pricing['recommended_client_high_per_source_gb']:,.2f} / source GB"
    )
    lines.append(f"- Basis: {pricing['note']}")
    lines.append("")
    lines.append("Stage Breakdown")
    for s in data["stages"]:
        lines.append(
            f"- {s['stage_name']}: {s['status']}; {s['duration_ms']} ms; "
            f"files {int(s['files_in']):,}->{int(s['files_out']):,}; "
            f"pages {int(s['pages_in']):,}->{int(s['pages_out']):,}; "
            f"exceptions {int(s['exceptions']):,}; est ${float(s['estimated_cost_usd'] or 0):.6f}"
        )
    lines.append("")
    lines.append("Cost Events by Azure Meter")
    for c in data["cost_events_by_meter"]:
        lines.append(
            f"- {c['azure_service']} / {c['meter_name']}: "
            f"qty {float(c['quantity'] or 0):,.4f} {c['unit_of_measure']}; "
            f"unit ${float(c['unit_price_usd'] or 0):.8f}; "
            f"est ${float(c['estimated_cost_usd'] or 0):.6f}; "
            f"confidence {c['confidence']}; type {c['cost_type']}"
        )
    return "\n".join(lines)


def export_job_report(db: LedgerDB, job_id: str, out_dir: str) -> dict[str, str]:
    data = job_report_data(db, job_id)
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    base = output / job_id

    json_path = base.with_suffix(".summary.json")
    txt_path = base.with_suffix(".summary.txt")
    stage_csv_path = base.with_suffix(".stages.csv")
    meter_csv_path = base.with_suffix(".cost_events_by_meter.csv")
    file_csv_path = base.with_suffix(".files.csv")
    containers_csv_path = base.with_suffix(".containers.csv")
    promotion_csv_path = base.with_suffix(".review_promotion.csv")

    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    txt_path.write_text(job_cost_report(db, job_id), encoding="utf-8")

    def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(stage_csv_path, data["stages"])
    write_csv(meter_csv_path, data["cost_events_by_meter"])
    write_csv(file_csv_path, data["files"])
    write_csv(containers_csv_path, data["containers"]["events"])
    write_csv(promotion_csv_path, data["review_promotion"]["events"])

    return {
        "summary_json": str(json_path),
        "summary_txt": str(txt_path),
        "stages_csv": str(stage_csv_path),
        "cost_events_by_meter_csv": str(meter_csv_path),
        "files_csv": str(file_csv_path),
        "containers_csv": str(containers_csv_path),
        "review_promotion_csv": str(promotion_csv_path),
    }
