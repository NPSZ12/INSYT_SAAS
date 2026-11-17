"""Safety tests for the existing JSON identification AI branch.

Only the real AST branch is executed, with a fake AI resolver.
No Azure calls, network requests, production writes, or CSV creation.
"""

import ast
import copy
from pathlib import Path

import pytest


SOURCE = Path(__file__).with_name("header_identification.py")


def load_real_json_ai_branch():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    route = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "identify_cyber2_header_set"
    )

    branches = [
        node for node in ast.walk(route)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "ai_suggestions"
        and any(
            isinstance(child, ast.Name)
            and child.id == "approved_headers"
            for child in ast.walk(node)
        )
    ]

    assert len(branches) == 1, (
        "Expected exactly one JSON AI integration branch"
    )

    module = ast.fix_missing_locations(
        ast.Module(
            body=[copy.deepcopy(branches[0])],
            type_ignores=[],
        )
    )

    return compile(module, "<real-json-ai-branch>", "exec")


REAL_AI_BRANCH = load_real_json_ai_branch()


def exercise_ai_branch(
    *,
    ai_requested=True,
    enabled=True,
    recommendation="First Name",
    confidence=0.91,
):
    column = {
        "source_header": "employee.first_name",
        "json_pointer": "/employee/first_name",
        "json_kind": "scalar",
        "sample_values": ["SYNTHETIC"],
        "recommended_protocol_header": "",
        "matched": False,
        "default_disposition": "delete",
        "approved": False,
        "ai_invoked": False,
    }

    identified = {
        "source_kind": "native_json",
        "source_sha256": "a" * 64,
        "source_csv_path": "",
        "mapping_approved": False,
        "csv_generated": False,
        "columns": [column],
    }

    preview = {
        "header_review": {
            "protocol_headers": [
                "First Name",
                "Social Security Number",
            ]
        }
    }

    original_preview = copy.deepcopy(preview)
    calls = {"gate": [], "resolver": []}

    def fake_should_invoke_ai(**kwargs):
        calls["gate"].append(kwargs)
        return enabled

    def fake_resolve_header_with_ai(**kwargs):
        calls["resolver"].append(kwargs)

        assert kwargs["source_header"] == "employee.first_name"
        assert kwargs["protocol_headers"] == [
            "First Name",
            "Social Security Number",
        ]

        return {
            "ai_invoked": True,
            "ai_status": "completed",
            "ai_recommendation": recommendation,
            "ai_confidence": confidence,
        }

    namespace = {
        "ai_suggestions": ai_requested,
        "identified": identified,
        "preview": preview,
        "should_invoke_ai": fake_should_invoke_ai,
        "resolve_header_with_ai": fake_resolve_header_with_ai,
    }

    exec(REAL_AI_BRANCH, namespace)

    result = namespace["identified"]
    output = result["columns"][0]

    # Every scenario must preserve reviewer and source safeguards.
    assert output["approved"] is False
    assert output["default_disposition"] == "delete"
    assert output["json_pointer"] == "/employee/first_name"
    assert output["source_header"] == "employee.first_name"

    assert result["source_kind"] == "native_json"
    assert result["source_sha256"] == "a" * 64
    assert result["source_csv_path"] == ""
    assert result["mapping_approved"] is False
    assert result["csv_generated"] is False

    assert preview == original_preview

    return result, output, calls


def test_unmatched_valid_ai_suggestion():
    result, column, calls = exercise_ai_branch(
        recommendation="First Name",
        confidence=0.91,
    )

    assert len(calls["gate"]) == 1
    assert calls["gate"][0]["matched"] is False
    assert len(calls["resolver"]) == 1

    assert column["matched"] is True
    assert column["recommended_protocol_header"] == "First Name"
    assert column["match_method"] == "ai_assisted"
    assert result["matched_column_count"] == 1
    assert result["ai_invoked_column_count"] == 1


def test_low_confidence_ai_suggestion_rejected():
    result, column, calls = exercise_ai_branch(
        recommendation="First Name",
        confidence=0.69,
    )

    assert len(calls["resolver"]) == 1
    assert column["matched"] is False
    assert not column["recommended_protocol_header"]
    assert result["matched_column_count"] == 0


def test_invalid_protocol_ai_suggestion_rejected():
    result, column, calls = exercise_ai_branch(
        recommendation="Unauthorized Header",
        confidence=0.99,
    )

    assert len(calls["resolver"]) == 1
    assert column["matched"] is False
    assert not column["recommended_protocol_header"]
    assert result["matched_column_count"] == 0


def test_disabled_ai_never_calls_resolver():
    result, column, calls = exercise_ai_branch(
        ai_requested=True,
        enabled=False,
    )

    assert len(calls["gate"]) == 1
    assert calls["resolver"] == []
    assert column["matched"] is False
    assert result["ai_invoked_column_count"] == 0


def test_ai_not_requested_never_calls_resolver():
    result, column, calls = exercise_ai_branch(
        ai_requested=False,
        enabled=True,
    )

    assert calls["gate"] == []
    assert calls["resolver"] == []
    assert column["matched"] is False
    assert result["mapping_approved"] is False
