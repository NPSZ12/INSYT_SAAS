from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .db import LedgerDB
from .util import utc_now

DEFAULT_PROCESSING_ACCOUNT = "insytprodstorage"
DEFAULT_REVIEW_ACCOUNT = "insytreviewstorage"


def default_container_for_workspace(workspace: str) -> str:
    clean = (workspace or "capture").strip().lower()

    if clean in {"capture", "discovery", "summaries"}:
        return f"insyt-{clean}"

    return "insyt-capture"


def clean_segment(value: str | None) -> str:
    return str(value or "").strip().strip("/").replace("\\", "/")

def storage_segment(value: str | None) -> str:
    return clean_segment(value).replace(" ", "_")

@dataclass(frozen=True)
class AzureRoutingConfig:
    workspace: str
    client: str
    project: str
    processing_account: str = DEFAULT_PROCESSING_ACCOUNT
    review_account: str = DEFAULT_REVIEW_ACCOUNT
    processing_container: str = "insyt-capture"
    review_container: str = "insyt-capture"
    azure_write: bool = False
    allow_same_account: bool = False

    @classmethod
    def from_args(
        cls,
        workspace: str,
        client: str,
        project: str,
        processing_account: str | None = None,
        review_account: str | None = None,
        processing_container: str | None = None,
        review_container: str | None = None,
        azure_write: bool = False,
        allow_same_account: bool = False,
    ) -> "AzureRoutingConfig":
        workspace_clean = clean_segment(workspace).lower() or "capture"
        default_container = default_container_for_workspace(workspace_clean)

        return cls(
            workspace=workspace_clean,
            client=clean_segment(client),
            project=storage_segment(project),
            processing_account=processing_account
            or os.getenv(
                "INSYT_PROCESSING_STORAGE_ACCOUNT",
                DEFAULT_PROCESSING_ACCOUNT,
            ),
            review_account=review_account
            or os.getenv(
                "INSYT_REVIEW_STORAGE_ACCOUNT",
                DEFAULT_REVIEW_ACCOUNT,
            ),
            processing_container=processing_container
            or os.getenv(
                "INSYT_PROCESSING_CONTAINER",
                default_container,
            ),
            review_container=review_container
            or os.getenv(
                "INSYT_REVIEW_CONTAINER",
                default_container,
            ),
            azure_write=azure_write,
            allow_same_account=allow_same_account,
        )

    @property
    def prefix(self) -> str:
        """
        INSYT canonical project path.

        Standard:
            client/workspace/project_storage_key_storage_key

        Example:
            Client1/capture/Project_Client1
        """
        client = clean_segment(self.client)
        workspace = clean_segment(self.workspace).lower() or "capture"
        project = storage_segment(self.project)

        return f"{client}/{workspace}/{project}"

    def processing_blob_url(self, path: str) -> str:
        return (
            f"https://{self.processing_account}.blob.core.windows.net/"
            f"{self.processing_container}/{path}"
        )

    def review_blob_url(self, path: str) -> str:
        return (
            f"https://{self.review_account}.blob.core.windows.net/"
            f"{self.review_container}/{path}"
        )

    def processing_paths(self) -> dict[str, str]:
        p = self.prefix

        return {
            "uploads": f"{p}/source/processing_center/uploads",
            "work": f"{p}/processing_center/work",
            "temp": f"{p}/processing_center/temp",
            "jobs": f"{p}/processing_center/jobs",
            "telemetry": f"{p}/processing_center/telemetry",
            "internal_reports": f"{p}/processing_center/reports/internal",
        }

    def review_paths(self) -> dict[str, str]:
        p = self.prefix

        return {
            "native": f"{p}/source/native",
            "text": f"{p}/source/text",
            "preview": f"{p}/source/preview",
            "metadata": f"{p}/source/metadata",
            "reports": f"{p}/processing_center/reports",
        }

    def validate(self) -> list[str]:
        warnings: list[str] = []

        if not self.client:
            raise ValueError("client is required for Azure routing")

        if not self.project:
            raise ValueError("project is required for Azure routing")

        if (
            self.processing_account.lower() == self.review_account.lower()
            and not self.allow_same_account
        ):
            raise ValueError(
                "Processing and review storage accounts are the same. "
                "Expected insytprodstorage for processing and "
                "insytreviewstorage for review outputs. "
                "Use --allow-same-account only for an intentional "
                "non-production test."
            )

        if self.processing_account.lower() != DEFAULT_PROCESSING_ACCOUNT:
            warnings.append(
                f"processing account is {self.processing_account}, "
                f"expected {DEFAULT_PROCESSING_ACCOUNT}"
            )

        if self.review_account.lower() != DEFAULT_REVIEW_ACCOUNT:
            warnings.append(
                f"review account is {self.review_account}, "
                f"expected {DEFAULT_REVIEW_ACCOUNT}"
            )

        if not self.azure_write:
            warnings.append(
                "azure_write is false; this is a dry-run routing/manifest "
                "plan only"
            )

        return warnings


