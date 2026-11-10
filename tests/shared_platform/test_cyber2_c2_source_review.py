"""Executable C2 source-review authorization and inventory tests."""

import ast
import sys
import types
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


API = Path("backend/app/api/cyber2/membership_api.py")
MERGE = "MSET-" + "A" * 32


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


def environment(monkeypatch, *, deny=False):
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDRSET-TEST",
    }
    mapping = {
        **scope,
        "status": "approved",
        "documents": [
            {
                "doc_id": "DOC-1",
                "source_csv_path": "private/one.csv",
                "original_filename": "Payroll.xlsx",
                "sheet_name": "January",
            },
            {
                "doc_id": "DOC-2",
                "source_csv_path": "private/two.csv",
                "original_filename": "Payroll.xlsx",
                "sheet_name": "February",
            },
        ],
    }
    merge = {
        **scope,
        "merge_set_id": MERGE,
        "status": "completed",
    }
    state = {
        "mapping": mapping,
        "merge": merge,
        "ready": True,
        "calls": [],
    }

    def access(*args):
        state["calls"].append("scope")
        if deny:
            raise FakeHTTPException(403, "Access denied")

    def readiness(**kwargs):
        state["calls"].append("readiness")
        if not state["ready"]:
            raise FakeHTTPException(409, "Not ready")
        return {
            **scope,
            "status": "source_verified_origin_pending",
            "merge_set_id": MERGE,
            "working_record_count": 1,
            "original_source_record_count": 2,
            "source_conservation_verified": True,
            "origin_authorized": False,
            "transfer_authorized": False,
        }

    class Store:
        def load(self, merge_id):
            state["calls"].append("merge_load")
            assert merge_id == MERGE
            return deepcopy(state["merge"])

    schema = types.ModuleType(
        "app.api.cyber2.schema_mapping"
    )
    schema._approved_mapping_path = (
        lambda **kwargs: "mapping.json"
    )
    schema._load_required_json = (
        lambda *args, **kwargs: deepcopy(state["mapping"])
    )
    monkeypatch.setitem(
        sys.modules, "app.api.cyber2.schema_mapping", schema
    )

    tree = ast.parse(API.read_text(encoding="utf-8-sig"))
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "read_cyber2_c2_source_review"
    ]
    assert len(matches) == 1

    fn = matches[0]
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        "Workspace": str,
        "Response": object,
        "Query": lambda **kwargs: None,
        "Depends": lambda fn: None,
        "get_current_user": lambda: None,
        "HTTPException": FakeHTTPException,
        "require_scoped_project_access": access,
        "require_permission":
            lambda *args: state["calls"].append("review"),
        "require_admin":
            lambda *args: state["calls"].append("admin"),
        "PERMISSION_REVIEW": "review",
        "inspect_cyber2_c2_transfer_readiness": readiness,
        "_cyber2_merge_store_for": lambda *args: Store(),
    }

    exec(compile(module, str(API), "exec"), namespace)

    state["route"] = namespace[
        "read_cyber2_c2_source_review"
    ]
    return state


def call(state):
    response = SimpleNamespace(headers={})
    result = state["route"](
        "capture", response, "Demo", "Payroll", MERGE, object()
    )
    return result, response


def test_authorized_inventory_contains_exact_document_ids(monkeypatch):
    state = environment(monkeypatch)
    result, response = call(state)

    assert result["status"] == "review_required"
    assert result["document_count"] == 2
    assert result["working_record_count"] == 1
    assert result["original_source_record_count"] == 2
    assert [doc["doc_id"] for doc in result["documents"]] == [
        "DOC-1", "DOC-2"
    ]
    assert result["origin_authorized"] is False
    assert result["transfer_authorized"] is False
    assert "source_csv_path" not in repr(result)
    assert "private/one.csv" not in repr(result)
    assert response.headers["Cache-Control"] == "no-store, private"
    assert state["calls"][:4] == [
        "scope", "review", "admin", "readiness"
    ]


def test_denied_access_never_calls_readiness(monkeypatch):
    state = environment(monkeypatch, deny=True)

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 403
    assert state["calls"] == ["scope"]


def test_failed_readiness_prevents_review(monkeypatch):
    state = environment(monkeypatch)
    state["ready"] = False

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 409
    assert "merge_load" not in state["calls"]


def test_duplicate_source_document_rejected(monkeypatch):
    state = environment(monkeypatch)
    state["mapping"]["documents"][1]["doc_id"] = "DOC-1"

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 409


def test_missing_source_path_rejected(monkeypatch):
    state = environment(monkeypatch)
    state["mapping"]["documents"][0]["source_csv_path"] = ""

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 409


def test_cross_project_mapping_rejected(monkeypatch):
    state = environment(monkeypatch)
    state["mapping"]["project"] = "Other"

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 409


def test_wrong_merge_header_set_rejected(monkeypatch):
    state = environment(monkeypatch)
    state["merge"]["header_set_id"] = "HDR-OTHER"

    with pytest.raises(FakeHTTPException) as exc:
        call(state)

    assert exc.value.status_code == 409
