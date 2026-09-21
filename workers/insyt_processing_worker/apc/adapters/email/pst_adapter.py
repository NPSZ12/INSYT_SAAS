from __future__ import annotations

import re
from email.message import EmailMessage
from pathlib import Path

from ..base import (
    AdapterContext,
    AdapterResult,
    PreparedChild,
)
from .pst_backend import (
    PstBackend,
    PstMessage,
)


class PstAdapter:
    """
    INSYT PST mailbox adapter.

    PST-specific responsibility:
      - enumerate mailbox folders/messages
      - preserve mailbox/folder provenance
      - emit each email as a canonical EML child

    Normal EML processing then handles:
      - email body
      - headers
      - attachments
      - Family relationships
      - downstream APC processing
    """

    name = "pst"

    extensions = (
        ".pst",
    )

    def __init__(
        self,
        backend: PstBackend,
    ):
        self.backend = backend

    def process(
        self,
        context: AdapterContext,
    ) -> AdapterResult:
        try:
            if context.work_dir is None:
                raise RuntimeError(
                    "PST processing requires "
                    "an adapter work_dir."
                )

            output_dir = (
                context.work_dir
                / "messages"
            )

            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            children: list[
                PreparedChild
            ] = []

            folder_counts: dict[
                str,
                int
            ] = {}

            message_count = 0

            for message_count, message in enumerate(
                self.backend.iter_messages(
                    context.source_path
                ),
                start=1,
            ):
                folder_path = str(
                    message.folder_path
                    or "Mailbox"
                ).strip()

                folder_counts[
                    folder_path
                ] = (
                    folder_counts.get(
                        folder_path,
                        0,
                    )
                    + 1
                )

                eml_path = (
                    self._write_eml(
                        message=message,
                        output_dir=output_dir,
                        ordinal=message_count,
                    )
                )

                logical_folder = (
                    self._safe_logical_folder(
                        folder_path
                    )
                )

                logical_path = (
                    f"{context.normalized_path}"
                    f"!/mailbox/"
                    f"{logical_folder}/"
                    f"{eml_path.name}"
                )

                children.append(
                    PreparedChild(
                        source_path=eml_path,
                        normalized_path=(
                            logical_path
                        ),
                        relationship=(
                            "mailbox_message"
                        ),
                        original_name=(
                            eml_path.name
                        ),
                        extension=".eml",
                        start_new_family=True,
                        metadata={
                            "source_type": (
                                "pst_message"
                            ),
                            "mailbox_format": (
                                "pst"
                            ),
                            "backend": (
                                self.backend.name
                            ),
                            "folder_path": (
                                folder_path
                            ),
                            "message_ordinal": (
                                message_count
                            ),
                            "message_id": (
                                message.message_id
                            ),
                            "subject": (
                                message.subject
                            ),
                            "sent_at": (
                                message.sent_at
                            ),
                            "received_at": (
                                message.received_at
                            ),
                            **dict(
                                message.metadata
                                or {}
                            ),
                        },
                    )
                )

            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=(
                    context.file_id
                ),
                children=children,
                family_id=(
                    context.family_id
                ),
                parent_file_id=(
                    context.parent_file_id
                ),
                requires_ocr=False,
                resume_stage="post_expansion",
                metadata={
                    "mailbox_format": "pst",
                    "backend": (
                        self.backend.name
                    ),
                    "message_count": (
                        message_count
                    ),
                    "folder_count": len(
                        folder_counts
                    ),
                    "folder_message_counts": (
                        folder_counts
                    ),
                },
            )

        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=(
                    context.file_id
                ),
                family_id=(
                    context.family_id
                ),
                parent_file_id=(
                    context.parent_file_id
                ),
                resume_stage="post_expansion",
                error=str(exc),
            )

    @staticmethod
    def _write_eml(
        *,
        message: PstMessage,
        output_dir: Path,
        ordinal: int,
    ) -> Path:
        safe_subject = (
            PstAdapter._safe_filename(
                message.subject
                or "Message"
            )
        )

        safe_subject = (
            safe_subject[:80]
            or "Message"
        )

        output_path = (
            output_dir
            / (
                f"Message_{ordinal:08d}"
                f"__{safe_subject}.eml"
            )
        )

        #
        # Prefer a backend-provided complete EML.
        #
        # This preserves MIME boundaries, embedded
        # attachments, transport headers, inline content,
        # and other RFC822 details exactly as exported.
        #
        if message.raw_eml_bytes is not None:
            output_path.write_bytes(
                message.raw_eml_bytes
            )

            return output_path

        #
        # Fallback for PST backends that provide parsed
        # message fields rather than complete EML bytes.
        #
        eml = EmailMessage()

        if message.message_id:
            eml["Message-ID"] = (
                message.message_id
            )

        if message.subject:
            eml["Subject"] = (
                message.subject
            )

        if message.sender:
            eml["From"] = (
                message.sender
            )

        if message.to:
            eml["To"] = (
                message.to
            )

        if message.cc:
            eml["Cc"] = (
                message.cc
            )

        if message.bcc:
            eml["Bcc"] = (
                message.bcc
            )

        if message.sent_at:
            eml["Date"] = (
                message.sent_at
            )

        plain_body = str(
            message.plain_body
            or ""
        )

        html_body = str(
            message.html_body
            or ""
        )

        if plain_body:
            eml.set_content(
                plain_body
            )

            if html_body:
                eml.add_alternative(
                    html_body,
                    subtype="html",
                )

        elif html_body:
            eml.set_content(
                "HTML email content"
            )

            eml.add_alternative(
                html_body,
                subtype="html",
            )

        else:
            eml.set_content("")

        for (
            filename,
            payload,
            content_type,
        ) in message.attachments:

            maintype = (
                "application"
            )

            subtype = (
                "octet-stream"
            )

            if (
                content_type
                and "/"
                in content_type
            ):
                (
                    maintype,
                    subtype,
                ) = content_type.split(
                    "/",
                    1,
                )

            eml.add_attachment(
                bytes(
                    payload
                    or b""
                ),
                maintype=maintype,
                subtype=subtype,
                filename=(
                    filename
                    or "Attachment.bin"
                ),
            )

        output_path.write_bytes(
            eml.as_bytes()
        )

        return output_path

    @staticmethod
    def _safe_filename(
        value: str,
    ) -> str:
        clean = str(
            value or ""
        ).strip()

        clean = re.sub(
            r'[\x00-\x1f<>:"/\\|?*]',
            "_",
            clean,
        )

        clean = re.sub(
            r"\s+",
            "_",
            clean,
        )

        return clean.strip(
            " ._"
        )

    @staticmethod
    def _safe_logical_folder(
        value: str,
    ) -> str:
        parts = [
            PstAdapter._safe_filename(
                part
            )
            for part in re.split(
                r"[\\/]+",
                str(
                    value
                    or "Mailbox"
                ),
            )
        ]

        parts = [
            part
            for part in parts
            if part
        ]

        return (
            "/".join(parts)
            or "Mailbox"
        )