from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AdapterContext:
    """
    Standard input supplied to a file-type adapter.

    The adapter receives only the information needed to perform
    file-type-specific preparation. Shared APC processing remains
    outside the adapter.
    """

    job_id: str
    matter_id: str
    file_id: str

    source_path: Path
    normalized_path: str
    extension: str

    #
    # Temporary/preparation location where an adapter may emit
    # extracted child files or normalized artifacts.
    #
    # These artifacts are subsequently registered by the normal
    # APC pipeline. The adapter itself does not assign INSYT IDs.
    #
    work_dir: Path | None = None

    parent_file_id: str | None = None
    family_id: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class PreparedChild:
    """
    A physical/logical child produced by a file-type adapter.
    """

    source_path: Path
    normalized_path: str

    relationship: str
    original_name: str | None = None
    extension: str | None = None

    #
    # True when this child starts a new logical Family
    # instead of inheriting the parent/container Family.
    #
    # Example:
    #     PST -> EML
    #     The EML begins its own email Family, while its
    #     subsequent attachments inherit that EML Family.
    #
    start_new_family: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class AdapterResult:
    """
    Standard output from every adapter.

    File-type-specific work ends here. The normal APC pipeline
    consumes this result and resumes shared processing.
    """

    adapter_name: str
    handled: bool
    status: str

    source_file_id: str

    children: list[PreparedChild] = field(
        default_factory=list
    )

    structured_outputs: list[str] = field(
        default_factory=list
    )

    extracted_text_path: str | None = None

    family_id: str | None = None
    parent_file_id: str | None = None

    requires_ocr: bool | None = None

    #
    # Normal point at which APC should resume after adapter work.
    #
    resume_stage: str = "post_expansion"

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    error: str | None = None


class FileAdapter(Protocol):
    """
    Common contract implemented by all INSYT file adapters.
    """

    name: str
    extensions: tuple[str, ...]

    def process(
        self,
        context: AdapterContext,
    ) -> AdapterResult:
        ...