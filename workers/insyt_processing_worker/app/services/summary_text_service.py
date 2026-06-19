import io
import json
import os

from pypdf import PdfReader

from app.services.summary_outline_service import (
    build_summary_extract_payload,
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


def extract_text_with_pypdf(pdf_bytes: bytes):
    """
    Extracts text without modifying the original PDF.

    The original PDF remains clickable because this only reads bytes and
    writes a separate TXT file.
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

    The original PDF in source/native is not modified, converted, flattened,
    or reprinted. This preserves embedded/clickable PDF links.
    """

    if "/source/native/" not in native_blob_name:
        return None

    text_blob_name = get_summary_text_blob_path(native_blob_name)

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

    create_summary_extract_file(
        container=container,
        native_blob_name=native_blob_name,
        text_blob_name=text_blob_name,
        extracted_text=text,
    )

    return text_blob_name