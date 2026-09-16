from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .azure_layout import AzureRoutingConfig, build_review_promotion_blob_plan, build_azure_routing_summary
from .db import LedgerDB
from .reports import latest_job_id
from .util import utc_now


class AzureDependencyError(RuntimeError):
    pass


def _load_azure_sdk():
    try:
        from azure.storage.blob import BlobServiceClient, ContentSettings  # type: ignore
        from azure.identity import DefaultAzureCredential  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional Azure packages
        raise AzureDependencyError(
            "Azure SDK packages are not installed. Run: pip install -e .[azure] "
            "or pip install azure-storage-blob azure-identity"
        ) from exc
    return BlobServiceClient, ContentSettings, DefaultAzureCredential


@dataclass(frozen=True)
class BlobItem:
    name: str
    size: int
    last_modified: str
    content_type: str = ""


class DualStorageBlobAdapter:
    """Two-account Blob adapter.

    Processing reads/staging use insytprodstorage. Review outputs are written to
    insytreviewstorage. In production, prefer DefaultAzureCredential/managed identity.
    For local tests, connection strings can be provided through environment variables.
    """

    def __init__(self, routing: AzureRoutingConfig):
        self.routing = routing
        BlobServiceClient, ContentSettings, DefaultAzureCredential = _load_azure_sdk()
        self._content_settings_cls = ContentSettings

        processing_conn = os.getenv("INSYT_PROCESSING_STORAGE_CONNECTION_STRING")
        review_conn = os.getenv("INSYT_REVIEW_STORAGE_CONNECTION_STRING")

        if processing_conn:
            self.processing_service = BlobServiceClient.from_connection_string(processing_conn)
        else:
            cred = DefaultAzureCredential()
            self.processing_service = BlobServiceClient(
                account_url=f"https://{routing.processing_account}.blob.core.windows.net",
                credential=cred,
            )

        if review_conn:
            self.review_service = BlobServiceClient.from_connection_string(review_conn)
        else:
            cred = DefaultAzureCredential()
            self.review_service = BlobServiceClient(
                account_url=f"https://{routing.review_account}.blob.core.windows.net",
                credential=cred,
            )

        self.processing_container = self.processing_service.get_container_client(routing.processing_container)
        self.review_container = self.review_service.get_container_client(routing.review_container)

    def list_processing_uploads(self, prefix: str | None = None) -> list[BlobItem]:
        upload_prefix = prefix or self.routing.processing_paths()["uploads"]
        rows: list[BlobItem] = []
        for blob in self.processing_container.list_blobs(name_starts_with=upload_prefix):
            if str(blob.name).endswith("/"):
                continue
            props = getattr(blob, "content_settings", None)
            rows.append(
                BlobItem(
                    name=blob.name,
                    size=int(getattr(blob, "size", 0) or 0),
                    last_modified=str(getattr(blob, "last_modified", "") or ""),
                    content_type=str(getattr(props, "content_type", "") or ""),
                )
            )
        return rows

    def download_processing_uploads(self, destination_root: str, prefix: str | None = None, overwrite: bool = False) -> list[dict[str, object]]:
        dest = Path(destination_root)
        dest.mkdir(parents=True, exist_ok=True)
        upload_prefix = (prefix or self.routing.processing_paths()["uploads"]).rstrip("/") + "/"
        downloaded: list[dict[str, object]] = []
        for item in self.list_processing_uploads(prefix=upload_prefix.rstrip("/")):
            rel = item.name[len(upload_prefix):] if item.name.startswith(upload_prefix) else Path(item.name).name
            local_path = dest / rel.replace("/", os.sep)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if local_path.exists() and not overwrite:
                status = "skipped_exists"
            else:
                data = self.processing_container.download_blob(item.name).readall()
                local_path.write_bytes(data)
                status = "downloaded"
            downloaded.append({
                "blob_name": item.name,
                "local_path": str(local_path),
                "size": item.size,
                "status": status,
            })
        return downloaded
    
    def archive_processing_uploads(
        self,
        job_id: str,
        uploads: list[dict[str, object]] | None = None,
        blob_names: list[str] | None = None,
        delete_original: bool = True,
    ) -> dict[str, object]:
        """Archive pending Processing Center uploads after a successful worker run.

        Files are copied from:
            {client}/{workspace}/{project_storage_key}/source/processing_center/uploads/

        to:
            {client}/{workspace}/{project_storage_key}/processing_center/archive/{job_id}/uploads/

        Then the original pending upload is deleted when delete_original=True.
        """

        upload_prefix = self.routing.processing_paths()["uploads"].rstrip("/") + "/"
        archive_prefix = (
            f"{self.routing.prefix}/processing_center/archive/"
            f"{job_id}/uploads"
        ).rstrip("/") + "/"

        names: list[str] = []

        for item in uploads or []:
            blob_name = str(item.get("blob_name") or "").strip()
            if blob_name:
                names.append(blob_name)

        for blob_name in blob_names or []:
            clean_name = str(blob_name or "").strip()
            if clean_name:
                names.append(clean_name)

        # Preserve order while removing duplicates.
        unique_names = list(dict.fromkeys(names))

        archived: list[dict[str, object]] = []

        for source_blob_name in unique_names:
            if not source_blob_name.startswith(upload_prefix):
                archived.append(
                    {
                        "source_blob_path": source_blob_name,
                        "status": "skipped_not_processing_upload",
                    }
                )
                continue

            relative_name = source_blob_name[len(upload_prefix):].lstrip("/")
            destination_blob_name = f"{archive_prefix}{relative_name}"

            source_blob = self.processing_container.get_blob_client(
                source_blob_name
            )
            destination_blob = self.processing_container.get_blob_client(
                destination_blob_name
            )

            try:
                props = source_blob.get_blob_properties()
                content_settings = getattr(props, "content_settings", None)

                stream = source_blob.download_blob()

                destination_blob.upload_blob(
                    stream.chunks(),
                    overwrite=True,
                    content_settings=content_settings,
                )

                deleted = False
                if delete_original:
                    source_blob.delete_blob()
                    deleted = True

                archived.append(
                    {
                        "source_blob_path": source_blob_name,
                        "archive_blob_path": destination_blob_name,
                        "status": "archived",
                        "deleted_original": deleted,
                        "bytes": int(getattr(props, "size", 0) or 0),
                    }
                )
            except Exception as exc:
                archived.append(
                    {
                        "source_blob_path": source_blob_name,
                        "archive_blob_path": destination_blob_name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        failed_count = sum(
            1 for item in archived if item.get("status") == "failed"
        )

        return {
            "status": "completed" if failed_count == 0 else "completed_with_errors",
            "job_id": job_id,
            "source_prefix": upload_prefix,
            "archive_prefix": archive_prefix,
            "archived_count": sum(
                1 for item in archived if item.get("status") == "archived"
            ),
            "failed_count": failed_count,
            "items": archived,
        }

    def upload_review_promotion_outputs(
        self,
        promotion_plan: list[dict[str, object]],
        local_review_root: str,
        job_id: str,
        overwrite: bool = False,
        promote_to_source: bool = False,
    ) -> list[dict[str, object]]:
        """Upload review-ready Native/Text pairs.

        Default professional APC behavior is staged output:

            {client}/{workspace}/{project_storage_key}/processing_center/staged/{job_id}/native/
            {client}/{workspace}/{project_storage_key}/processing_center/staged/{job_id}/text/

        Final project source promotion happens later through an explicit admin
        promotion action, which copies selected staged pairs into:

            {client}/{workspace}/{project_storage_key}/source/native/
            {client}/{workspace}/{project_storage_key}/source/text/
        """

        root = Path(local_review_root)
        results: list[dict[str, object]] = []

        staged_prefix = (
            f"{self.routing.prefix}/processing_center/staged/{job_id}"
        ).rstrip("/")

        for row in promotion_plan:
            doc_id = str(row["doc_id"])
            ext = str(row.get("extension") or "bin").lstrip(".") or "bin"

            local_native = root / "source" / "native" / f"{doc_id}.{ext}"
            local_text = root / "source" / "text" / f"{doc_id}.txt"

            if promote_to_source:
                native_blob_path = str(row["native_blob_path"])
                text_blob_path = str(row["text_blob_path"])
                destination_mode = "source"
            else:
                native_blob_path = f"{staged_prefix}/native/{doc_id}.{ext}"
                text_blob_path = f"{staged_prefix}/text/{doc_id}.txt"
                destination_mode = "staged"

            for kind, local_path, blob_path in (
                ("native", local_native, native_blob_path),
                ("text", local_text, text_blob_path),
            ):
                if not local_path.exists():
                    results.append(
                        {
                            "doc_id": doc_id,
                            "kind": kind,
                            "local_path": str(local_path),
                            "blob_path": blob_path,
                            "status": "missing_local_file",
                            "bytes": 0,
                            "destination_mode": destination_mode,
                            "final_source_blob_path": (
                                str(row["native_blob_path"])
                                if kind == "native"
                                else str(row["text_blob_path"])
                            ),
                        }
                    )
                    continue

                content_type = (
                    "text/plain; charset=utf-8"
                    if kind == "text"
                    else "application/octet-stream"
                )

                blob_client = self.review_container.get_blob_client(blob_path)

                with local_path.open("rb") as fh:
                    blob_client.upload_blob(
                        fh,
                        overwrite=overwrite,
                        content_settings=self._content_settings_cls(
                            content_type=content_type
                        ),
                    )

                results.append(
                    {
                        "doc_id": doc_id,
                        "kind": kind,
                        "local_path": str(local_path),
                        "blob_path": blob_path,
                        "status": "uploaded",
                        "bytes": local_path.stat().st_size,
                        "destination_mode": destination_mode,
                        "final_source_blob_path": (
                            str(row["native_blob_path"])
                            if kind == "native"
                            else str(row["text_blob_path"])
                        ),
                    }
                )

        return results

    def upload_report_file(self, local_path: str, blob_path: str, overwrite: bool = True) -> dict[str, object]:
        path = Path(local_path)
        blob_client = self.review_container.get_blob_client(blob_path)
        with path.open("rb") as fh:
            blob_client.upload_blob(fh, overwrite=overwrite)
        return {"local_path": str(path), "blob_path": blob_path, "bytes": path.stat().st_size, "status": "uploaded"}


def export_json(path: str | Path, payload: object) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(p)


def azure_list_uploads(routing: AzureRoutingConfig, export_dir: str | None = None) -> list[dict[str, object]]:
    adapter = DualStorageBlobAdapter(routing)
    items = adapter.list_processing_uploads()
    rows = [item.__dict__ for item in items]
    if export_dir:
        export_json(Path(export_dir) / "azure_processing_uploads.json", {"generated_at": utc_now(), "uploads": rows})
    return rows


def azure_download_uploads(routing: AzureRoutingConfig, destination_root: str, overwrite: bool = False, export_dir: str | None = None) -> list[dict[str, object]]:
    adapter = DualStorageBlobAdapter(routing)
    rows = adapter.download_processing_uploads(destination_root, overwrite=overwrite)
    if export_dir:
        export_json(Path(export_dir) / "azure_processing_downloads.json", {"generated_at": utc_now(), "downloads": rows})
    return rows

def azure_archive_processing_uploads(
    routing: AzureRoutingConfig,
    job_id: str,
    uploads: list[dict[str, object]] | None = None,
    blob_names: list[str] | None = None,
    delete_original: bool = True,
    export_dir: str | None = None,
) -> dict[str, object]:
    adapter = DualStorageBlobAdapter(routing)

    payload = adapter.archive_processing_uploads(
        job_id=job_id,
        uploads=uploads,
        blob_names=blob_names,
        delete_original=delete_original,
    )

    payload["generated_at"] = utc_now()

    if export_dir:
        export_json(
            Path(export_dir) / f"{job_id}.azure_archive_uploads.json",
            payload,
        )

    return payload

def azure_upload_review_outputs(
    db: LedgerDB,
    routing: AzureRoutingConfig,
    job_id: str,
    local_review_root: str,
    azure_write: bool,
    overwrite: bool = False,
    export_dir: str | None = None,
) -> dict[str, object]:
    if not azure_write:
        raise ValueError("Refusing to write to Azure because --azure-write was not passed.")
    expected_review_account = os.getenv(
        "INSYT_REVIEW_STORAGE_ACCOUNT",
        "insytreviewstorage",
    ).lower()

    if routing.review_account.lower() != expected_review_account:
        raise ValueError(
            f"Refusing review output upload: review account must be {expected_review_account}."
        )
    if routing.processing_account.lower() != "insytprodstorage":
        raise ValueError("Refusing review output upload: processing account must be insytprodstorage.")
    warnings = routing.validate()
    plan = build_review_promotion_blob_plan(db, job_id, routing)
    adapter = DualStorageBlobAdapter(routing)
    uploads = adapter.upload_review_promotion_outputs(
        plan,
        local_review_root=local_review_root,
        job_id=job_id,
        overwrite=overwrite,
        promote_to_source=False,
    )
    staged_prefix = f"{routing.prefix}/processing_center/staged/{job_id}"

    payload = {
        "generated_at": utc_now(),
        "mode": "azure-write",
        "destination_mode": "staged",
        "job_id": job_id,
        "routing": build_azure_routing_summary(
            routing,
            job_id=job_id,
            promotion_count=len(plan),
        ),
        "warnings": warnings,
        "planned_docs": len(plan),
        "staged": {
            "storage_account": routing.review_account,
            "container": routing.review_container,
            "job_id": job_id,
            "prefix": staged_prefix,
            "native_prefix": f"{staged_prefix}/native",
            "text_prefix": f"{staged_prefix}/text",
            "promotion_required": True,
            "final_source_native_prefix": (
                f"{routing.prefix}/source/native"
            ),
            "final_source_text_prefix": (
                f"{routing.prefix}/source/text"
            ),
        },
        "uploads": uploads,
    }
    if export_dir:
        export_json(Path(export_dir) / f"{job_id}.azure_upload_results.json", payload)
    return payload


def azure_upload_report_files(
    routing: AzureRoutingConfig,
    job_id: str,
    local_review_root: str | None = None,
    report_files: list[str] | None = None,
    azure_write: bool = False,
    overwrite: bool = True,
    export_dir: str | None = None,
) -> dict[str, object]:
    """Upload job report/manifest artifacts to the review account reports prefix.

    Review-ready Native/Text files are handled by azure_upload_review_outputs.
    This function uploads non-source artifacts, such as review_ready_manifest.csv,
    job summaries, stage CSVs, meter CSVs, and Azure upload result JSON.
    """
    if not azure_write:
        raise ValueError("Refusing to write report files to Azure because --azure-write was not passed.")
    expected_review_account = os.getenv(
        "INSYT_REVIEW_STORAGE_ACCOUNT",
        "insytreviewstorage",
    ).lower()

    if routing.review_account.lower() != expected_review_account:
        raise ValueError(
            f"Refusing report upload: review account must be {expected_review_account}."
        )
    if routing.processing_account.lower() != "insytprodstorage":
        raise ValueError("Refusing report upload: processing account must be insytprodstorage.")

    adapter = DualStorageBlobAdapter(routing)
    reports_prefix = routing.review_paths()["reports"].rstrip("/")
    candidates: list[Path] = []

    if local_review_root:
        manifest = Path(local_review_root) / "processing_center" / "reports" / "review_ready_manifest.csv"
        if manifest.exists():
            candidates.append(manifest)

    for file in report_files or []:
        path = Path(file)
        if path.exists() and path.is_file():
            candidates.append(path)

    seen: set[str] = set()
    uploads: list[dict[str, object]] = []
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        blob_path = f"{reports_prefix}/{job_id}/{path.name}"
        uploads.append(adapter.upload_report_file(str(path), blob_path, overwrite=overwrite))

    payload = {
        "generated_at": utc_now(),
        "mode": "azure-write",
        "job_id": job_id,
        "routing": build_azure_routing_summary(routing, job_id=job_id, promotion_count=0),
        "uploaded_reports": uploads,
    }
    if export_dir:
        export_json(Path(export_dir) / f"{job_id}.azure_report_upload_results.json", payload)
    return payload


def upload_processing_job_status(
    routing: AzureRoutingConfig,
    job_id: str,
    payload: dict[str, object],
    overwrite: bool = True,
) -> dict[str, object]:
    """Upload billing/job status JSON to the processing account.

    This writes to insytprodstorage under processing_center/jobs/{job_id}/status.json,
    keeping operational job state separate from review-ready outputs.
    """
    if routing.processing_account.lower() != "insytprodstorage":
        raise ValueError("Refusing job status upload: processing account must be insytprodstorage.")
    adapter = DualStorageBlobAdapter(routing)
    jobs_prefix = routing.processing_paths()["jobs"].rstrip("/")
    blob_path = f"{jobs_prefix}/{job_id}/status.json"
    blob_client = adapter.processing_container.get_blob_client(blob_path)
    data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=adapter._content_settings_cls(content_type="application/json"),
    )
    return {
        "status": "uploaded",
        "storage_account": routing.processing_account,
        "container": routing.processing_container,
        "blob_path": blob_path,
        "bytes": len(data),
    }

def _processed_hash_index_blob_path(routing: AzureRoutingConfig) -> str:
    return (
        f"{routing.prefix}/"
        f"processing_center/index/processed_hash_index.json"
    )


def azure_read_processed_hash_index(routing: AzureRoutingConfig) -> dict[str, object]:
    adapter = DualStorageBlobAdapter(routing)
    blob_path = _processed_hash_index_blob_path(routing)
    blob_client = adapter.processing_container.get_blob_client(blob_path)

    try:
        data = blob_client.download_blob().readall()
        payload = json.loads(data.decode("utf-8"))

        if not isinstance(payload, dict):
            raise ValueError("processed_hash_index.json is not a JSON object.")

        payload.setdefault("items", {})
        return payload
    except Exception as exc:
        message = str(exc)

        if (
            "BlobNotFound" in message
            or "The specified blob does not exist" in message
            or getattr(exc, "status_code", None) == 404
        ):
            return {
                "generated_at": utc_now(),
                "workspace": routing.workspace,
                "client": routing.client,
                "project": routing.project,
                "storage_account": routing.processing_account,
                "container": routing.processing_container,
                "blob_path": blob_path,
                "count": 0,
                "items": {},
            }

        raise


def azure_update_processed_hash_index(
    db: LedgerDB,
    routing: AzureRoutingConfig,
    job_id: str,
    overwrite: bool = True,
) -> dict[str, object]:
    adapter = DualStorageBlobAdapter(routing)
    blob_path = _processed_hash_index_blob_path(routing)

    existing = azure_read_processed_hash_index(routing)
    existing_items = existing.get("items") or {}

    if isinstance(existing_items, list):
        items: dict[str, object] = {
            str(record.get("sha256") or "").strip().lower(): record
            for record in existing_items
            if isinstance(record, dict)
            and str(record.get("sha256") or "").strip()
        }
    elif isinstance(existing_items, dict):
        items = {
            str(sha256).strip().lower(): record
            for sha256, record in existing_items.items()
            if str(sha256).strip()
        }
    else:
        items = {}

    rows = db.query(
        """
        SELECT
            file_id,
            job_id,
            doc_id,
            normalized_path,
            extension,
            source_bytes,
            page_count,
            md5,
            sha1,
            sha256,
            native_output_path,
            text_output_path
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND promoted_to_review=1
          AND doc_id IS NOT NULL
          AND sha256 IS NOT NULL
          AND sha256 <> ''
        ORDER BY doc_id
        """,
        (job_id,),
    )

    added = 0
    updated = 0

    for row in rows:
        sha256 = str(row["sha256"] or "").strip().lower()
        if not sha256:
            continue

        existed = sha256 in items

        items[sha256] = {
            "sha256": sha256,
            "md5": row["md5"] or "",
            "sha1": row["sha1"] or "",
            "doc_id": row["doc_id"],
            "file_id": row["file_id"],
            "original_name": Path(row["normalized_path"] or "").name,
            "normalized_path": row["normalized_path"],
            "extension": row["extension"] or "",
            "source_bytes": int(row["source_bytes"] or 0),
            "page_count": int(row["page_count"] or 0),
            "first_processed_job_id": (
                (items.get(sha256) or {}).get("first_processed_job_id")
                if isinstance(items.get(sha256), dict)
                else None
            )
            or row["job_id"],
            "last_seen_job_id": row["job_id"],
            "native_output_path": row["native_output_path"] or "",
            "text_output_path": row["text_output_path"] or "",
            "updated_at": utc_now(),
        }

        if existed:
            updated += 1
        else:
            added += 1

    payload = {
        "generated_at": utc_now(),
        "workspace": routing.workspace,
        "client": routing.client,
        "project": routing.project,
        "storage_account": routing.processing_account,
        "container": routing.processing_container,
        "blob_path": blob_path,
        "count": len(items),
        "added_count": added,
        "updated_count": updated,
        "job_id": job_id,
        "items": items,
    }

    blob_client = adapter.processing_container.get_blob_client(blob_path)
    data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=adapter._content_settings_cls(
            content_type="application/json"
        ),
    )

    return {
        "status": "uploaded",
        "storage_account": routing.processing_account,
        "container": routing.processing_container,
        "blob_path": blob_path,
        "bytes": len(data),
        "count": len(items),
        "added_count": added,
        "updated_count": updated,
    }

def read_processing_job_status(routing: AzureRoutingConfig, job_id: str) -> dict[str, object]:
    adapter = DualStorageBlobAdapter(routing)
    jobs_prefix = routing.processing_paths()["jobs"].rstrip("/")
    blob_path = f"{jobs_prefix}/{job_id}/status.json"
    data = adapter.processing_container.download_blob(blob_path).readall()
    return json.loads(data.decode("utf-8"))
