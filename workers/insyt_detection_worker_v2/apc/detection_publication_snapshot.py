from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from azure.core.exceptions import ResourceExistsError


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_snapshot(
    snapshot: Any,
    job_id: str,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("Invalid publication snapshot.")

    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("detection_job_id") != job_id
    ):
        raise ValueError("Publication snapshot identity mismatch.")

    plan = snapshot.get("plan")
    digest = snapshot.get("sha256")

    if not isinstance(plan, dict):
        raise ValueError("Publication plan missing.")

    if not isinstance(digest, str):
        raise ValueError("Publication digest missing.")

    actual = hashlib.sha256(
        _canonical_bytes(plan)
    ).hexdigest()

    if actual != digest:
        raise ValueError("Publication snapshot digest mismatch.")

    writes = plan.get("writes")
    result = plan.get("result")

    if not isinstance(writes, list) or not writes:
        raise ValueError("Publication writes missing.")

    if not isinstance(result, dict):
        raise ValueError("Publication result missing.")

    if result.get("detection_job_id") != job_id:
        raise ValueError("Publication result identity mismatch.")

    if result.get("status") not in {
        "completed",
        "completed_with_exceptions",
    }:
        raise ValueError("Publication result is not terminal.")

    paths = set()

    for write in writes:
        if not isinstance(write, dict):
            raise ValueError("Invalid publication write.")

        path = write.get("blob_path")

        if not isinstance(path, str) or not path.strip():
            raise ValueError("Publication write path missing.")

        if path in paths:
            raise ValueError("Duplicate publication write path.")

        if "payload" not in write:
            raise ValueError("Publication write payload missing.")

        if type(write.get("overwrite")) is not bool:
            raise ValueError("Publication overwrite policy missing.")

        paths.add(path)

    return plan


def load_or_create_publication_snapshot(
    *,
    container: Any,
    blob_path: str,
    detection_job_id: str,
    build_plan: Callable[[], dict[str, Any]],
    assert_owner: Callable[[], None],
) -> dict[str, Any]:
    """
    Reuse the first durable complete publication plan.

    Call only after complete worksheet verification
    and while holding the existing job-level claim.

    Does not publish any result artifacts itself.
    """
    job_id = str(detection_job_id or "").strip()

    if not job_id or not blob_path:
        raise ValueError("Snapshot identity/path missing.")

    if not callable(build_plan) or not callable(assert_owner):
        raise TypeError("Snapshot callbacks required.")

    blob = container.get_blob_client(blob_path)

    def load_existing():
        raw = blob.download_blob().readall()
        snapshot = json.loads(raw.decode("utf-8"))
        return _validate_snapshot(snapshot, job_id)

    try:
        if blob.exists():
            return load_existing()
    except ResourceExistsError:
        return load_existing()

    assert_owner()

    plan = build_plan()

    # Validate the complete plan BEFORE creating
    # the durable snapshot.
    snapshot = {
        "schema_version": 1,
        "detection_job_id": job_id,
        "plan": plan,
        "sha256": hashlib.sha256(
            _canonical_bytes(plan)
        ).hexdigest(),
    }

    _validate_snapshot(snapshot, job_id)

    assert_owner()

    try:
        blob.upload_blob(
            _canonical_bytes(snapshot),
            overwrite=False,
        )
    except ResourceExistsError:
        # A concurrent creator won. Never overwrite it.
        return load_existing()

    return load_existing()