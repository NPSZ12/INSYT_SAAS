import pytest
from fastapi import HTTPException

from test_cyber2_membership_api import harness
from test_cyber2_iterative_preview_api import configure


def request(api, user):
    result = api.preview_cyber2_iterative_spreadsheet(
        "capture",
        api.IterativePreviewBody(
            client="ACME",
            project="CaseA",
            parent_merge_set_id="MSET-" + "A" * 32,
            merge_index=["First Name", "DOB"],
        ),
        user,
    )
    return result


def test_authorized_spreadsheet_has_complete_parent_rows(
    harness, monkeypatch
):
    import json

    api, user, registry = harness
    configure(api, monkeypatch)

    response = request(api, user)
    payload = json.loads(response.body)

    assert payload["status"] == "iterative_spreadsheet_preview"
    assert payload["preview_row_count"] == 2
    assert payload["preview_rows_complete"] is True
    assert payload["execution_enabled"] is False

    rows = payload["preview_rows"]
    assert len(rows) == 2
    assert len({row["working_record_id"] for row in rows}) == 2
    assert all(row["classification"] == "qc_conflict" for row in rows)
    assert all("SSN" in row["field_provenance"] for row in rows)
    assert all("source_ucids" in row for row in rows)
    assert registry["writes"] == 0
    assert response.headers["cache-control"] == "no-store, private"


def test_other_project_parent_rejected(harness, monkeypatch):
    api, user, _ = harness
    configure(
        api, monkeypatch,
        scope_override={"project": "Other"},
    )

    with pytest.raises(HTTPException) as error:
        request(api, user)

    assert error.value.status_code == 409


def test_permission_denial_prevents_data_retrieval(
    harness, monkeypatch
):
    api, user, _ = harness
    touched = []

    monkeypatch.setattr(
        api,
        "require_scoped_project_access",
        lambda *args: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="Denied")
        ),
    )

    monkeypatch.setattr(
        api,
        "_cyber2_merge_store_for",
        lambda *args: touched.append(True),
    )

    with pytest.raises(HTTPException) as error:
        request(api, user)

    assert error.value.status_code == 403
    assert not touched
