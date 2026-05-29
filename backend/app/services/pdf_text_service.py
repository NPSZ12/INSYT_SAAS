import io
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath

from pypdf import PdfReader


def get_text_blob_path(source_blob_path: str) -> str:
    source_blob_path = source_blob_path.strip("/")
    path = PurePosixPath(source_blob_path)

    parts = list(path.parts)

    if "source" in parts and "native" in parts:
        native_index = parts.index("native")
        parts[native_index] = "text"

        text_path = PurePosixPath(*parts).with_suffix(".txt")
        return str(text_path)

    return str(
        path.parent / "source" / "text" / f"{path.stem}.txt"
    )


def get_metadata_blob_path(text_blob_path: str) -> str:
    return str(
        PurePosixPath(text_blob_path).with_suffix(".metadata.json")
    )


def extract_pdf_text_from_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))

    pages = []

    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append(
            f"\n\n----- PAGE {index} -----\n\n{page_text.strip()}"
        )

    return "\n".join(pages).strip()


def get_or_create_extracted_text(
    container,
    source_blob_path: str,
) -> dict:
    source_blob_path = source_blob_path.strip("/")
    text_blob_path = get_text_blob_path(source_blob_path)
    metadata_blob_path = get_metadata_blob_path(text_blob_path)

    text_blob = container.get_blob_client(text_blob_path)

    if text_blob.exists():
        text = text_blob.download_blob().readall().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "text": text,
            "text_blob_path": text_blob_path,
            "metadata_blob_path": metadata_blob_path,
            "created": False,
        }

    source_blob = container.get_blob_client(source_blob_path)

    if not source_blob.exists():
        raise FileNotFoundError(
            f"Source PDF not found: {source_blob_path}"
        )

    pdf_bytes = source_blob.download_blob().readall()
    text = extract_pdf_text_from_bytes(pdf_bytes)

    text_blob.upload_blob(
        text.encode("utf-8"),
        overwrite=True,
        content_type="text/plain; charset=utf-8",
    )

    metadata = {
        "source_file_name": PurePosixPath(source_blob_path).name,
        "source_blob_path": source_blob_path,
        "text_blob_path": text_blob_path,
        "metadata_blob_path": metadata_blob_path,
        "extraction_method": "pypdf",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    metadata_blob = container.get_blob_client(metadata_blob_path)

    metadata_blob.upload_blob(
        json.dumps(metadata, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )

    return {
        "text": text,
        "text_blob_path": text_blob_path,
        "metadata_blob_path": metadata_blob_path,
        "created": True,
    }