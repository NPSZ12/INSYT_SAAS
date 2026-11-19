"""Create-only Cyber2 registration from independently verified native JSON."""

from .native_json_handoff import (
    build_native_json_intake_record,
    verify_existing_native_json_intake,
)


def register_verified_native_json(
    *,
    workspace,
    client,
    project,
    project_base,
    doc_id,
    original_filename,
    source_row,
    staged_path,
    final_path,
    read_staged,
    read_final,
    read_index,
    create_index,
):
    """Registration only. Never promotes, rewrites native, or creates CSV."""

    source_job_id = str(source_row.get("source_job_id") or "").strip()

    expected_prefix = (
        f"{project_base}/processing_center/staged/{source_job_id}/"
    )

    if (
        not source_job_id
        or not staged_path.startswith(expected_prefix)
        or not staged_path[len(expected_prefix):].startswith("native/")
        or not staged_path.endswith(
            f"/{doc_id}.{final_path.rsplit('.', 1)[-1]}"
        )
    ):
        raise ValueError("Invalid staged source provenance.")

    original = read_staged(staged_path)
    final = read_final(final_path)

    if not isinstance(original, bytes) or not original:
        raise ValueError("Original staged JSON is unavailable.")

    if not isinstance(final, bytes) or not final:
        raise ValueError("Promoted Files JSON is unavailable.")

    if original != final:
        raise ValueError(
            "Files JSON differs from independently staged original."
        )

    import hashlib
    staged_hash = hashlib.sha256(original).hexdigest()

    expected = build_native_json_intake_record(
        workspace=workspace,
        client=client,
        project=project,
        project_base=project_base,
        doc_id=doc_id,
        native_path=final_path,
        native_bytes=final,
        expected_source_sha256=staged_hash,
        original_filename=original_filename,
        source_row=source_row,
    )

    index_path = expected["intake_index_path"]
    existing = read_index(index_path)

    if existing is not None:
        verify_existing_native_json_intake(existing, expected)
        return {
            "status": "already_registered_verified",
            "doc_id": doc_id,
            "intake_index_path": index_path,
            "source_profile": expected["source_profile"],
            "verified": True,
            "csv_generated": False,
        }

    try:
        create_index(index_path, expected)
    except FileExistsError:
        # Handle a concurrent registration without overwriting it.
        concurrent = read_index(index_path)
        verify_existing_native_json_intake(concurrent, expected)

    saved = read_index(index_path)
    verify_existing_native_json_intake(saved, expected)

    return {
        "status": "registered_verified",
        "doc_id": doc_id,
        "intake_index_path": index_path,
        "source_profile": expected["source_profile"],
        "verified": True,
        "csv_generated": False,
    }
