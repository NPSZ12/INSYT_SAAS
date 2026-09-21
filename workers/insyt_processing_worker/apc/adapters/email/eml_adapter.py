from __future__ import annotations

import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from ..base import (
    AdapterContext,
    AdapterResult,
    PreparedChild,
)


class EmlAdapter:
    """
    INSYT adapter for RFC/MIME EML email files.

    Responsibilities:
      - parse email metadata
      - identify body content
      - extract attachments
      - return attachment artifacts to APC

    Responsibilities intentionally NOT handled here:
      - INSYT Doc ID assignment
      - hashing/dedupe
      - processing sets
      - Detection
      - promotion
      - review

    Those remain normal APC responsibilities.
    """

    name = "eml"

    extensions = (
        ".eml",
    )

    def process(
        self,
        context: AdapterContext,
    ) -> AdapterResult:
        try:
            message = self._load_message(
                context.source_path
            )

            metadata = self._extract_metadata(
                message
            )

            body = self._extract_body(
                message
            )

            extracted_text_path = (
                self._write_body_text(
                    body=body,
                    context=context,
                )
            )

            children = self._extract_attachments(
                message=message,
                context=context,
            )

            metadata["attachment_count"] = len(
                children
            )

            metadata["has_attachments"] = bool(
                children
            )

            metadata["body_character_count"] = len(
                body
            )


            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=context.file_id,
                children=children,
                family_id=context.family_id,
                parent_file_id=(
                    context.parent_file_id
                ),
                requires_ocr=False,
                resume_stage="post_expansion",
                metadata=metadata,
                extracted_text_path=(
                    str(extracted_text_path)
                    if extracted_text_path
                    else None
                ),
            )

        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                family_id=context.family_id,
                parent_file_id=(
                    context.parent_file_id
                ),
                resume_stage="post_expansion",
                error=str(exc),
            )

    @staticmethod
    def _load_message(
        source_path: Path,
    ) -> Message:
        with source_path.open("rb") as handle:
            return BytesParser(
                policy=policy.default
            ).parse(handle)

    @staticmethod
    def _header(
        message: Message,
        name: str,
    ) -> str:
        value = message.get(name)

        if value is None:
            return ""

        return str(value).strip()

    def _extract_metadata(
        self,
        message: Message,
    ) -> dict[str, Any]:
        return {
            "message_id": self._header(
                message,
                "Message-ID",
            ),
            "subject": self._header(
                message,
                "Subject",
            ),
            "from": self._header(
                message,
                "From",
            ),
            "to": self._header(
                message,
                "To",
            ),
            "cc": self._header(
                message,
                "Cc",
            ),
            "bcc": self._header(
                message,
                "Bcc",
            ),
            "date": self._header(
                message,
                "Date",
            ),
            "reply_to": self._header(
                message,
                "Reply-To",
            ),
            "in_reply_to": self._header(
                message,
                "In-Reply-To",
            ),
            "references": self._header(
                message,
                "References",
            ),
        }

    @staticmethod
    def _extract_body(
        message: Message,
    ) -> str:
        plain_parts: list[str] = []
        html_parts: list[str] = []

        if not message.is_multipart():
            content_type = message.get_content_type()

            try:
                content = message.get_content()
            except Exception:
                content = ""

            if content_type == "text/plain":
                return str(content or "")

            if content_type == "text/html":
                return str(content or "")

            return ""

        for part in message.walk():
            if part.is_multipart():
                continue

            disposition = (
                part.get_content_disposition()
            )

            #
            # Attachments are not part of the parent
            # email body.
            #
            if disposition == "attachment":
                continue

            content_type = part.get_content_type()

            if content_type not in {
                "text/plain",
                "text/html",
            }:
                continue

            try:
                content = str(
                    part.get_content() or ""
                )
            except Exception:
                continue

            if content_type == "text/plain":
                plain_parts.append(content)
            else:
                html_parts.append(content)

        #
        # Prefer actual plain-text email content.
        #
        if plain_parts:
            return "\n\n".join(
                plain_parts
            ).strip()

        #
        # HTML remains available when no text/plain
        # representation was supplied by the sender.
        #
        return "\n\n".join(
            html_parts
        ).strip()

    def _extract_attachments(
        self,
        *,
        message: Message,
        context: AdapterContext,
    ) -> list[PreparedChild]:
        attachments: list[PreparedChild] = []

        attachment_parts = []

        for part in message.walk():
            if part.is_multipart():
                continue

            filename = part.get_filename()

            disposition = (
                part.get_content_disposition()
            )

            if (
                disposition == "attachment"
                or filename
            ):
                attachment_parts.append(
                    part
                )

        if not attachment_parts:
            return []

        if context.work_dir is None:
            raise RuntimeError(
                "EML contains attachments but no "
                "adapter work_dir was provided."
            )

        attachment_dir = (
            context.work_dir
            / "attachments"
        )

        attachment_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        for ordinal, part in enumerate(
            attachment_parts,
            start=1,
        ):
            raw_name = (
                part.get_filename()
                or f"Attachment_{ordinal:04d}.bin"
            )

            safe_name = self._safe_filename(
                raw_name
            )

            output_path = self._unique_path(
                attachment_dir,
                safe_name,
            )

            payload = part.get_payload(
                decode=True
            )

            if payload is None:
                payload = b""

            output_path.write_bytes(
                payload
            )

            extension = (
                output_path.suffix.lower()
                or None
            )

            attachments.append(
                PreparedChild(
                    source_path=output_path,
                    normalized_path=(
                        f"{context.normalized_path}"
                        f"!/attachments/"
                        f"{output_path.name}"
                    ),
                    relationship="email_attachment",
                    original_name=str(raw_name),
                    extension=extension,
                    metadata={
                        "attachment_ordinal": ordinal,
                        "content_type": (
                            part.get_content_type()
                        ),
                        "content_disposition": (
                            part.get_content_disposition()
                            or ""
                        ),
                        "parent_file_id": (
                            context.file_id
                        ),
                    },
                )
            )

        return attachments

    @staticmethod
    def _write_body_text(
        *,
        body: str,
        context: AdapterContext,
    ) -> Path | None:
        """
        Write the clean parent-email body as the native
        text artifact used by downstream INSYT stages.

        Do not use the raw MIME EML bytes as Detection text.
        """

        value = str(
            body or ""
        ).strip()

        if not value:
            return None

        if context.work_dir is None:
            raise RuntimeError(
                "EML body extraction requires "
                "an adapter work_dir."
            )

        text_dir = (
            context.work_dir
            / "text"
        )

        text_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        text_path = (
            text_dir
            / "email_body.txt"
        )

        text_path.write_text(
            value,
            encoding="utf-8",
        )

        return text_path

    @staticmethod
    def _safe_filename(
        filename: str,
    ) -> str:
        value = str(
            filename or ""
        ).strip()

        value = value.replace(
            "\\",
            "_",
        ).replace(
            "/",
            "_",
        )

        value = re.sub(
            r'[\x00-\x1f<>:"|?*]',
            "_",
            value,
        )

        value = value.strip(
            " ."
        )

        if not value:
            return "Attachment.bin"

        return value

    @staticmethod
    def _unique_path(
        directory: Path,
        filename: str,
    ) -> Path:
        candidate = (
            directory
            / filename
        )

        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix

        ordinal = 2

        while True:
            candidate = (
                directory
                / f"{stem}_{ordinal}{suffix}"
            )

            if not candidate.exists():
                return candidate

            ordinal += 1


EML_ADAPTER = EmlAdapter()