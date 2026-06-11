import io
import os

from pypdf import PdfReader


def get_summary_text_blob_path(native_blob_name: str):
    text_blob_name = native_blob_name.replace(
        "/source/native/",
        "/source/text/",
    )

    return os.path.splitext(text_blob_name)[0] + ".txt"


def extract_text_with_pypdf(pdf_bytes: bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append(
            f"\n\n--- Page {page_number} ---\n\n{page_text}"
        )

    return "\n".join(pages).strip()


def create_summary_text_file(
    container,
    native_blob_name: str,
    pdf_bytes: bytes,
):
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

    return text_blob_name