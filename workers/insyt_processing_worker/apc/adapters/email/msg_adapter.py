from __future__ import annotations

import shutil
import tempfile

import re
from pathlib import Path
from typing import Any

from ..base import AdapterContext, AdapterResult, PreparedChild


class MsgAdapter:
    """Prepare Outlook MSG text and attachments; APC owns IDs and lifecycle."""

    name = "msg"
    extensions = (".msg",)

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, bytes):
            if value.startswith(
                (b"\xff\xfe", b"\xfe\xff")
            ):
                return value.decode(
                    "utf-16"
                ).strip("\x00 \r\n\t")

            if value.startswith(b"\xef\xbb\xbf"):
                return value.decode(
                    "utf-8-sig"
                ).strip("\x00 \r\n\t")

            # Recognize common BOM-less UTF-16LE
            # text without automatically reinterpreting
            # arbitrary binary properties.
            if (
                len(value) >= 4
                and len(value) % 2 == 0
            ):
                odd_bytes = value[1::2]

                nul_ratio = (
                    odd_bytes.count(0)
                    / len(odd_bytes)
                )

                if nul_ratio >= 0.6:
                    try:
                        return value.decode(
                            "utf-16-le"
                        ).strip("\x00 \r\n\t")
                    except UnicodeDecodeError:
                        pass

            for encoding in (
                "utf-8",
                "cp1252",
            ):
                try:
                    return value.decode(
                        encoding
                    ).strip("\x00 \r\n\t")
                except UnicodeDecodeError:
                    continue

            raise UnicodeError(
                "MSG property cannot be decoded"
            )

        return str(value).strip(
            "\x00 \r\n\t"
        )

    @classmethod
    def _first(cls, *values: Any) -> str:
        for value in values:
            result = cls._text(value)
            if result:
                return result
        return ""

    @classmethod
    def _header(cls, header: Any, name: str) -> str:
        try:
            return cls._text(header.get(name)) if header is not None else ""
        except (AttributeError, TypeError):
            return ""

    @classmethod
    def _attachment_name(cls, attachment: Any, ordinal: int) -> str:
        for attr in ("longFilename", "shortFilename", "displayName", "filename", "name"):
            name = cls._text(getattr(attachment, attr, None))
            if name:
                return name
        getter = getattr(attachment, "getFilename", None)
        if callable(getter):
            name = cls._text(getter())
            if name:
                return name
        return f"Attachment_{ordinal:04d}.bin"

    @staticmethod
    def _safe_name(name: str) -> str:
        safe = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" ._")
        return safe[:180] or "attachment.bin"

    @staticmethod
    def _save_attachment(
        attachment: Any,
        output: Path,
    ) -> None:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = getattr(
            attachment,
            "data",
            None,
        )

        if isinstance(
            payload,
            (bytes, bytearray),
        ):
            output.write_bytes(bytes(payload))
            return

        save_method = getattr(
            attachment,
            "save",
            None,
        )

        if not callable(save_method):
            raise ValueError(
                "MSG attachment has neither binary "
                "data nor a supported save method: "
                f"{output.name}"
            )

        # Keep extract-msg temporary outputs separate
        # from the final registered attachment artifact.
        with tempfile.TemporaryDirectory(
            prefix="insyt_msg_",
            dir=str(output.parent),
        ) as temporary_directory:

            temporary_path = Path(
                temporary_directory
            )

            save_method(
                customPath=str(temporary_path)
            )

            candidates = [
                candidate
                for candidate in temporary_path.rglob("*")
                if candidate.is_file()
            ]

            if len(candidates) != 1:
                raise ValueError(
                    "MSG attachment save produced "
                    f"{len(candidates)} files; expected "
                    "exactly one validated artifact: "
                    f"{output.name}"
                )

            source = candidates[0]

            if (
                output.suffix
                and source.suffix.lower()
                != output.suffix.lower()
            ):
                raise ValueError(
                    "MSG attachment output extension "
                    "does not match its source artifact: "
                    f"{source.name} -> {output.name}"
                )

            shutil.copyfile(
                source,
                output,
            )

    def process(self, context: AdapterContext) -> AdapterResult:
        message = None
        try:
            import extract_msg

            if context.work_dir is None:
                raise ValueError("MSG adapter requires a work_dir")
            work_dir = Path(context.work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            message = extract_msg.openMsg(str(context.source_path))
            header = getattr(message, "header", None)
            fields = [
                ("From", self._first(self._header(header, "From"), getattr(message, "sender", None))),
                ("Sender", self._text(getattr(message, "sender", None))),
                ("To", self._text(getattr(message, "to", None))),
                ("Cc", self._text(getattr(message, "cc", None))),
                ("Bcc", self._text(getattr(message, "bcc", None))),
                ("Subject", self._first(getattr(message, "subject", None), self._header(header, "Subject"))),
                ("Sent", self._first(getattr(message, "date", None), self._header(header, "Date"))),
                ("Received", self._first(self._header(header, "Received-Date"), self._header(header, "Delivery-Date"))),
                ("Message-ID", self._first(getattr(message, "messageId", None), self._header(header, "Message-ID"))),
                ("Conversation Topic", self._text(getattr(message, "conversationTopic", None))),
                ("Importance", self._text(getattr(message, "importance", None))),
            ]
            body = self._text(getattr(message, "body", None))
            # A parser error is not equivalent to an attachment-free email.
            attachments = list(message.attachments or [])
            children: list[PreparedChild] = []
            att_dir = work_dir / "attachments"
            for ordinal, attachment in enumerate(attachments, start=1):
                original_name = self._attachment_name(attachment, ordinal)
                name = self._safe_name(original_name)
                output = att_dir / f"{ordinal:04d}_{name}"
                att_dir.mkdir(parents=True, exist_ok=True)
                self._save_attachment(attachment, output)
                children.append(
                    PreparedChild(
                        source_path=output,
                        normalized_path=f"{context.normalized_path}!/attachments/{output.name}",
                        relationship="email_attachment",
                        original_name=original_name,
                        extension=output.suffix.lower() or None,
                        metadata={"attachment_ordinal": ordinal, "parent_file_id": context.file_id},
                    )
                )
            if not body and not any(value for _, value in fields) and not children:
                raise ValueError("MSG has no extractable body, metadata or attachments")
            lines = ["INSYT EMAIL METADATA", ""]
            lines += [f"{name}: {value}" for name, value in fields]
            lines += [f"Attachment Count: {len(attachments)}", "", "Attachments:"]
            lines += [f"- {item.original_name}" for item in children] or ["- None"]
            lines += ["", "--- EMAIL BODY ---", "", body]
            text_dir = work_dir / "text"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_path = text_dir / "email_body.txt"
            text_path.write_text("\n".join(lines).strip(), encoding="utf-8")
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="completed",
                source_file_id=context.file_id,
                children=children,
                extracted_text_path=str(text_path),
                family_id=context.family_id,
                parent_file_id=context.parent_file_id,
                requires_ocr=False,
                resume_stage="post_expansion",
                metadata={"attachment_count": len(attachments), "has_attachments": bool(attachments)},
            )
        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                family_id=context.family_id,
                parent_file_id=context.parent_file_id,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if message is not None:
                try:
                    message.close()
                except Exception:
                    pass


MSG_ADAPTER = MsgAdapter()