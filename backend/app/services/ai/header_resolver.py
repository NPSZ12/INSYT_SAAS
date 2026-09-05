from __future__ import annotations

import json
import os
from typing import Any
from openai import OpenAI


def ai_header_resolution_enabled() -> bool:
    return (
        os.getenv(
            "INSYT_AI_HEADER_RESOLUTION_ENABLED",
            "false",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def should_invoke_ai(
    *,
    mapping_confidence: float,
    matched: bool,
) -> bool:

    if not ai_header_resolution_enabled():
        return False

    if not matched:
        return True

    return float(
        mapping_confidence
        or 0.0
    ) < 0.90


def resolve_header_with_ai(
    *,
    source_header: str,
    sample_values: list[str],
    semantic_type: str,
    deterministic_recommendation: str,
    deterministic_confidence: float,
    protocol_headers: list[str],
) -> dict[str, Any]:

    if not ai_header_resolution_enabled():
        return {
            "ai_invoked": False,
            "ai_status": "disabled",
            "ai_recommendation": "",
            "ai_confidence": None,
            "ai_reason": "",
        }

    endpoint = (
        os.getenv(
            "AZURE_OPENAI_ENDPOINT",
            "",
        )
        .strip()
        .rstrip("/")
    )

    api_key = (
        os.getenv(
            "AZURE_OPENAI_API_KEY",
            "",
        )
        .strip()
    )

    deployment = (
        os.getenv(
            "AZURE_OPENAI_DEPLOYMENT",
            "",
        )
        .strip()
    )

    if (
        not endpoint
        or not api_key
        or not deployment
    ):
        return {
            "ai_invoked": False,
            "ai_status": "provider_not_configured",
            "ai_recommendation": "",
            "ai_confidence": None,
            "ai_reason": (
                "Azure OpenAI endpoint, API key, "
                "or deployment is not configured."
            ),
        }

    prompt_payload = (
        build_ai_header_prompt_payload(
            source_header=source_header,
            sample_values=sample_values,
            semantic_type=semantic_type,
            deterministic_recommendation=(
                deterministic_recommendation
            ),
            deterministic_confidence=(
                deterministic_confidence
            ),
            protocol_headers=(
                protocol_headers
            ),
        )
    )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=(
                f"{endpoint}/openai/v1/"
            ),
        )

        response = (
            client.responses.create(
                model=deployment,
                instructions=(
                    "You are the INSYT structured-data "
                    "header resolver. Return JSON only. "
                    "Choose only from the supplied Project "
                    "Protocol headers or return NO_MATCH. "
                    "Do not invent headers."
                ),
                input=prompt_payload,
            )
        )

        raw_text = str(
            response.output_text
            or ""
        ).strip()

        clean_text = (
            raw_text
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        result = json.loads(
            clean_text
        )

        recommendation = str(
            result.get(
                "recommendation"
            )
            or ""
        ).strip()

        confidence_raw = (
            result.get(
                "confidence"
            )
        )

        reason = str(
            result.get(
                "reason"
            )
            or ""
        ).strip()

        if (
            recommendation.upper()
            == "NO_MATCH"
        ):
            recommendation = ""

        #
        # Hard safety boundary:
        # AI may only choose an actual
        # Project Protocol header.
        #
        protocol_lookup = {
            str(header).strip().casefold():
                str(header).strip()
            for header in protocol_headers
            if str(header).strip()
        }

        if recommendation:
            canonical = (
                protocol_lookup.get(
                    recommendation.casefold()
                )
            )

            if not canonical:
                return {
                    "ai_invoked": True,
                    "ai_status": (
                        "invalid_protocol_response"
                    ),
                    "ai_recommendation": "",
                    "ai_confidence": None,
                    "ai_reason": (
                        "AI returned a header that "
                        "is not in the Project Protocol."
                    ),
                }

            recommendation = (
                canonical
            )

        try:
            confidence = (
                float(
                    confidence_raw
                )
                if confidence_raw
                is not None
                else None
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = None

        if confidence is not None:
            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            )

        return {
            "ai_invoked": True,
            "ai_status": "completed",
            "ai_recommendation": (
                recommendation
            ),
            "ai_confidence": (
                confidence
            ),
            "ai_reason": (
                reason
            ),
        }

    except Exception as exc:
        return {
            "ai_invoked": True,
            "ai_status": "error",
            "ai_recommendation": "",
            "ai_confidence": None,
            "ai_reason": str(
                exc
            ),
        }


def build_ai_header_prompt_payload(
    *,
    source_header: str,
    sample_values: list[str],
    semantic_type: str,
    deterministic_recommendation: str,
    deterministic_confidence: float,
    protocol_headers: list[str],
) -> str:

    payload = {
        "task": (
            "Choose the single best Project Protocol "
            "header for this source column, or return "
            "NO_MATCH."
        ),

        "source_header": (
            source_header
        ),

        "sample_values": (
            sample_values[:8]
        ),

        "semantic_type": (
            semantic_type
        ),

        "deterministic_recommendation": (
            deterministic_recommendation
        ),

        "deterministic_confidence": (
            deterministic_confidence
        ),

        "allowed_protocol_headers": (
            protocol_headers
        ),

        "rules": [
            (
                "Return only a value from "
                "allowed_protocol_headers "
                "or NO_MATCH."
            ),
            (
                "Do not invent a new header."
            ),
            (
                "Use both source header text "
                "and sample values."
            ),
            (
                "Return JSON with exactly these fields: "
                "recommendation, confidence, reason. "
                "confidence must be between 0 and 1."
            ),
        ],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
    )