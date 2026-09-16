import json
import os
import tempfile
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from app.api.processing_center import (
    copy_blob,
    delete_blob_if_exists,
    determine_viewer_type,
    errors_path,
    extract_text_basic,
    final_native_path,
    final_text_path,
    get_blob_service_client,
    get_container_name,
    get_doc_id,
    get_extension,
    get_processing_queue_client,
    in_progress_path,
    now_iso,
    preview_html_path,
    preview_pdf_path,
    processed_metadata_path,
    processed_native_path,
    processed_text_path,
    read_json_blob,
    update_manifest_item,
    write_json_blob,
)


def update_job(container, job_blob_path: str, updates: dict):
    job = read_json_blob(container, job_blob_path, {})

    if not job:
        raise RuntimeError(f"Job not found: {job_blob_path}")

    job.update(updates)
    job["last_updated_at"] = now_iso()

    write_json_blob(container, job_blob_path, job)

    return job


def process_one_upload(
    workspace: str,
    client: str,
    project_id: str,
    upload_blob_path: str,
):
    container_name = get_container_name(workspace)
    service = get_blob_service_client()
    container = service.get_container_client(container_name)

    file_name = upload_blob_path.split("/")[-1]

    if not file_name:
        raise RuntimeError(f"Invalid upload path: {upload_blob_path}")

    doc_id = get_doc_id(file_name)
    progress_path = in_progress_path(client, project_id, file_name)

    update_manifest_item(
        container,
        client,
        project_id,
        file_name,
        {
            "doc_id": doc_id,
            "extension": get_extension(file_name),
            "status": "In Progress",
            "started_at": now_iso(),
            "upload_path": upload_blob_path,
            "in_progress_path": progress_path,
            "error": "",
        },
    )

    copy_blob(container, upload_blob_path, progress_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        local_file_path = os.path.join(tmpdir, file_name)

        with open(local_file_path, "wb") as f:
            f.write(
                container.get_blob_client(progress_path)
                .download_blob()
                .readall()
            )

        extraction_result = extract_text_basic(
            local_file_path,
            file_name,
        )

    extracted_text = extraction_result.get("text", "")

    processed_native = processed_native_path(
        client,
        project_id,
        file_name,
    )

    processed_text = processed_text_path(
        client,
        project_id,
        doc_id,
    )

    metadata_path = processed_metadata_path(
        client,
        project_id,
        doc_id,
    )

    final_native = final_native_path(
        client,
        project_id,
        file_name,
    )

    final_text = final_text_path(
        client,
        project_id,
        doc_id,
    )

    extension = get_extension(file_name)
    viewer_type = determine_viewer_type(file_name, extracted_text)

    preview_pdf = preview_pdf_path(
        client,
        project_id,
        doc_id,
    )

    preview_html = preview_html_path(
        client,
        project_id,
        doc_id,
    )

    copy_blob(container, progress_path, processed_native)
    copy_blob(container, progress_path, final_native)

    container.get_blob_client(processed_text).upload_blob(
        extracted_text,
        overwrite=True,
    )

    container.get_blob_client(final_text).upload_blob(
        extracted_text,
        overwrite=True,
    )

    metadata = {
        "doc_id": doc_id,
        "file_name": file_name,
        "extension": extension,
        "workspace": workspace,
        "client": client,
        "project_id": project_id,
        "status": "Processed",
        "processed_at": now_iso(),
        "upload_path": upload_blob_path,
        "processed_native_path": processed_native,
        "processed_text_path": processed_text,
        "final_native_path": final_native,
        "final_text_path": final_text,
        "preview_pdf_path": preview_pdf,
        "preview_html_path": preview_html,
        "viewer_type": viewer_type,
        "preview_available": viewer_type
        in ["pdf", "image", "text", "email"],
        "ocr_status": extraction_result.get("ocr_status", ""),
        "ocr_applied": extraction_result.get("ocr_applied", False),
        "ocr_engine": extraction_result.get("ocr_engine", ""),
        "ocr_page_count": extraction_result.get("ocr_page_count", 0),
        "ocr_text_length": extraction_result.get(
            "ocr_text_length",
            len(extracted_text or ""),
        ),
        "ocr_confidence_score": extraction_result.get(
            "ocr_confidence_score"
        ),
        "ocr_quality": extraction_result.get("ocr_quality", ""),
        "ocr_warning": extraction_result.get("ocr_warning", ""),
        "text_length": len(extracted_text or ""),
        "error": "",
    }

    write_json_blob(container, metadata_path, metadata)

    delete_blob_if_exists(container, upload_blob_path)
    delete_blob_if_exists(container, progress_path)

    update_manifest_item(
        container,
        client,
        project_id,
        file_name,
        metadata,
    )

    return metadata


def process_job_message(message_content: str):
    queue_payload = json.loads(message_content)

    workspace = queue_payload["workspace"]
    client = queue_payload["client"]
    project_id = queue_payload["project_id"]
    job_blob_path = queue_payload["job_blob_path"]

    container_name = get_container_name(workspace)
    service = get_blob_service_client()
    container = service.get_container_client(container_name)

    job = read_json_blob(container, job_blob_path, None)

    if not job:
        raise RuntimeError(f"Job blob not found: {job_blob_path}")

    files = job.get("files", [])

    update_job(
        container,
        job_blob_path,
        {
            "status": "Running",
            "started_at": job.get("started_at") or now_iso(),
            "message": "Processing job running.",
        },
    )

    processed_files = 0
    error_files = 0
    updated_files = []

    for item in files:
        file_name = item.get("file_name", "")
        upload_path = item.get("upload_path", "")

        if not upload_path:
            item["status"] = "Error"
            item["error"] = "Missing upload_path."
            error_files += 1
            updated_files.append(item)
            continue

        try:
            item["status"] = "Running"
            item["started_at"] = now_iso()

            job = update_job(
                container,
                job_blob_path,
                {
                    "files": updated_files + [item] + files[len(updated_files) + 1 :],
                    "processed_files": processed_files,
                    "error_files": error_files,
                    "message": f"Processing {file_name}.",
                },
            )

            metadata = process_one_upload(
                workspace=workspace,
                client=client,
                project_id=project_id,
                upload_blob_path=upload_path,
            )

            item.update(
                {
                    "status": "Processed",
                    "processed_at": metadata.get("processed_at", now_iso()),
                    "doc_id": metadata.get("doc_id", ""),
                    "final_native_path": metadata.get(
                        "final_native_path",
                        "",
                    ),
                    "final_text_path": metadata.get(
                        "final_text_path",
                        "",
                    ),
                    "text_length": metadata.get("text_length", 0),
                    "ocr_status": metadata.get("ocr_status", ""),
                    "ocr_applied": metadata.get("ocr_applied", False),
                    "ocr_quality": metadata.get("ocr_quality", ""),
                    "ocr_confidence_score": metadata.get(
                        "ocr_confidence_score"
                    ),
                    "error": "",
                }
            )

            processed_files += 1

        except Exception as exc:
            message = str(exc)

            error_destination = errors_path(
                client,
                project_id,
                file_name or "unknown_file",
            )

            try:
                copy_blob(container, upload_path, error_destination)
            except Exception:
                pass

            item.update(
                {
                    "status": "Error",
                    "failed_at": now_iso(),
                    "error": message,
                    "error_path": error_destination,
                }
            )

            error_files += 1

        updated_files.append(item)

        update_job(
            container,
            job_blob_path,
            {
                "files": updated_files + files[len(updated_files) :],
                "processed_files": processed_files,
                "error_files": error_files,
                "message": (
                    f"Processed {processed_files} file(s), "
                    f"{error_files} error(s)."
                ),
            },
        )

    final_status = "Completed"

    if error_files and processed_files:
        final_status = "Completed With Errors"
    elif error_files and not processed_files:
        final_status = "Failed"

    update_job(
        container,
        job_blob_path,
        {
            "status": final_status,
            "processed_files": processed_files,
            "error_files": error_files,
            "completed_at": now_iso(),
            "files": updated_files,
            "message": (
                f"Job {final_status}. "
                f"Processed {processed_files} file(s), "
                f"{error_files} error(s)."
            ),
        },
    )


def run_once():
    queue_client = get_processing_queue_client()

    messages = queue_client.receive_messages(
        messages_per_page=1,
        visibility_timeout=300,
    )

    processed_any = False

    for message in messages:
        processed_any = True

        print(f"Processing queue message: {message.id}")

        try:
            process_job_message(message.content)

            queue_client.delete_message(message)

            print("Queue message processed and deleted.")

        except Exception as exc:
            print(f"Worker failed: {type(exc).__name__}: {exc}")
            raise

    if not processed_any:
        print("No processing jobs found.")


if __name__ == "__main__":
    run_once()