"""C2 read-route security and response contract tests.

Extract the route function for unit testing without importing unrelated
Azure services or requiring a live FastAPI application.
"""

import ast
from pathlib import Path

import pytest

from app.services.cyber2 import c2_transfer_store


SOURCE = Path(
    "backend/app/api/cyber2/membership_api.py"
)


def build_route(monkeypatch, *, result=None, deny=False):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

    matches = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "read_cyber2_c2_records"
    ]

    assert len(matches) == 1

    fn = matches[0]
    fn.decorator_list = []

    calls = []

    def access(*args):
        calls.append("scope")
        if deny:
            raise PermissionError("Access denied")

    def permission(*args):
        calls.append("permission")

    def admin(*args):
        calls.append("admin")

    class FakeStore:
        def __init__(self, *args, **kwargs):
            calls.append("store")
            assert kwargs["workspace"] == "capture"
            assert kwargs["client"] == "Demo"
            assert kwargs["project"] == "Payroll"

        def display(self, header_set_id):
            calls.append("display")
            assert header_set_id == "HDRSET-TEST"
            return result

    monkeypatch.setattr(
        c2_transfer_store,
        "Cyber2C2TransferStore",
        FakeStore,
    )

    namespace = {
        "Workspace": str,
        "Response": object,
        "Query": lambda **kwargs: None,
        "Depends": lambda dependency: None,
        "get_current_user": lambda: None,
        "require_scoped_project_access": access,
        "require_permission": permission,
        "require_admin": admin,
        "PERMISSION_REVIEW": "review",
        "_processing_container_client": lambda: object(),
        "_project_base_path": lambda **kwargs: "capture/Demo/Payroll",
        "HTTPException": RuntimeError,
    }

    executable = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(executable)

    exec(compile(executable, str(SOURCE), "exec"), namespace)

    return namespace["read_cyber2_c2_records"], calls


class FakeResponse:
    def __init__(self):
        self.headers = {}


def test_authorized_c2_display(monkeypatch):
    expected = {
        "headers": ["Doc ID", "First Name"],
        "rows": [{"Doc ID": "DOC1", "First Name": "Alex"}],
        "source": "cyber2_c2_transfer",
        "working_record_count": 1,
        "original_source_record_count": 2,
    }

    route, calls = build_route(
        monkeypatch, result=expected
    )
    response = FakeResponse()

    output = route(
        "capture",
        response,
        "Demo",
        "Payroll",
        "HDRSET-TEST",
        object(),
    )

    assert output["status"] == "ok"
    assert output["rows"] == expected["rows"]
    assert calls == [
        "scope", "permission", "admin", "store", "display"
    ]
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["Pragma"] == "no-cache"


def test_denied_request_never_reads_storage(monkeypatch):
    route, calls = build_route(monkeypatch, deny=True)

    with pytest.raises(PermissionError):
        route(
            "capture",
            FakeResponse(),
            "Demo",
            "Payroll",
            "HDRSET-TEST",
            object(),
        )

    assert calls == ["scope"]


def test_absent_c2_snapshot_is_empty(monkeypatch):
    route, calls = build_route(monkeypatch, result=None)

    output = route(
        "capture",
        FakeResponse(),
        "Demo",
        "Payroll",
        "HDRSET-TEST",
        object(),
    )

    assert output["rows"] == []
    assert output["working_record_count"] == 0
    assert "display" in calls
