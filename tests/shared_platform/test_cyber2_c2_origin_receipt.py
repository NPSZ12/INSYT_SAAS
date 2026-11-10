"""C2 origin approval receipt and API security regressions."""

import ast
import json
from pathlib import Path

import pytest

from app.services.cyber2.c2_origin_receipt import (
    C2OriginReceiptError,
    save_c2_origin_approval,
)


class BlobError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class Blob:
    def __init__(self, data, name):
        self.data = data
        self.name = name

    def upload_blob(self, payload, *, overwrite, content_settings):
        assert overwrite is False
        if self.name in self.data:
            raise BlobError(409)
        self.data[self.name] = payload

    def download_blob(self):
        if self.name not in self.data:
            raise BlobError(404)

        class Reader:
            def __init__(self, value):
                self.value = value

            def readall(self):
                return self.value

        return Reader(self.data[self.name])


class Container:
    def __init__(self):
        self.data = {}

    def get_blob_client(self, name):
        return Blob(self.data, name)


def fixture():
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDRSET-TEST",
    }
    docs = [
        {
            "doc_id": "DOC-1",
            "source_csv_path": "source/payroll1.csv",
        },
        {
            "doc_id": "DOC-2",
            "source_csv_path": "source/payroll2.csv",
        },
    ]
    merge = {
        **scope,
        "status": "completed",
        "merge_set_id": "MSET-" + "A" * 32,
        "integrity_sha256": "b" * 64,
    }
    mapping = {
        **scope,
        "status": "approved",
        "documents": docs,
    }
    return Container(), merge, mapping


def save(container, merge, mapping, **overrides):
    options = {
        "container": container,
        "project_base_path": "capture/Demo/Payroll",
        "merge_set": merge,
        "approved_mapping": mapping,
        "reviewed_doc_ids": ["DOC-1", "DOC-2"],
        "reviewer": "admin",
        "attested_non_ai": True,
        "content_settings_factory": lambda: object(),
    }
    options.update(overrides)
    return save_c2_origin_approval(**options)


def test_creates_immutable_server_derived_receipt():
    container, merge, mapping = fixture()
    result = save(container, merge, mapping)

    assert result["status"] == "approved"
    assert result["reviewed_document_count"] == 2
    assert len(container.data) == 1

    stored = json.loads(next(iter(container.data.values())))
    assert stored["documents"][0]["source_csv_path"] == (
        "source/payroll1.csv"
    )
    assert stored["authorized_by"] == "admin"
    assert stored["decision"] == "approved_non_ai"
    assert stored["approval_basis"] == (
        "administrator_source_review"
    )
    assert len(stored["integrity_sha256"]) == 64


def test_exact_approval_replay_is_idempotent():
    container, merge, mapping = fixture()
    save(container, merge, mapping)
    result = save(container, merge, mapping)

    assert result["status"] == "already_approved"
    assert len(container.data) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"attested_non_ai": False},
        {"reviewer": ""},
        {"reviewed_doc_ids": ["DOC-1"]},
        {"reviewed_doc_ids": ["DOC-1", "DOC-1"]},
        {"reviewed_doc_ids": ["DOC-1", "DOC-OTHER"]},
    ],
)
def test_untrusted_review_is_rejected(override):
    container, merge, mapping = fixture()

    with pytest.raises(C2OriginReceiptError):
        save(container, merge, mapping, **override)

    assert container.data == {}


def test_different_review_actor_cannot_replace_receipt():
    container, merge, mapping = fixture()
    save(container, merge, mapping)

    with pytest.raises(C2OriginReceiptError):
        save(container, merge, mapping, reviewer="other-admin")


def test_project_mismatch_rejected():
    container, merge, mapping = fixture()
    mapping["project"] = "Other"

    with pytest.raises(Exception):
        save(container, merge, mapping)

    assert container.data == {}


def test_api_requires_auth_before_server_approval():
    path = Path("backend/app/api/cyber2/membership_api.py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))

    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "approve_cyber2_c2_origin"
    ]
    assert len(matches) == 1

    source = ast.unparse(matches[0])

    for required in (
        "require_scoped_project_access",
        "require_permission",
        "require_admin",
        "_cyber2_execution_actor",
        "inspect_cyber2_c2_transfer_readiness",
        "save_c2_origin_approval",
    ):
        assert required in source

    assert source.index("require_admin") < (
        source.index("save_c2_origin_approval(")
    )
    assert source.index(
        "inspect_cyber2_c2_transfer_readiness("
    ) < source.index("save_c2_origin_approval(")


def test_api_does_not_accept_origin_receipt_from_client():
    path = Path("backend/app/api/cyber2/membership_api.py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))

    models = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "C2OriginApprovalBody"
    ]
    assert len(models) == 1

    fields = {
        item.target.id
        for item in models[0].body
        if isinstance(item, ast.AnnAssign)
        and isinstance(item.target, ast.Name)
    }

    assert fields == {
        "client", "project", "merge_set_id",
        "reviewed_doc_ids", "attested_non_ai",
    }
    assert "authorized_by" not in fields
    assert "capture_source" not in fields
