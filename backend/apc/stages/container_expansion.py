from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path, PurePosixPath

from ..config import Settings
from ..db import LedgerDB
from ..telemetry import StageRunner
from ..util import normalize_path, new_id, utc_now, json_dumps


ZIP_EXTENSIONS = {"zip"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
MAX_CONTAINER_DEPTH = 8


def _safe_member_path(member_name: str) -> Path | None:
    # Normalize ZIP member names and block absolute/parent traversal paths.
    pure = PurePosixPath(member_name.replace("\\", "/"))
    if pure.is_absolute():
        return None
    parts = [p for p in pure.parts if p not in {"", "."}]
    if not parts or any(p == ".." for p in parts):
        return None
    return Path(*parts)


def _unique_child_path(base: Path, rel: Path) -> Path:
    candidate = base / rel
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    n = 2
    while True:
        alt = parent / f"{stem}__{n}{suffix}"
        if not alt.exists():
            return alt
        n += 1


def _is_zip_extension(extension: str | None) -> bool:
    return (extension or "").lower().lstrip(".") in ZIP_EXTENSIONS


def run_container_expansion(
    db: LedgerDB,
    settings: Settings,
    job_id: str,
    matter_id: str,
    input_dir: str,
    max_depth: int = MAX_CONTAINER_DEPTH,
) -> None:
    """Expand ZIP containers locally and ledger expansion telemetry.

    v0.4 intentionally supports ZIP/nested ZIP only. The stage does not upload data
    anywhere. Extracted files are placed under <input_parent>/.apc_expanded/<job_id>/.
    Successfully expanded ZIP rows are marked is_container=1 so downstream stages
    hash/dedupe/Doc-ID only the extracted leaf files plus normal non-container files.
    """
    root = Path(input_dir).resolve()
    expansion_root = root.parent / ".apc_expanded" / job_id
    expansion_root.mkdir(parents=True, exist_ok=True)

    initial_rows = db.query(
        """
        SELECT file_id, original_path, normalized_path, extension, source_bytes,
               source_container_file_id, container_depth, is_container
        FROM file_processing_metrics
        WHERE job_id=? AND is_container=0 AND lower(coalesce(extension,''))='zip'
        ORDER BY normalized_path
        """,
        (job_id,),
    )

    with StageRunner(db, settings, job_id, matter_id, "container_expansion", "local-zip-expander") as stage:
        stage.metrics.files_in = len(initial_rows)
        stage.metrics.documents_in = len(initial_rows)
        stage.metrics.bytes_in = sum(int(r["source_bytes"] or 0) for r in initial_rows)

        queue = list(initial_rows)
        expanded_container_count = 0
        extracted_file_count = 0
        nested_container_count = 0
        extracted_bytes_total = 0
        max_seen_depth = 0
        exceptions: list[dict] = []
        expansion_events = 0

        while queue:
            row = queue.pop(0)
            file_id = row["file_id"]
            container_depth = int(row["container_depth"] or 0)
            max_seen_depth = max(max_seen_depth, container_depth)
            container_path = Path(row["original_path"])
            compressed_bytes = int(row["source_bytes"] or 0)
            parent_container_file_id = row["source_container_file_id"]

            event_status = "completed"
            event_exceptions: list[dict] = []
            event_extracted_files = 0
            event_extracted_bytes = 0
            event_nested_count = 0

            if container_depth >= max_depth:
                event_status = "skipped_max_depth"
                event_exceptions.append({"error": f"max container depth {max_depth} reached"})
            else:
                try:
                    with zipfile.ZipFile(container_path) as zf:
                        bad = zf.testzip()
                        if bad:
                            event_status = "completed_with_warnings"
                            event_exceptions.append({"warning": f"zip CRC issue first bad member: {bad}"})
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            safe_rel = _safe_member_path(member.filename)
                            if safe_rel is None or safe_rel.name in SKIP_NAMES:
                                continue
                            child_base = expansion_root / file_id
                            child_path = _unique_child_path(child_base, safe_rel)
                            child_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, child_path.open("wb") as dst:
                                while True:
                                    chunk = src.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    dst.write(chunk)
                            stat_size = child_path.stat().st_size
                            ext = child_path.suffix.lower().lstrip(".")
                            mime_type, _ = mimetypes.guess_type(child_path.name)
                            child_file_id = new_id("FILE")
                            logical_path = f"{row['normalized_path']}!/{safe_rel.as_posix()}"
                            now = utc_now()
                            db.execute(
                                """
                                INSERT INTO file_processing_metrics (
                                    file_id, matter_id, job_id, custodian_id, original_path, normalized_path,
                                    extension, mime_type, source_bytes, expanded_bytes, is_container, is_extracted,
                                    source_container_file_id, container_depth, container_path, created_at, updated_at
                                )
                                SELECT ?, matter_id, job_id, custodian_id, ?, ?, ?, ?, ?, ?, 0, 1,
                                       ?, ?, ?, ?, ?
                                FROM file_processing_metrics WHERE file_id=?
                                """,
                                (
                                    child_file_id,
                                    str(child_path),
                                    logical_path,
                                    ext,
                                    mime_type or "application/octet-stream",
                                    stat_size,
                                    stat_size,
                                    file_id,
                                    container_depth + 1,
                                    row["normalized_path"],
                                    now,
                                    now,
                                    file_id,
                                ),
                            )
                            event_extracted_files += 1
                            event_extracted_bytes += stat_size
                            extracted_file_count += 1
                            extracted_bytes_total += stat_size
                            if _is_zip_extension(ext):
                                nested_container_count += 1
                                event_nested_count += 1
                                queue.append(
                                    {
                                        "file_id": child_file_id,
                                        "original_path": str(child_path),
                                        "normalized_path": logical_path,
                                        "extension": ext,
                                        "source_bytes": stat_size,
                                        "source_container_file_id": file_id,
                                        "container_depth": container_depth + 1,
                                        "is_container": 0,
                                    }
                                )
                except Exception as exc:  # noqa: BLE001 - record and continue.
                    event_status = "failed"
                    event_exceptions.append({"error": repr(exc)})

            if event_status in {"completed", "completed_with_warnings"}:
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET is_container=1, updated_at=?, stage_status_json=json_patch(stage_status_json, ?)
                    WHERE file_id=?
                    """,
                    (
                        utc_now(),
                        json_dumps(
                            {
                                "container_expansion": {
                                    "status": event_status,
                                    "extracted_files": event_extracted_files,
                                    "extracted_bytes": event_extracted_bytes,
                                }
                            }
                        ),
                        file_id,
                    ),
                )
                expanded_container_count += 1
            else:
                # Failed/skipped ZIP stays reviewable as a leaf file so it can be exception coded later.
                exceptions.append({"file_id": file_id, "path": str(container_path), "status": event_status, "details": event_exceptions})
                db.execute(
                    """
                    UPDATE file_processing_metrics
                    SET updated_at=?, exception_json=json_patch(exception_json, ?), stage_status_json=json_patch(stage_status_json, ?)
                    WHERE file_id=?
                    """,
                    (
                        utc_now(),
                        json_dumps(event_exceptions),
                        json_dumps({"container_expansion": {"status": event_status}}),
                        file_id,
                    ),
                )

            db.execute(
                """
                INSERT INTO container_expansion_event (
                    event_id, matter_id, job_id, source_file_id, parent_container_file_id,
                    container_path, original_container_path, container_depth, compressed_bytes,
                    extracted_bytes, extracted_file_count, nested_container_count, status,
                    exception_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("EXPAND"),
                    matter_id,
                    job_id,
                    file_id,
                    parent_container_file_id,
                    row["normalized_path"],
                    str(container_path),
                    container_depth,
                    compressed_bytes,
                    event_extracted_bytes,
                    event_extracted_files,
                    event_nested_count,
                    event_status,
                    json_dumps(event_exceptions),
                    utc_now(),
                ),
            )
            expansion_events += 1

        leaf = db.query_one(
            """
            SELECT count(*) AS leaf_files, coalesce(sum(source_bytes),0) AS leaf_bytes
            FROM file_processing_metrics
            WHERE job_id=? AND is_container=0
            """,
            (job_id,),
        )
        source = db.query_one("SELECT source_bytes FROM processing_job WHERE job_id=?", (job_id,))
        source_bytes = int(source["source_bytes"] or 0) if source else 0
        expanded_bytes = int(leaf["leaf_bytes"] or 0) if leaf else 0
        leaf_files = int(leaf["leaf_files"] or 0) if leaf else 0
        expansion_ratio = (expanded_bytes / source_bytes) if source_bytes else 1.0

        # Blob transaction proxies: local extracted writes plus source reads.
        if extracted_file_count:
            stage.quote_cost("Storage", "Blob Write Operations", extracted_file_count, "operations", confidence_note="proxy for extracted object writes")
        if expansion_events:
            stage.quote_cost("Storage", "Blob Read Operations", expansion_events, "operations", confidence_note="proxy for container reads")

        stage.metrics.files_in = expansion_events
        stage.metrics.documents_in = expansion_events
        stage.metrics.files_out = leaf_files
        stage.metrics.documents_out = leaf_files
        stage.metrics.bytes_out = expanded_bytes
        stage.metrics.exceptions = len(exceptions)
        stage.metrics.extra.update(
            {
                "expansion_root": str(expansion_root),
                "expanded_container_count": expanded_container_count,
                "extracted_file_count": extracted_file_count,
                "nested_container_count": nested_container_count,
                "extracted_bytes_total": extracted_bytes_total,
                "expanded_leaf_file_count": leaf_files,
                "expanded_leaf_bytes": expanded_bytes,
                "expansion_ratio": expansion_ratio,
                "max_container_depth": max_seen_depth,
                "container_exceptions": exceptions[:50],
                "supported_containers": sorted(ZIP_EXTENSIONS),
            }
        )

        db.execute(
            """
            UPDATE processing_job
            SET compressed_source_bytes=?, expanded_bytes=?, expanded_file_count=?,
                container_file_count=?, extracted_file_count=?, container_exception_count=?,
                max_container_depth=?, expansion_ratio=?, processed_bytes=?
            WHERE job_id=?
            """,
            (
                source_bytes,
                expanded_bytes,
                leaf_files,
                expanded_container_count,
                extracted_file_count,
                len(exceptions),
                max_seen_depth,
                expansion_ratio,
                expanded_bytes,
                job_id,
            ),
        )
