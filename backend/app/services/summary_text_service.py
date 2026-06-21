import io
import json
import os

from pypdf import PdfReader

from app.services.summary_outline_service import (
    build_summary_extract_payload,
)

from app.services.summaries_large_text_builder import (
    build_summaries_large_pdf_text_from_bytes,
    upload_summaries_large_text_result_to_blob,
)


def get_summary_text_blob_path(native_blob_name: str):
    text_blob_name = native_blob_name.replace(
        "/source/native/",
        "/source/text/",
    )

    return os.path.splitext(text_blob_name)[0] + ".txt"


def get_summary_extract_blob_path(native_blob_name: str):
    extract_blob_name = native_blob_name.replace(
        "/source/native/",
        "/source/summary_extracts/",
    )

    return os.path.splitext(extract_blob_name)[0] + ".json"


def get_doc_id_from_native_blob_name(native_blob_name: str):
    filename = os.path.basename(native_blob_name or "")
    doc_id, _extension = os.path.splitext(filename)

    return doc_id or filename or "UNKNOWN_DOC"


def get_base_project_path_from_native_blob_name(native_blob_name: str):
    """
    Converts:
      {client}/summaries/{project}/source/native/{pdf}

    Into:
      {client}/summaries/{project}

    This keeps the large Summaries text builder aligned with the existing
    Summaries project folder structure.
    """

    if "/source/native/" not in native_blob_name:
        return None

    return native_blob_name.split("/source/native/", 1)[0].strip("/")


def extract_text_with_pypdf(pdf_bytes: bytes):
    """
    Fallback extractor only.

    The primary Summaries extractor is now the chunked Summaries large PDF
    text builder, which stops before Original Source Medical Records and
    creates full_text.txt, sections.json, manifest.json, and chunks/.
    """

    reader = PdfReader(io.BytesIO(pdf_bytes))

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append(
            f"\n\n--- Page {page_number} ---\n\n{page_text}"
        )

    return "\n".join(pages).strip()


def create_summary_extract_file(
    container,
    native_blob_name: str,
    text_blob_name: str,
    extracted_text: str,
):
    """
    Saves the structured Summaries JSON used by the PDF Outline/QC panes.

    Output:
      source/summary_extracts/{doc_id}.json
    """

    if "/source/native/" not in native_blob_name:
        return None

    extract_blob_name = get_summary_extract_blob_path(native_blob_name)
    doc_id = get_doc_id_from_native_blob_name(native_blob_name)

    payload = build_summary_extract_payload(
        text=extracted_text or "",
        doc_id=doc_id,
        source_pdf_name=os.path.basename(native_blob_name or ""),
        native_pdf_path=native_blob_name,
        text_path=text_blob_name,
        workspace="summaries",
    )

    container.upload_blob(
        name=extract_blob_name,
        data=json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
        overwrite=True,
    )

    return extract_blob_name


def create_summary_text_file(
    container,
    native_blob_name: str,
    pdf_bytes: bytes,
):
    """
    Creates:
      source/text/{doc_id}.txt
      source/summary_extracts/{doc_id}.json
      source/text_extract/{pdf_name}/full_text.txt
      source/text_extract/{pdf_name}/sections.json
      source/text_extract/{pdf_name}/manifest.json
      source/text_extract/{pdf_name}/chunks/*.txt

    The original PDF in source/native is not modified, converted, flattened,
    or reprinted. This preserves embedded/clickable PDF links.
    """

    if "/source/native/" not in native_blob_name:
        return None

    text_blob_name = get_summary_text_blob_path(native_blob_name)
    pdf_name = os.path.basename(native_blob_name or "")
    base_project_path = get_base_project_path_from_native_blob_name(
        native_blob_name
    )

    large_text_result = None
    large_text_upload_result = None

    try:
        large_text_result = build_summaries_large_pdf_text_from_bytes(
            pdf_bytes,
            pdf_name=pdf_name,
            chunk_size=10,
        )

        text = large_text_result.get("full_text") or ""

        if base_project_path:
            large_text_upload_result = upload_summaries_large_text_result_to_blob(
                container_client=container,
                base_project_path=base_project_path,
                result=large_text_result,
            )

    except Exception as exc:
        print(
            "Summaries large PDF text builder failed; "
            f"falling back to pypdf extraction for {native_blob_name}: "
            f"{type(exc).__name__}: {exc}"
        )

        text = extract_text_with_pypdf(pdf_bytes)

    if not text or len(text.strip()) < 50:
        text = (
            f"No extractable text found for "
            f"{os.path.basename(native_blob_name)}."
        )

    container.upload_blob(
        name=text_blob_name,
        data=text.encode("utf-8"),
        overwrite=True,
    )

    extract_blob_name = create_summary_extract_file(
        container=container,
        native_blob_name=native_blob_name,
        text_blob_name=text_blob_name,
        extracted_text=text,
    )

    return {
        "text_blob_name": text_blob_name,
        "extract_blob_name": extract_blob_name,
        "large_text_extract": {
            "status": (
                large_text_upload_result.get("status")
                if large_text_upload_result
                else None
            ),
            "root_prefix": (
                large_text_upload_result.get("root_prefix")
                if large_text_upload_result
                else None
            ),
            "full_text_blob_path": (
                large_text_upload_result.get("full_text_blob_path")
                if large_text_upload_result
                else None
            ),
            "sections_blob_path": (
                large_text_upload_result.get("sections_blob_path")
                if large_text_upload_result
                else None
            ),
            "manifest_blob_path": (
                large_text_upload_result.get("manifest_blob_path")
                if large_text_upload_result
                else None
            ),
            "uploaded_count": (
                large_text_upload_result.get("uploaded_count")
                if large_text_upload_result
                else None
            ),
            "chunks_created": (
                large_text_result.get("manifest", {}).get("chunks_created")
                if large_text_result
                else None
            ),
            "stopped_on_marker": (
                large_text_result.get("manifest", {}).get("stopped_on_marker")
                if large_text_result
                else None
            ),
            "stopped_at_page_range": (
                large_text_result.get("manifest", {}).get("stopped_at_page_range")
                if large_text_result
                else None
            ),
            "detected_qc_titles": (
                large_text_result.get("manifest", {}).get("detected_qc_titles")
                if large_text_result
                else []
            ),
            "missing_qc_titles": (
                large_text_result.get("manifest", {}).get("missing_qc_titles")
                if large_text_result
                else []
            ),
        },
    }
