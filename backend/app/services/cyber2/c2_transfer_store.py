"""Project-scoped, immutable C2 transfer snapshots in existing storage.

API callers must independently authenticate, authorize project access,
verify Merge Set integrity, validate source conservation, and verify a
trusted origin approval before invoking save().

The initial release does not permit replacing a different Merge Set
within the same Header Set. Such replacement requires a separate
audited, lineage-checked operation.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone


class C2TransferStoreError(ValueError):
    pass


class C2TransferConflict(C2TransferStoreError):
    pass


def _require(condition, message):
    if not condition:
        raise C2TransferStoreError(message)


def _encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


class Cyber2C2TransferStore:
    def __init__(
        self,
        container_client,
        project_base_path,
        *,
        workspace,
        client,
        project,
        content_settings_factory=None,
    ):
        _require(container_client is not None, "Processing container required")
        _require(
            isinstance(project_base_path, str)
            and bool(project_base_path.strip())
            and not project_base_path.startswith("/")
            and ".." not in project_base_path.split("/"),
            "Invalid project storage base",
        )

        self.container = container_client
        self.base = project_base_path.rstrip("/")
        self.scope = {
            "workspace": workspace,
            "client": client,
            "project": project,
        }
        _require(
            all(isinstance(v, str) and bool(v) for v in self.scope.values()),
            "Incomplete project scope",
        )
        self.content_settings_factory = content_settings_factory

    def _path(self, header_set_id):
        _require(
            isinstance(header_set_id, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,96}", header_set_id)
            is not None,
            "Invalid Header Set identity",
        )
        return (
            f"{self.base}/cyber2/c2/header_sets/"
            f"{header_set_id}/current.json"
        )

    def _content_settings(self):
        if self.content_settings_factory is not None:
            return self.content_settings_factory()
        from azure.storage.blob import ContentSettings
        return ContentSettings(content_type="application/json")

    def _validate_scope(self, payload):
        _require(
            isinstance(payload, dict)
            and all(payload.get(k) == v for k, v in self.scope.items()),
            "C2 snapshot project scope mismatch",
        )

    def load(self, header_set_id):
        """Load an existing transfer snapshot, or None if absent.

        Never treat corruption, storage failures, or authorization
        failures as an empty C2 table.
        """
        blob = self.container.get_blob_client(self._path(header_set_id))

        try:
            document = json.loads(
                blob.download_blob().readall().decode("utf-8")
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise

        self._validate_scope(document)
        _require(
            document.get("schema_version") == 1
            and document.get("status") == "transferred"
            and document.get("header_set_id") == header_set_id,
            "C2 snapshot identity or status mismatch",
        )

        projection = document.get("projection")
        _require(
            isinstance(projection, dict),
            "C2 projection missing",
        )
        self._validate_scope(projection)

        _require(
            projection.get("header_set_id") == header_set_id
            and projection.get("merge_set_id")
                == document.get("merge_set_id")
            and projection.get("merge_integrity_sha256")
                == document.get("merge_integrity_sha256"),
            "C2 snapshot projection binding mismatch",
        )

        _require(
            isinstance(document.get("projection_sha256"), str)
            and document["projection_sha256"] == _digest(projection),
            "C2 transfer integrity check failed",
        )

        unsigned = {
            key: value
            for key, value in document.items()
            if key != "integrity_sha256"
        }

        _require(
            isinstance(document.get("integrity_sha256"), str)
            and document["integrity_sha256"] == _digest(unsigned),
            "C2 snapshot integrity check failed",
        )

        return document

    def save(self, projection, *, authorized_by):
        """Atomically create one immutable Header Set snapshot.

        Exact replays are safe. Different submissions conflict.
        """
        self._validate_scope(projection)

        header_set_id = projection.get("header_set_id")
        path = self._path(header_set_id)

        _require(
            projection.get("schema_version") == 1
            and isinstance(projection.get("merge_set_id"), str)
            and re.fullmatch(
                r"MSET-[0-9A-F]{32}",
                projection["merge_set_id"],
            ) is not None,
            "Invalid C2 Merge Set identity",
        )

        _require(
            isinstance(projection.get("merge_integrity_sha256"), str)
            and re.fullmatch(
                r"[0-9a-f]{64}",
                projection["merge_integrity_sha256"],
            ) is not None,
            "Invalid source Merge Set digest",
        )

        _require(
            isinstance(projection.get("rows"), list)
            and isinstance(projection.get("records"), list)
            and bool(projection["records"])
            and projection.get("working_record_count")
                == len(projection["records"])
                == len(projection["rows"])
            and isinstance(projection.get("original_source_record_count"), int)
            and projection["original_source_record_count"] > 0,
            "Invalid C2 transfer population",
        )

        _require(
            isinstance(authorized_by, str)
            and bool(authorized_by.strip()),
            "Authenticated transfer actor required",
        )

        digest = _digest(projection)
        blob = self.container.get_blob_client(path)

        document = {
            "schema_version": 1,
            "status": "transferred",
            **self.scope,
            "header_set_id": header_set_id,
            "merge_set_id": projection["merge_set_id"],
            "merge_integrity_sha256":
                projection["merge_integrity_sha256"],
            "projection_sha256": digest,
            "transferred_by": authorized_by,
            "transferred_at": datetime.now(timezone.utc).isoformat(),
            "projection": deepcopy(projection),
        }

        document["integrity_sha256"] = _digest(document)

        try:
            blob.upload_blob(
                _encode(document),
                overwrite=False,
                content_settings=self._content_settings(),
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) not in (409, 412):
                raise

            existing = self.load(header_set_id)
            if existing is None:
                raise C2TransferConflict(
                    "C2 transfer raced with an unavailable snapshot"
                ) from exc

            if existing["projection_sha256"] != digest:
                raise C2TransferConflict(
                    "Different Merge Set already occupies this Header Set"
                ) from exc

            return {
                "status": "already_transferred",
                "header_set_id": header_set_id,
                "merge_set_id": existing["merge_set_id"],
                "working_record_count":
                    existing["projection"]["working_record_count"],
                "original_source_record_count":
                    existing["projection"]["original_source_record_count"],
            }

        return {
            "status": "transferred",
            "header_set_id": header_set_id,
            "merge_set_id": projection["merge_set_id"],
            "working_record_count": projection["working_record_count"],
            "original_source_record_count":
                projection["original_source_record_count"],
        }

    def display(self, header_set_id):
        """Return table rows without exposing complete provenance."""
        document = self.load(header_set_id)
        if document is None:
            return None

        projection = document["projection"]
        return {
            "headers": deepcopy(projection["headers"]),
            "rows": deepcopy(projection["rows"]),
            "source": "cyber2_c2_transfer",
            "merge_set_id": document["merge_set_id"],
            "working_record_count":
                projection["working_record_count"],
            "original_source_record_count":
                projection["original_source_record_count"],
        }
