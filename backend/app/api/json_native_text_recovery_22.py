"""Temporary, strictly scoped native JSON text recovery for Doc 22."""

import hashlib

from json_native_promotion_execution import (
    JsonNativePromotionFailed,
    promote_json_native_verified,
)

DOC = "INSYT000000022"
JOB = "JOB-2FEF1425D3384DC5"
DETECTION = "DET-893C4B6633E64211"
BASE = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"

STAGED_NATIVE = f"{BASE}/processing_center/staged/{JOB}/native/{DOC}.json"
STAGED_TEXT = f"{BASE}/processing_center/staged/{JOB}/text/{DOC}.txt"
FINAL_NATIVE = f"{BASE}/source/native/{DOC}.json"
FINAL_TEXT = f"{BASE}/source/text/{DOC}.txt"


class JsonTextRecoveryRejected(ValueError):
    pass


def recover_doc22_text_verified(
    *,
    workspace,
    client,
    project,
    doc_ids,
    intake,
    read_staged,
    read_final,
    write_final,
):
    if (
        workspace != "capture"
        or client != "INSYT_Demo"
        or project != "Project_Payroll_Dedupe_Test"
        or doc_ids != [DOC]
    ):
        raise JsonTextRecoveryRejected("Recovery scope mismatch.")

    required = {
        "workspace": workspace,
        "client": client,
        "project": project,
        "doc_id": DOC,
        "source_job_id": JOB,
        "detection_job_id": DETECTION,
        "source_kind": "native_json",
        "classification": "HIT",
        "source_native_path": FINAL_NATIVE,
        "csv_generation_status": "not_started",
    }

    if not isinstance(intake, dict):
        raise JsonTextRecoveryRejected("Missing Cyber2 intake record.")

    for key, expected in required.items():
        if intake.get(key) != expected:
            raise JsonTextRecoveryRejected(
                f"Cyber2 intake mismatch: {key}."
            )

    if intake.get("source_csv_path") is not None:
        raise JsonTextRecoveryRejected(
            "Unexpected CSV reference in JSON intake."
        )

    native = read_staged(STAGED_NATIVE)
    text = read_staged(STAGED_TEXT)
    final_native = read_final(FINAL_NATIVE)

    if not isinstance(native, bytes) or not native:
        raise JsonTextRecoveryRejected("Original JSON is missing.")

    if not isinstance(text, bytes) or len(text) != 1336:
        raise JsonTextRecoveryRejected(
            "Staged text is missing or not 1336 bytes."
        )

    digest = hashlib.sha256(native).hexdigest()

    if (
        not isinstance(final_native, bytes)
        or final_native != native
        or intake.get("source_sha256") != digest
        or intake.get("source_bytes") != len(native)
    ):
        raise JsonTextRecoveryRejected(
            "Native JSON integrity verification failed."
        )

    def guarded_write(path, data):
        if path != FINAL_TEXT or data != text:
            raise JsonTextRecoveryRejected(
                "Only the original Doc 22 text may be written."
            )
        write_final(path, data)

    contract = {
        "doc_id": DOC,
        "source_job_id": JOB,
        "source_kind": "native_json",
        "requires_manual_promotion": True,
        "generate_csv": False,
        "staged_native_path": STAGED_NATIVE,
        "staged_text_path": STAGED_TEXT,
        "final_native_path": FINAL_NATIVE,
        "final_text_path": FINAL_TEXT,
    }

    try:
        result = promote_json_native_verified(
            contract=contract,
            read_staged=read_staged,
            read_final=read_final,
            write_final=guarded_write,
        )
    except JsonNativePromotionFailed as exc:
        raise JsonTextRecoveryRejected(str(exc)) from exc

    if (
        result.get("verified") is not True
        or result.get("text_verified") is not True
        or result.get("status") != "already_promoted_verified"
        or result.get("text_bytes") != 1336
    ):
        raise JsonTextRecoveryRejected(
            "Text recovery verification failed."
        )

    return {
        "status": "completed",
        "doc_id": DOC,
        "text_status": result["text_status"],
        "text_verified": True,
        "text_bytes": result["text_bytes"],
        "text_sha256": result["text_sha256"],
        "native_verified_unchanged": True,
        "cyber2_registration_unchanged": True,
        "csv_generated": False,
    }
