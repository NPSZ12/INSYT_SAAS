"""Project-wide C2 read aggregation and authorization regressions."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.cyber2 import c2_transfer_store


API = Path("backend/app/api/cyber2/membership_api.py")


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


def environment(monkeypatch, *, deny=False, incomplete=False):
    data = {
        "HDR-A": {
            "headers": ["Doc ID", "Name"],
            "rows": [{"id": "MSET-A:WORK-1", "Doc ID": "D1", "Name": "Alex"}],
            "merge_set_id": "MSET-A",
            "working_record_count": 1,
            "original_source_record_count": 2,
        },
        "HDR-B": {
            "headers": ["Doc ID", "Name", "DOB"],
            "rows": [{"id": "MSET-B:WORK-1", "Doc ID": "D2", "Name": "Sam"}],
            "merge_set_id": "MSET-B",
            "working_record_count": 1,
            "original_source_record_count": 3,
        },
    }
    calls = []

    def require_access(*args):
        calls.append("authorization")
        if deny:
            raise FakeHTTPException(403, "Access denied")

    class FakeMergeStore:
        def list_completed(self):
            calls.append("list")
            if incomplete:
                return [
                    {"merge_set_id": str(i),
                     "header_set_id": "HDR-A",
                     "status": "completed"}
                    for i in range(1000)
                ]
            return [
                {"merge_set_id": "MSET-A", "header_set_id": "HDR-A",
                 "status": "completed"},
                {"merge_set_id": "MSET-B", "header_set_id": "HDR-B",
                 "status": "completed"},
            ]

    class FakeC2Store:
        def __init__(self, *args, **kwargs):
            calls.append("create_store")
            assert kwargs["project"] == "Payroll"

        def display(self, header_id):
            calls.append(("display", header_id))
            return data.get(header_id)

    monkeypatch.setattr(
        c2_transfer_store, "Cyber2C2TransferStore", FakeC2Store
    )

    tree = ast.parse(API.read_text(encoding="utf-8-sig"))
    functions = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "read_cyber2_project_c2_records"
    ]
    assert len(functions) == 1
    fn = functions[0]
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
        "PERMISSION_REVIEW": "review",
        "require_scoped_project_access": require_access,
        "require_permission": lambda *args: calls.append("review"),
        "require_admin": lambda *args: calls.append("admin"),
        "_cyber2_merge_store_for": lambda *args: FakeMergeStore(),
        "_processing_container_client": lambda: object(),
        "_project_base_path": lambda **kwargs: "capture/Demo/Payroll",
    }

    exec(compile(module, str(API), "exec"), namespace)

    return namespace["read_cyber2_project_c2_records"], calls, data


def call(fn):
    response = SimpleNamespace(headers={})
    result = fn("capture", response, "Demo", "Payroll", object())
    return result, response


def test_project_c2_combines_transferred_header_sets(monkeypatch):
    fn, calls, _ = environment(monkeypatch)
    result, response = call(fn)

    assert result["status"] == "ok"
    assert result["working_record_count"] == 2
    assert result["source_membership_count"] == 5
    assert result["headers"] == ["Doc ID", "Name", "DOB"]
    assert result["transferred_header_set_count"] == 2
    assert len({row["id"] for row in result["rows"]}) == 2
    assert calls[:3] == ["authorization", "review", "admin"]
    assert response.headers["Cache-Control"] == "no-store, private"


def test_denied_project_access_prevents_storage_reads(monkeypatch):
    fn, calls, _ = environment(monkeypatch, deny=True)

    with pytest.raises(FakeHTTPException) as exc:
        call(fn)

    assert exc.value.status_code == 403
    assert calls == ["authorization"]


def test_duplicate_c2_record_identity_is_rejected(monkeypatch):
    fn, _, data = environment(monkeypatch)
    data["HDR-B"]["rows"][0]["id"] = "MSET-A:WORK-1"

    with pytest.raises(FakeHTTPException) as exc:
        call(fn)

    assert exc.value.status_code == 409


def test_incomplete_inventory_is_rejected(monkeypatch):
    fn, calls, _ = environment(monkeypatch, incomplete=True)

    with pytest.raises(FakeHTTPException) as exc:
        call(fn)

    assert exc.value.status_code == 409
    assert "create_store" not in calls


def test_missing_c2_snapshots_do_not_add_records(monkeypatch):
    fn, _, data = environment(monkeypatch)
    data.clear()

    result, _ = call(fn)

    assert result["rows"] == []
    assert result["transferred_header_set_count"] == 0


def test_source_count_mismatch_is_rejected(monkeypatch):
    fn, _, data = environment(monkeypatch)
    data["HDR-A"]["working_record_count"] = 12

    with pytest.raises(FakeHTTPException) as exc:
        call(fn)

    assert exc.value.status_code == 409
