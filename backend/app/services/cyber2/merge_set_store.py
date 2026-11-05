"""Independent, immutable Cyber2 merge-set persistence.

Uses an already-authorized INSYT processing container and project base path.
Does not write to RAW Capture or approved-identity membership storage.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4


class MergeSetStoreError(ValueError):
    pass


class MergeSetConflict(MergeSetStoreError):
    pass


class Cyber2MergeSetStore:
    def __init__(
        self,
        container_client,
        project_base_path: str,
        *,
        content_settings_factory=None,
    ):
        if container_client is None:
            raise MergeSetStoreError("Processing container required")

        base = str(project_base_path or "").strip("/")

        if (
            not base
            or ".." in base.split("/")
            or len(base.split("/")) < 3
        ):
            raise MergeSetStoreError("Invalid scoped project base path")

        self.container = container_client
        self.base = base
        self.content_settings_factory = content_settings_factory

    def _content_settings(self):
        if self.content_settings_factory is not None:
            return self.content_settings_factory()

        from azure.storage.blob import ContentSettings

        return ContentSettings(content_type="application/json")

    def _path(self, merge_set_id):
        value = str(merge_set_id or "")

        if not re.fullmatch(r"MSET-[0-9A-F]{32}", value):
            raise MergeSetStoreError("Invalid merge-set ID")

        return (
            f"{self.base}/cyber2/merge_sets/"
            f"{value}/merge_set.json"
        )

    @staticmethod
    def _encode(payload):
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def _digest(cls, payload):
        return hashlib.sha256(cls._encode(payload)).hexdigest()

    @staticmethod
    def _validate_working_set(derived):
        if (
            not isinstance(derived, dict)
            or derived.get("status") != "derived_not_persisted"
        ):
            raise MergeSetStoreError("Invalid derived working set")

        records = derived.get("working_records")
        headers = derived.get("approved_headers")
        index = derived.get("merge_index")

        if (
            not isinstance(records, list)
            or not records
            or not isinstance(headers, list)
            or not headers
            or len(headers) != len(set(headers))
            or not isinstance(index, list)
            or not index
            or not set(index).issubset(headers)
        ):
            raise MergeSetStoreError("Incomplete working-set definition")

        if derived.get("working_record_count") != len(records):
            raise MergeSetStoreError("Working record count mismatch")

        all_ucids = []
        working_ids = []

        for record in records:
            if not isinstance(record, dict):
                raise MergeSetStoreError("Invalid working record")

            ucids = record.get("source_ucids")
            cells = record.get("cells")
            provenance = record.get("field_provenance")

            if (
                not isinstance(ucids, list)
                or not ucids
                or not isinstance(cells, dict)
                or not isinstance(provenance, dict)
                or set(cells) != set(headers)
                or set(provenance) != set(headers)
            ):
                raise MergeSetStoreError("Incomplete field provenance")

            for field in headers:
                lineage = provenance[field]

                if (
                    not isinstance(lineage, list)
                    or len(lineage) != len(ucids)
                    or [str(p.get("ucid")) for p in lineage]
                    != [str(u) for u in ucids]
                ):
                    raise MergeSetStoreError("Invalid field lineage")

            all_ucids.extend(str(value) for value in ucids)
            working_ids.append(record.get("working_record_id"))

        if (
            len(all_ucids) != len(set(all_ucids))
            or len(working_ids) != len(set(working_ids))
            or derived.get("raw_record_count") != len(all_ucids)
        ):
            raise MergeSetStoreError("Source or working identity mismatch")

    def save(
        self,
        *,
        derived,
        workspace,
        client,
        project,
        approved_mapping_path,
        executed_by,
        request_id=None,
        snapshot_fingerprint=None,
    ):
        self._validate_working_set(derived)

        if not all([
            workspace, client, project,
            approved_mapping_path, executed_by,
        ]):
            raise MergeSetStoreError("Missing execution audit fields")

        intent_hash = None

        if request_id is not None:
            try:
                request_uuid = UUID(str(request_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise MergeSetStoreError(
                    "Execution request ID must be a UUID"
                ) from exc

            if request_uuid.version != 4:
                raise MergeSetStoreError(
                    "Execution request ID must be UUID version 4"
                )

            if not isinstance(snapshot_fingerprint, str) or not re.fullmatch(
                r"[0-9a-f]{64}", snapshot_fingerprint
            ):
                raise MergeSetStoreError(
                    "Valid snapshot fingerprint is required"
                )

            request_id = str(request_uuid)

            intent_hash = self._digest({
                "derived": derived,
                "workspace": workspace,
                "client": client,
                "project": project,
                "approved_mapping_path": approved_mapping_path,
                "executed_by": executed_by,
                "snapshot_fingerprint": snapshot_fingerprint,
            })

            merge_set_id = f"MSET-{request_uuid.hex.upper()}"
        else:
            merge_set_id = f"MSET-{uuid4().hex.upper()}"

        created_at = datetime.now(timezone.utc).isoformat()

        document = {
            "schema_version": 1,
            "merge_set_id": merge_set_id,
            "status": "completed",
            "workspace": str(workspace),
            "client": str(client),
            "project": str(project),
            "header_set_id": derived["header_set_id"],
            "merge_index": derived["merge_index"],
            "approved_mapping_path": str(approved_mapping_path),
            "created_at": created_at,
            "executed_by": str(executed_by),
            "raw_record_count": derived["raw_record_count"],
            "working_record_count": derived["working_record_count"],
            "merged_group_count": derived["merged_group_count"],
            "approved_headers": derived["approved_headers"],
            "working_records": derived["working_records"],
        }

        if request_id is not None:
            document["request_id"] = request_id
            document["snapshot_fingerprint"] = snapshot_fingerprint
            document["execution_intent_sha256"] = intent_hash

        document["integrity_sha256"] = self._digest(document)

        path = self._path(merge_set_id)
        blob = self.container.get_blob_client(path)

        replayed = False

        try:
            blob.upload_blob(
                self._encode(document),
                overwrite=False,
                content_settings=self._content_settings(),
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) not in (409, 412):
                raise

            if request_id is None:
                raise MergeSetConflict(
                    "Merge-set ID already exists"
                ) from exc

            # Create-only upload is atomic. A concurrent retry reads
            # the already-committed set and verifies identical intent.
            existing = self.load(merge_set_id)

            if (
                existing.get("request_id") != request_id
                or existing.get("execution_intent_sha256") != intent_hash
                or existing.get("snapshot_fingerprint")
                != snapshot_fingerprint
            ):
                raise MergeSetConflict(
                    "Execution request ID reused with different data"
                ) from exc

            document = existing
            replayed = True

        return {
            "merge_set_id": merge_set_id,
            "idempotent_replay": replayed,
            "status": "completed",
            "header_set_id": document["header_set_id"],
            "created_at": created_at,
            "raw_record_count": document["raw_record_count"],
            "working_record_count": document["working_record_count"],
            "merged_group_count": document["merged_group_count"],
        }

    def load(self, merge_set_id):
        blob = self.container.get_blob_client(
            self._path(merge_set_id)
        )

        document = json.loads(
            blob.download_blob().readall().decode("utf-8")
        )

        if not isinstance(document, dict):
            raise MergeSetStoreError("Invalid merge-set document")

        if document.get("merge_set_id") != merge_set_id:
            raise MergeSetStoreError("Merge-set identity mismatch")

        stored_digest = document.get("integrity_sha256")
        original = {
            key: value
            for key, value in document.items()
            if key != "integrity_sha256"
        }

        if stored_digest != self._digest(original):
            raise MergeSetStoreError("Merge-set integrity check failed")

        return document
