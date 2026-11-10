"""C2 origin authorization policy regressions."""

from copy import deepcopy

import pytest

from app.services.cyber2.c2_origin_authorization import (
    C2OriginAuthorizationError,
    require_c2_origin_authorization,
)


def fixture():
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDR-1",
    }

    document = {
        "doc_id": "DOC-1",
        "source_csv_path": "source/payroll.csv",
    }

    merge = {
        **scope,
        "status": "completed",
        "merge_set_id": "MSET-" + "A" * 32,
        "integrity_sha256": "b" * 64,
    }

    mapping = {
        **scope,
        "status": "approved",
        "documents": [deepcopy(document)],
    }

    auth = {
        **scope,
        "merge_set_id": merge["merge_set_id"],
        "merge_integrity_sha256": merge["integrity_sha256"],
        "decision": "approved_non_ai",
        "authorized_by": "authorized-reviewer",
        "authorized_at": "2026-11-10T16:00:00Z",
        "documents": [{
            **document,
            "capture_method": "non_ai_structured_source",
        }],
    }

    return merge, mapping, auth


def check(merge, mapping, auth):
    return require_c2_origin_authorization(
        merge, mapping, auth
    )


def test_authorized_structured_source():
    merge, mapping, auth = fixture()
    before = deepcopy((merge, mapping, auth))
    result = check(merge, mapping, auth)
    assert result["origin_authorized"] is True
    assert result["authorized_document_count"] == 1
    assert (merge, mapping, auth) == before


@pytest.mark.parametrize(
    "method",
    ["ai_extraction", "manual_capture", "unknown", ""],
)
def test_rejects_non_structured_origin(method):
    merge, mapping, auth = fixture()
    auth["documents"][0]["capture_method"] = method
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_missing_origin():
    merge, mapping, auth = fixture()
    del auth["documents"][0]["capture_method"]
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_different_document():
    merge, mapping, auth = fixture()
    auth["documents"][0]["doc_id"] = "DOC-OTHER"
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_different_source_csv():
    merge, mapping, auth = fixture()
    auth["documents"][0]["source_csv_path"] = "other.csv"
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_changed_merge_digest():
    merge, mapping, auth = fixture()
    merge["integrity_sha256"] = "c" * 64
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_wrong_project():
    merge, mapping, auth = fixture()
    auth["project"] = "Other"
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_unapproved_decision():
    merge, mapping, auth = fixture()
    auth["decision"] = "pending"
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)


def test_rejects_missing_authorizer():
    merge, mapping, auth = fixture()
    auth["authorized_by"] = ""
    with pytest.raises(C2OriginAuthorizationError):
        check(merge, mapping, auth)