def build_review_promotion_blob_plan(
    db: LedgerDB,
    job_id: str,
    routing: AzureRoutingConfig,
) -> list[dict[str, object]]:
    rows = db.query(
        """
        SELECT file_id, doc_id, normalized_path, extension, source_bytes,
               page_count, requires_ocr, family_id, parent_file_id, md5,
               sha1, sha256
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND doc_id IS NOT NULL
        ORDER BY doc_id
        """,
        (job_id,),
    )

    review = routing.review_paths()
    plan: list[dict[str, object]] = []

    for row in rows:
        ext = (row["extension"] or "bin").lower().lstrip(".") or "bin"
        doc_id = row["doc_id"]
        native_path = f"{review['native']}/{doc_id}.{ext}"
        text_path = f"{review['text']}/{doc_id}.txt"

        plan.append(
            {
                "job_id": job_id,
                "file_id": row["file_id"],
                "doc_id": doc_id,
                "original_path": row["normalized_path"],
                "review_storage_account": routing.review_account,
                "review_container": routing.review_container,
                "native_blob_path": native_path,
                "native_blob_url": routing.review_blob_url(native_path),
                "text_blob_path": text_path,
                "text_blob_url": routing.review_blob_url(text_path),
                "extension": ext,
                "source_bytes": int(row["source_bytes"] or 0),
                "page_count": int(row["page_count"] or 0),
                "requires_ocr": int(row["requires_ocr"] or 0),
                "family_id": row["family_id"] or "",
                "parent_file_id": row["parent_file_id"] or "",
                "md5": row["md5"] or "",
                "sha1": row["sha1"] or "",
                "sha256": row["sha256"] or "",
                "write_enabled": routing.azure_write,
            }
        )

    return plan


def build_azure_routing_summary(
    routing: AzureRoutingConfig,
    job_id: str | None = None,
    promotion_count: int = 0,
) -> dict[str, object]:
    processing_paths = routing.processing_paths()
    review_paths = routing.review_paths()

    return {
        "generated_at": utc_now(),
        "mode": "azure-write" if routing.azure_write else "dry-run",
        "job_id": job_id,
        "workspace": routing.workspace,
        "client": routing.client,
        "project": routing.project,
        "project_prefix": routing.prefix,
        "processing": {
            "storage_account": routing.processing_account,
            "container": routing.processing_container,
            "paths": processing_paths,
            "urls": {
                key: routing.processing_blob_url(value)
                for key, value in processing_paths.items()
            },
        },
        "review_outputs": {
            "storage_account": routing.review_account,
            "container": routing.review_container,
            "paths": review_paths,
            "urls": {
                key: routing.review_blob_url(value)
                for key, value in review_paths.items()
            },
        },
        "safety": {
            "processing_account_expected": (
                routing.processing_account.lower()
                == DEFAULT_PROCESSING_ACCOUNT
            ),
            "review_account_expected": (
                routing.review_account.lower()
                == DEFAULT_REVIEW_ACCOUNT
            ),
            "accounts_are_separate": (
                routing.processing_account.lower()
                != routing.review_account.lower()
            ),
            "azure_write_enabled": routing.azure_write,
        },
        "promotion_plan_count": promotion_count,
    }


def export_azure_plan(
    export_dir: str,
    job_id: str | None,
    summary: dict[str, object],
    promotion_plan: list[dict[str, object]],
) -> dict[str, str]:
    out = Path(export_dir)
    out.mkdir(parents=True, exist_ok=True)

    stem = job_id or "azure-routing"
    summary_path = out / f"{stem}.azure_routing_summary.json"

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    paths: dict[str, str] = {
        "azure_routing_summary_json": str(summary_path)
    }

    if promotion_plan:
        plan_json = out / f"{stem}.azure_review_promotion_plan.json"

        plan_json.write_text(
            json.dumps(promotion_plan, indent=2),
            encoding="utf-8",
        )

        paths["azure_review_promotion_plan_json"] = str(plan_json)

        plan_csv = out / f"{stem}.azure_review_promotion_plan.csv"

        with plan_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(promotion_plan[0].keys()),
            )
            writer.writeheader()
            writer.writerows(promotion_plan)

        paths["azure_review_promotion_plan_csv"] = str(plan_csv)

    return paths