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
    text_source = contract.get("staged_text_path")
    text_destination = contract.get("final_text_path")
    doc_id = contract.get("doc_id")
    job_id = contract.get("source_job_id")

    if (
        not isinstance(doc_id, str)
        or not isinstance(job_id, str)
        or not isinstance(source, str)
        or not isinstance(destination, str)
        or not isinstance(text_source, str)
        or not isinstance(text_destination, str)
        or "/processing_center/staged/" not in source
        or "/native/" not in source
        or "/xl/native/" in source
        or "/source/native/" not in destination
        or source == destination
    ):
        raise JsonNativePromotionFailed(
            "Invalid native source or destination."
        )

    expected_staged_text = (
        source.rsplit("/native/", 1)[0]
        + f"/text/{doc_id}.txt"
    )
    expected_final_text = (
        destination.rsplit("/source/native/", 1)[0]
        + f"/source/text/{doc_id}.txt"
    )

    if (
        text_source != expected_staged_text
        or text_destination != expected_final_text
        or f"/staged/{job_id}/" not in text_source
    ):
        raise JsonNativePromotionFailed(
            "JSON extracted-text lineage mismatch."
        )

    # Read and validate both original staged artifacts before writes.
    original = read_staged(source)
    original_text = read_staged(text_source)

    if not isinstance(original, bytes) or not original:
        raise JsonNativePromotionFailed(
            "Original staged JSON is missing or empty."
        )

    if not isinstance(original_text, bytes) or not original_text:
        raise JsonNativePromotionFailed(
            "Original staged extracted text is missing or empty."
        )

    original_sha = hashlib.sha256(original).hexdigest()
    text_sha = hashlib.sha256(original_text).hexdigest()

    existing = read_final(destination)
    existing_text = read_final(text_destination)

    # Never overwrite mismatched existing native or text artifacts.
    if existing is not None and (
        not isinstance(existing, bytes) or existing != original
    ):
        raise JsonNativePromotionFailed(
            "Existing Files native differs from staged source. "
            "Overwrite prohibited."
        )

    if existing_text is not None and (
        not isinstance(existing_text, bytes)
        or existing_text != original_text
    ):
        raise JsonNativePromotionFailed(
            "Existing Files text differs from staged text. "
            "Overwrite prohibited."
        )

    def ensure_final(path, expected, label):
        current = read_final(path)

        if current is None:
            try:
                write_final(path, expected)
            except Exception as exc:
                # A concurrent create-only writer may have won.
                # Accept only byte-identical, verified results.
                current = read_final(path)
                if current != expected:
                    raise JsonNativePromotionFailed(
                        f"{label} promotion write failed."
                    ) from exc

        verified = read_final(path)

        if not isinstance(verified, bytes):
            raise JsonNativePromotionFailed(
                f"{label} could not be read back."
            )

        if (
            verified != expected
            or hashlib.sha256(verified).hexdigest()
            != hashlib.sha256(expected).hexdigest()
        ):
            raise JsonNativePromotionFailed(
                f"{label} byte or SHA256 verification failed."
            )

    ensure_final(destination, original, "Native JSON")
    ensure_final(text_destination, original_text, "JSON extracted text")

    status = (
        "already_promoted_verified"
        if existing is not None
        else "promoted"
    )
    text_status = (
        "already_promoted_verified"
        if existing_text is not None
        else "promoted"
    )

    return {
        "doc_id": contract["doc_id"],
        "source_job_id": contract["source_job_id"],
        "status": status,
        "source_native_path": destination,
        "sha256": original_sha,
        "bytes": len(original),
        "verified": True,
        "text_status": text_status,
        "text_path": text_destination,
        "text_sha256": text_sha,
        "text_bytes": len(original_text),
        "text_verified": True,
        "generate_csv": False,
    }