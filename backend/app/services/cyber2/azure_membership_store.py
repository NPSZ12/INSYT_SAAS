"""Azure Blob ETag adapter for Cyber2 membership_persistence.

This module does not change existing INSYT storage helpers or provision resources.
Instantiate with the *existing* processing-storage container client after the API
has authenticated and authorized the requested workspace/client/project.

Blob update semantics:
  - absent: create only (overwrite=False)
  - existing: server-side ETag conditional overwrite (IfNotModified)
  - read: get ETag then download that exact version conditionally

Do not log registry contents: they may link to sensitive evidence.
"""
from __future__ import annotations

import json
from typing import Any

from .membership_persistence import MembershipConflict, StoredSnapshot


class AzureBlobMembershipStore:
    def __init__(self, container_client: Any):
        if container_client is None:
            raise ValueError("An existing processing container client is required")
        self._container = container_client

    @staticmethod
    def _sdk():
        # Delay SDK imports so pure tests and module imports do not open Azure.
        from azure.core import MatchConditions
        from azure.core.exceptions import (
            HttpResponseError,
            ResourceExistsError,
            ResourceModifiedError,
            ResourceNotFoundError,
        )
        from azure.storage.blob import ContentSettings
        return (MatchConditions, HttpResponseError, ResourceExistsError,
                ResourceModifiedError, ResourceNotFoundError, ContentSettings)

    @staticmethod
    def _conflict(exc: Exception) -> bool:
        # 409 = create race / conflicting write; 412 = failed ETag precondition.
        return getattr(exc, "status_code", None) in (409, 412)

    def read(self, path: str) -> StoredSnapshot:
        (MatchConditions, HttpResponseError, ResourceExistsError,
         ResourceModifiedError, ResourceNotFoundError, _) = self._sdk()
        blob = self._container.get_blob_client(path)
        try:
            props = blob.get_blob_properties()
        except ResourceNotFoundError:
            return StoredSnapshot(payload=None, version=None)
        etag = str(getattr(props, "etag", "") or "")
        if not etag:
            raise ValueError("Membership blob is missing its ETag")
        try:
            downloader = blob.download_blob(
                etag=etag,
                match_condition=MatchConditions.IfNotModified,
            )
            document = json.loads(downloader.readall().decode("utf-8"))
        except (ResourceModifiedError, ResourceNotFoundError) as exc:
            raise MembershipConflict("Registry changed during read; reload") from exc
        except HttpResponseError as exc:
            if self._conflict(exc) or getattr(exc, "status_code", None) == 404:
                raise MembershipConflict("Registry changed during read; reload") from exc
            raise
        if not isinstance(document, dict):
            raise ValueError("Membership registry must be a JSON object")
        return StoredSnapshot(payload=document, version=etag)

    def write(self, path: str, payload: dict[str, Any], *, expected_version: str | None) -> str:
        (MatchConditions, HttpResponseError, ResourceExistsError,
         ResourceModifiedError, ResourceNotFoundError, ContentSettings) = self._sdk()
        blob = self._container.get_blob_client(path)
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
        kwargs: dict[str, Any] = {
            "content_settings": ContentSettings(content_type="application/json"),
        }
        if expected_version is None:
            kwargs["overwrite"] = False
        else:
            if not isinstance(expected_version, str) or not expected_version.strip():
                raise ValueError("expected_version must be a nonempty ETag")
            kwargs.update({
                "overwrite": True,
                "etag": expected_version,
                "match_condition": MatchConditions.IfNotModified,
            })
        try:
            response = blob.upload_blob(data, **kwargs)
        except (ResourceExistsError, ResourceModifiedError) as exc:
            raise MembershipConflict("Membership registry changed; reload and reconcile") from exc
        except HttpResponseError as exc:
            if self._conflict(exc):
                raise MembershipConflict("Membership registry changed; reload and reconcile") from exc
            raise
        etag = (response.get("etag") if isinstance(response, dict)
                else getattr(response, "etag", None))
        if not etag:
            # A successful upload must report the version actually committed.
            raise RuntimeError("Azure Blob upload did not return a committed ETag")
        return str(etag)
