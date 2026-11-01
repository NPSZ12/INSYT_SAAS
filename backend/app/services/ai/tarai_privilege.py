"""Read-only validation of TARai privilege suggestions.

No Azure calls, storage writes, or automatic Review coding.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PrivilegeClass = Literal[
    "potentially_privileged",
    "not_privileged",
    "needs_review",
]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=2000)


class PrivilegeSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: PrivilegeClass
    rationale: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    reviewer_status: Literal["pending"] = "pending"

    @field_validator("rationale")
    @classmethod
    def require_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Rationale cannot be blank.")
        return value.strip()


def validate_privilege_suggestion(
    *,
    document_text: str,
    suggestion: dict,
) -> PrivilegeSuggestion:
    """Validate AI output against the supplied source text."""

    if not isinstance(document_text, str) or not document_text.strip():
        raise ValueError("Document text is required.")

    result = PrivilegeSuggestion.model_validate(suggestion)

    # AI-generated quotes must exist in the actual document.
    for item in result.evidence:
        if item.quote not in document_text:
            raise ValueError(
                "AI evidence quote was not found in source document."
            )

    if (
        result.classification == "potentially_privileged"
        and not result.evidence
    ):
        raise ValueError(
            "Potential privilege requires supporting evidence."
        )

    return result