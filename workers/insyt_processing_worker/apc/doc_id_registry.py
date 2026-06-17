from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .azure_layout import AzureRoutingConfig
from .util import utc_now


def _load_azure_sdk():
    from azure.storage.blob import BlobServiceClient, ContentSettings  # type: ignore
    from azure.identity import DefaultAzureCredential  # type: ignore

    return BlobServiceClient, ContentSettings, DefaultAzureCredential


@dataclass
class DocIdAllocation:
    start_number: int
    end_number: int
    assigned_count: int
    prefix: str
    width: int
    registry_blob_path: str
    previous_last_assigned_number: int
    new_last_assigned_number: int


def doc_id_registry_blob_path(routing: AzureRoutingConfig) -> str:
    return f"{routing.prefix}/_system/doc_id_registry.json"


def _parse_doc_id_number(doc_id: str, prefix: str) -> int:
    pattern = re.compile(
        rf"^{re.escape(prefix)}(\d+)$",
        re.IGNORECASE,
    )

    match = pattern.match(str(doc_id or "").strip())

    if not match:
        return 0

    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _get_processing_container(routing: AzureRoutingConfig):
    BlobServiceClient, _, DefaultAzureCredential = _load_azure_sdk()

    conn = os.getenv("INSYT_PROCESSING_STORAGE_CONNECTION_STRING")

    if conn:
        service = BlobServiceClient.from_connection_string(conn)
    else:
        credential = DefaultAzureCredential()
        service = BlobServiceClient(
            account_url=(
                f"https://{routing.processing_account}"
                ".blob.core.windows.net"
            ),
            credential=credential,
        )

    return service.get_container_client(routing.processing_container)


def read_doc_id_registry(
    routing: AzureRoutingConfig,
    prefix: str = "INSYT",
    width: int = 9,
) -> dict:
    container = _get_processing_container(routing)
    blob_path = doc_id_registry_blob_path(routing)
    blob_client = container.get_blob_client(blob_path)

    try:
        if not blob_client.exists():
            return {
                "workspace": routing.workspace,
                "client": routing.client,
                "project": routing.project,
                "prefix": prefix,
                "width": width,
                "last_assigned_number": 0,
                "last_assigned_doc_id": "",
                "updated_at": "",
            }

        data = blob_client.download_blob().readall()
        payload = json.loads(data.decode("utf-8"))

        if not isinstance(payload, dict):
            raise ValueError("Doc ID registry is not a JSON object.")

        payload.setdefault("workspace", routing.workspace)
        payload.setdefault("client", routing.client)
        payload.setdefault("project", routing.project)
        payload.setdefault("prefix", prefix)
        payload.setdefault("width", width)
        payload.setdefault("last_assigned_number", 0)
        payload.setdefault("last_assigned_doc_id", "")
        payload.setdefault("updated_at", "")

        return payload

    except Exception as exc:
        message = str(exc)

        if (
            "BlobNotFound" in message
            or "The specified blob does not exist" in message
            or getattr(exc, "status_code", None) == 404
        ):
            return {
                "workspace": routing.workspace,
                "client": routing.client,
                "project": routing.project,
                "prefix": prefix,
                "width": width,
                "last_assigned_number": 0,
                "last_assigned_doc_id": "",
                "updated_at": "",
            }

        raise


def scan_highest_existing_doc_number(
    routing: AzureRoutingConfig,
    prefix: str = "INSYT",
) -> int:
    """
    Safety scan existing processing index and staged/live-like processing paths
    to avoid reusing Doc IDs if the registry is missing or stale.
    """
    container = _get_processing_container(routing)

    highest = 0

    candidate_prefixes = [
        f"{routing.prefix}/processing_center/index/",
        f"{routing.prefix}/processing_center/jobs/",
        f"{routing.prefix}/processing_center/staged/",
        f"{routing.prefix}/source/native/",
        f"{routing.prefix}/source/text/",
    ]

    for candidate_prefix in candidate_prefixes:
        try:
            for blob in container.list_blobs(name_starts_with=candidate_prefix):
                name = str(blob.name or "")

                for token in re.findall(
                    rf"{re.escape(prefix)}\d+",
                    name,
                    flags=re.IGNORECASE,
                ):
                    highest = max(
                        highest,
                        _parse_doc_id_number(token, prefix),
                    )
        except Exception:
            continue

    # Also inspect processed_hash_index.json if present.
    index_path = (
        f"{routing.prefix}/processing_center/index/"
        "processed_hash_index.json"
    )

    try:
        blob_client = container.get_blob_client(index_path)

        if blob_client.exists():
            data = blob_client.download_blob().readall()
            payload = json.loads(data.decode("utf-8"))
            items = payload.get("items") or {}

            if isinstance(items, dict):
                records = items.values()
            elif isinstance(items, list):
                records = items
            else:
                records = []

            for record in records:
                if not isinstance(record, dict):
                    continue

                highest = max(
                    highest,
                    _parse_doc_id_number(
                        str(record.get("doc_id") or ""),
                        prefix,
                    ),
                )

    except Exception:
        pass

    return highest


def reserve_doc_ids(
    routing: AzureRoutingConfig,
    count: int,
    prefix: str = "INSYT",
    width: int = 9,
) -> DocIdAllocation:
    if count <= 0:
        registry = read_doc_id_registry(
            routing=routing,
            prefix=prefix,
            width=width,
        )

        last_number = int(registry.get("last_assigned_number") or 0)

        return DocIdAllocation(
            start_number=last_number + 1,
            end_number=last_number,
            assigned_count=0,
            prefix=prefix,
            width=width,
            registry_blob_path=doc_id_registry_blob_path(routing),
            previous_last_assigned_number=last_number,
            new_last_assigned_number=last_number,
        )

    container = _get_processing_container(routing)
    blob_path = doc_id_registry_blob_path(routing)
    blob_client = container.get_blob_client(blob_path)

    registry = read_doc_id_registry(
        routing=routing,
        prefix=prefix,
        width=width,
    )

    registry_last = int(registry.get("last_assigned_number") or 0)
    scan_last = scan_highest_existing_doc_number(
        routing=routing,
        prefix=prefix,
    )

    previous_last = max(registry_last, scan_last)

    start_number = previous_last + 1
    end_number = previous_last + count

    last_doc_id = f"{prefix}{end_number:0{width}d}"

    updated_registry = {
        "workspace": routing.workspace,
        "client": routing.client,
        "project": routing.project,
        "prefix": prefix,
        "width": width,
        "last_assigned_number": end_number,
        "last_assigned_doc_id": last_doc_id,
        "previous_last_assigned_number": previous_last,
        "registry_last_assigned_number": registry_last,
        "scan_last_assigned_number": scan_last,
        "last_reserved_count": count,
        "updated_at": utc_now(),
    }

    blob_client.upload_blob(
        json.dumps(updated_registry, indent=2),
        overwrite=True,
        content_settings=_load_azure_sdk()[1](
            content_type="application/json"
        ),
    )

    return DocIdAllocation(
        start_number=start_number,
        end_number=end_number,
        assigned_count=count,
        prefix=prefix,
        width=width,
        registry_blob_path=blob_path,
        previous_last_assigned_number=previous_last,
        new_last_assigned_number=end_number,
    )