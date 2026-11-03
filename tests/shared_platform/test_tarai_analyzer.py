import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ai.tarai_analyzer import (
    analyze_privilege,
    TARaiDisabledError,
    TARaiResponseError,
)


DOCUMENT = (
    "Counsel, please provide confidential legal advice "
    "regarding the proposed agreement."
)


def fake_factory(payload):
    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["store"] is False
            return SimpleNamespace(
                output_text=json.dumps(payload)
            )

    return lambda **kwargs: SimpleNamespace(
        responses=FakeResponses()
    )


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INSYT_TARAI_AI_ENABLED", raising=False)

    with pytest.raises(TARaiDisabledError):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Confidential legal advice.",
        )


def test_reject_capture(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")

    with pytest.raises(ValueError):
        analyze_privilege(
            workspace="capture",
            document_text=DOCUMENT,
            privilege_criteria="Legal advice.",
        )


def test_valid_mocked_ai_response(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mock-deployment")

    payload = {
        "classification": "potentially_privileged",
        "rationale": "Requests confidential legal advice.",
        "evidence": [{
            "quote": "please provide confidential legal advice",
            "explanation": "Direct request for legal advice.",
        }],
        "reviewer_status": "pending",
    }

    result = analyze_privilege(
        workspace="discovery",
        document_text=DOCUMENT,
        privilege_criteria="Confidential requests for legal advice.",
        client_factory=fake_factory(payload),
    )

    assert result.classification == "potentially_privileged"
    assert result.reviewer_status == "pending"


def test_reject_fabricated_quote(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mock-deployment")

    payload = {
        "classification": "potentially_privileged",
        "rationale": "Possible legal advice.",
        "evidence": [{
            "quote": "Fabricated document language.",
            "explanation": "Unsupported evidence.",
        }],
        "reviewer_status": "pending",
    }

    with pytest.raises(TARaiResponseError):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Requests for legal advice.",
            client_factory=fake_factory(payload),
        )

def test_invalid_classification_response(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mock-model")

    payload = {
        "classification": "definitely_privileged",
        "rationale": "Unsupported legal determination.",
        "evidence": [],
        "reviewer_status": "pending",
    }

    with pytest.raises(TARaiResponseError):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Legal advice.",
            client_factory=fake_factory(payload),
        )


def test_empty_model_response(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mock-model")

    factory = lambda **kwargs: SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(output_text="")
        )
    )

    with pytest.raises(TARaiResponseError):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Legal advice.",
            client_factory=factory,
        )


def test_missing_ai_configuration(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)

    from app.services.ai.tarai_analyzer import TARaiConfigurationError

    with pytest.raises(TARaiConfigurationError):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Legal advice.",
        )


def test_provider_failure_propagates(monkeypatch):
    monkeypatch.setenv("INSYT_TARAI_AI_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mock-model")

    def failed_factory(**kwargs):
        class FailedResponses:
            def create(self, **kwargs):
                raise RuntimeError("Synthetic provider unavailable")

        return SimpleNamespace(responses=FailedResponses())

    with pytest.raises(RuntimeError, match="Synthetic provider unavailable"):
        analyze_privilege(
            workspace="discovery",
            document_text=DOCUMENT,
            privilege_criteria="Legal advice.",
            client_factory=failed_factory,
        )