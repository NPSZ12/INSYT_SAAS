from __future__ import annotations

import hashlib
import json

from .worksheet_work_units import WorksheetWorkUnit


UNIT_IDENTITY_VERSION = 1


def worksheet_detection_fingerprint(
    unit: WorksheetWorkUnit,
    *,
    protocol_fingerprint: str,
    detection_mode: str,
    include_phi: bool,
    enable_azure: bool,
    enable_structured_rules: bool,
) -> str:
    """
    Compute a deterministic, content-bound detection identity.

    A change to the source chunk, boundaries, protocol,
    or detection settings invalidates checkpoint reuse.

    This fingerprint is intended to populate the existing
    DetectionCheckpoint.protocol_fingerprint field for
    worksheet work units.

    It does not perform detection or access Azure.
    """
    if not protocol_fingerprint.strip():
        raise ValueError("Protocol fingerprint is required.")

    if not detection_mode.strip():
        raise ValueError("Detection mode is required.")

    if unit.start_row < 1:
        raise ValueError("Invalid starting row.")

    if unit.end_row < unit.start_row:
        raise ValueError("Invalid ending row.")

    if unit.start_offset < 0:
        raise ValueError("Invalid starting offset.")

    if unit.end_offset < unit.start_offset:
        raise ValueError("Invalid ending offset.")

    if unit.row_count != unit.end_row - unit.start_row + 1:
        raise ValueError("Inconsistent worksheet row count.")

    if unit.end_offset - unit.start_offset != len(unit.text):
        raise ValueError("Inconsistent worksheet offsets.")

    actual_hash = hashlib.sha256(
        unit.text.encode("utf-8")
    ).hexdigest()

    if actual_hash != unit.text_sha256:
        raise ValueError("Worksheet chunk hash mismatch.")

    identity = {
        "schema_version": UNIT_IDENTITY_VERSION,
        "unit_id": unit.unit_id,
        "start_row": unit.start_row,
        "end_row": unit.end_row,
        "start_offset": unit.start_offset,
        "end_offset": unit.end_offset,
        "text_sha256": actual_hash,
        "protocol_fingerprint": protocol_fingerprint,
        "detection_mode": detection_mode,
        "include_phi": bool(include_phi),
        "enable_azure": bool(enable_azure),
        "enable_structured_rules": bool(
            enable_structured_rules
        ),
    }

    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(
        canonical
    ).hexdigest()