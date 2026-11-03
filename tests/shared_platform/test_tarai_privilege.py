import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ai.tarai_privilege import validate_privilege_suggestion


DOCUMENT = (
    "Counsel, please provide confidential legal advice "
    "regarding the proposed agreement."
)


def test_valid_privilege_suggestion():
    result = validate_privilege_suggestion(
        document_text=DOCUMENT,
        suggestion={
            "classification": "potentially_privileged",
            "rationale": "The communication requests legal advice.",
            "evidence": [
                {
                    "quote": "please provide confidential legal advice",
                    "explanation": "Direct request for legal advice.",
                }
            ],
        },
    )

    assert result.classification == "potentially_privileged"
    assert result.reviewer_status == "pending"


def test_reject_invented_evidence():
    with pytest.raises(ValueError):
        validate_privilege_suggestion(
            document_text=DOCUMENT,
            suggestion={
                "classification": "potentially_privileged",
                "rationale": "Possible attorney-client communication.",
                "evidence": [
                    {
                        "quote": "This document was prepared by outside counsel.",
                        "explanation": "Purported attorney involvement.",
                    }
                ],
            },
        )


def test_reject_unknown_classification():
    with pytest.raises(ValidationError):
        validate_privilege_suggestion(
            document_text=DOCUMENT,
            suggestion={
                "classification": "definitely_privileged",
                "rationale": "Unsupported final classification.",
                "evidence": [],
            },
        )


def test_reject_privilege_without_evidence():
    with pytest.raises(ValueError):
        validate_privilege_suggestion(
            document_text=DOCUMENT,
            suggestion={
                "classification": "potentially_privileged",
                "rationale": "No supporting citation provided.",
                "evidence": [],
            },
        )