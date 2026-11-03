"""Regression tests for strict TARai document provenance."""

import ast
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.storage_paths import build_project_path


SOURCE = ROOT / "backend/app/api/tarai.py"

tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

function_node = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "require_exact_document_identity"
)

module = ast.Module(
    body=[function_node],
    type_ignores=[],
)

namespace = {
    "HTTPException": HTTPException,
    "build_project_path": build_project_path,
}

exec(
    compile(
        ast.fix_missing_locations(module),
        str(SOURCE),
        "exec",
    ),
    namespace,
)

validate = namespace["require_exact_document_identity"]


def document(**changes):
    result = {
        "workspace": "discovery",
        "project_id": "Project_Ingestion",
        "doc_id": "INSYT000000001",
        "native_storage_source": "live_source",
        "native_blob": (
            "INSYT_DEMO/discovery/Project_Ingestion/"
            "source/native/INSYT000000001.pdf"
        ),
        "text_blob": (
            "INSYT_DEMO/discovery/Project_Ingestion/"
            "source/text/INSYT000000001.txt"
        ),
    }
    result.update(changes)
    return result


def check(value):
    validate(
        value,
        "INSYT_DEMO",
        "Project_Ingestion",
        "INSYT000000001",
    )


def test_valid_document():
    check(document())


@pytest.mark.parametrize(
    "changes",
    [
        {"workspace": "capture"},
        {"project_id": "Other_Project"},
        {"doc_id": "INSYT000000002"},
        {"native_storage_source": "review_storage"},
        {
            "native_blob": (
                "OTHER_CLIENT/discovery/Project_Ingestion/"
                "source/native/INSYT000000001.pdf"
            ),
        },
        {
            "native_blob": (
                "INSYT_DEMO/discovery/Other_Project/"
                "source/native/INSYT000000001.pdf"
            ),
        },
        {
            "text_blob": (
                "OTHER_CLIENT/discovery/Project_Ingestion/"
                "source/text/INSYT000000001.txt"
            ),
        },
        {
            "text_blob": (
                "INSYT_DEMO/discovery/Other_Project/"
                "source/text/INSYT000000001.txt"
            ),
        },
        {"native_blob": ""},
        {"text_blob": ""},
    ],
)
def test_reject_invalid_identity(changes):
    with pytest.raises(HTTPException) as exc:
        check(document(**changes))

    assert exc.value.status_code == 409


def test_project_storage_key_normalization():
    assert build_project_path(
        "discovery",
        "INSYT_DEMO",
        "Project Ingestion",
    ) == "INSYT_DEMO/discovery/Project_Ingestion"