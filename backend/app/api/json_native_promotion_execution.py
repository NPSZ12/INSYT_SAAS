"""Verified native JSON promotion, called only after authorization.

The caller must validate the selected document against authoritative
ingestion and detection records before invoking this operation.

Storage operations are injected so existing Azure helpers can be used.
No CSV generation, Cyber2 registration, or automatic promotion.
"""

import hashlib


class JsonNativePromotionFailed(RuntimeError):
    pass


def promote_json_native_verified(
    *,
    contract,
    read_staged,
    read_final,
    write_final,
):
    if not isinstance(contract, dict):
        raise JsonNativePromotionFailed("Invalid promotion contract.")

    if (
        contract.get("source_kind") != "native_json"
        or contract.get("requires_manual_promotion") is not True
        or contract.get("generate_csv") is not False
    ):
        raise JsonNativePromotionFailed(
            "Native JSON promotion contract is not authorized."
        )

    source = contract.get("staged_native_path")
    destination = contract.get("final_native_path")

    if (
        not isinstance(source, str)
        or not isinstance(destination, str)
        or "/processing_center/staged/" not in source
        or not (
            "/structured/native/" in source
            or "/native/" in source
        )
        or "/source/native/" not in destination
        or source == destination
    ):
        raise JsonNativePromotionFailed(
            "Invalid native source or destination."
        )

    original = read_staged(source)

    if not isinstance(original, bytes) or not original:
        raise JsonNativePromotionFailed(
            "Original staged JSON is missing or empty."
        )

    original_sha = hashlib.sha256(original).hexdigest()

    existing = read_final(destination)

    if existing is not None:
        if not isinstance(existing, bytes) or existing != original:
            raise JsonNativePromotionFailed(
                "Existing Files native differs from staged source. "
                "Overwrite prohibited."
            )
        status = "already_promoted_verified"
    else:
        try:
            write_final(destination, original)
        except Exception as exc:
            raise JsonNativePromotionFailed(
                "Native promotion write failed."
            ) from exc

        status = "promoted"

    verified = read_final(destination)

    if not isinstance(verified, bytes):
        raise JsonNativePromotionFailed(
            "Promoted native could not be read back."
        )

    if hashlib.sha256(verified).hexdigest() != original_sha:
        raise JsonNativePromotionFailed(
            "Promoted native hash verification failed."
        )

    if verified != original:
        raise JsonNativePromotionFailed(
            "Promoted native bytes do not match source."
        )

    return {
        "doc_id": contract["doc_id"],
        "source_job_id": contract["source_job_id"],
        "status": status,
        "source_native_path": destination,
        "sha256": original_sha,
        "bytes": len(original),
        "verified": True,
        "generate_csv": False,
    }