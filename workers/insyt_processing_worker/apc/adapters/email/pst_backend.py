from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass
class PstMessage:
    """
    One message extracted from a PST mailbox.

    The PST backend supplies mailbox-specific information.
    The PST adapter converts the result into an EML child so
    normal INSYT EML processing can take over.
    """

    folder_path: str

    subject: str = ""
    sender: str = ""
    to: str = ""
    cc: str = ""
    bcc: str = ""

    sent_at: str = ""
    received_at: str = ""

    message_id: str = ""

    plain_body: str = ""
    html_body: str = ""

    attachments: list[
        tuple[str, bytes, str]
    ] = field(
        default_factory=list
    )
    #
    # Some PST backends, such as readpst, can produce
    # a complete RFC822/EML representation directly.
    #
    # When available, preserve those bytes rather than
    # rebuilding the message and potentially losing
    # transport/MIME details.
    #
    raw_eml_bytes: bytes | None = None

    source_name: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


class PstBackend(Protocol):
    """
    Backend contract for reading a PST.

    The adapter itself does not care whether the eventual
    implementation uses libpff, pypff, readpst, or another
    supported mailbox parser.
    """

    name: str

    def iter_messages(
        self,
        pst_path: Path,
    ) -> Iterable[PstMessage]:
        ...