"""Execute C2 transfer using real validation services and fake Azure blobs."""

import ast
import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.cyber2 import c2_transfer_store
from app.services.cyber2.c2_origin_receipt import (
    save_c2_origin_approval,
)


API = Path("backend/app/api/cyber2/membership_api.py")
MERGE_A = "MSET-" + "A" * 32
MERGE_B = "MSET-" + "B" * 32


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BlobError(Exception):
    def __init__(self, code):
        self.status_code = code


class Blob:
    def __init__(self, data, path):
        self.data = data
        self.path = path

    def upload_blob(self, payload, *, overwrite, content_settings):
        assert overwrite is False
        if self.path in self.data:
            raise BlobError(409)
        self.data[self.path] = payload

    def download_blob(self):
        if self.path not in self.data:
            raise BlobError(404)

        payload = self.data[self.path]
        return SimpleNamespace(readall=lambda: payload)


class Container:
    def __init__(self):
        self.data = {}

    def get_blob_client(self, path):
        return Blob(self.data, path)


def sample():
    scope = {
        "workspace": "capture",
        "client": "Demo",
        "project": "Payroll",
        "header_set_id": "HDRSET-TEST",
    }

    headers = ["First Name", "Gross Pay"]

    records = [
        {
            "ucid": "U1",
            "doc_id": "DOC1",
            "metadata": {
                "First Name": "Alex",
                "Gross Pay": "1450.00",
            },
            "provenance": {
                "capture_source": "cyber2_mapped_csv",
                "header_set_id": "HDRSET-TEST",
                "source_row_number": 2,
                "column_lineage": [],
            },
        },
        {
            "ucid": "U2",
            "doc_id": "DOC2",
            "metadata": {
                "First Name": "Alex",
                "Gross Pay": "1512.42",
            },
            "provenance": {
                "capture_source": "cyber2_mapped_csv",
                "header_set_id": "HDRSET-TEST",
                "source_row_number": 2,
                "column_lineage": [],
            },
        },
    ]

    evidence = {
        field: [
            {
                "ucid": record["ucid"],
                "doc_id": record["doc_id"],
                "source_row_number": 2,
                "output_header": field,
                "original_value": record["metadata"][field],
            }
            for record in records
        ]
        for field in headers
    }

    merge = {
        **scope,
        "status": "completed",
        "merge_set_id": MERGE_A,
        "integrity_sha256": "a" * 64,
        "approved_headers": headers,
        "raw_record_count": 2,
        "working_record_count": 1,
        "working_records": [{
            "working_record_id": "WORK-000001",
            "classification": "exact_merged",
            "source_ucids": ["U1", "U2"],
            "source_doc_ids": ["DOC1", "DOC2"],
            "cells": {
                "First Name": "Alex",
                "Gross Pay": "1450.00; 1512.42",
            },
            "field_provenance": evidence,
        }],
    }

    mapping = {
        **scope,
        "status": "approved",
        "protocol_headers": headers,
        "documents": [
            {
                "doc_id": "DOC1",
                "source_csv_path": "source/one.csv",
            },
            {
                "doc_id": "DOC2",
                "source_csv_path": "source/two.csv",
            },
        ],
    }

    return merge, mapping, records


def environment(monkeypatch):
    container = Container()
    merge, mapping, records = sample()

    state = {
        "container": container,
        "merges": {MERGE_A: merge},
        "mapping": mapping,
        "records": records,
        "ready": 0,
        "deny": False,
    }

    def check_access(*args):
        if state["deny"]:
            raise FakeHTTPException(403, "Project access denied")

    def ready(**kwargs):
        state["ready"] += 1
        if state.get("block_ready"):
            raise FakeHTTPException(409, "Not ready")
        return {"transfer_authorized": False}

    class MergeStore:
        def load(self, merge_id):
            if merge_id not in state["merges"]:
                raise FakeHTTPException(404, "Missing Merge Set")
            return deepcopy(state["merges"][merge_id])

    class BoundC2Store(c2_transfer_store.Cyber2C2TransferStore):
        def __init__(self, *args, **kwargs):
            super().__init__(
                *args,
                content_settings_factory=lambda: object(),
                **kwargs,
            )

    monkeypatch.setattr(
        c2_transfer_store,
        "Cyber2C2TransferStore",
        BoundC2Store,
    )

    schema = types.ModuleType(
        "app.api.cyber2.schema_mapping"
    )
    schema._approved_mapping_path = lambda **kwargs: "mapping.json"
    schema._load_required_json = (
        lambda *args, **kwargs: deepcopy(state["mapping"])
    )

    monkeypatch.setitem(
        sys.modules,
        "app.api.cyber2.schema_mapping",
        schema,
    )

    tree = ast.parse(API.read_text(encoding="utf-8-sig"))

    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "transfer_cyber2_merge_set_to_c2"
    ]

    assert len(functions) == 1
    fn = functions[0]
    fn.decorator_list = []

    namespace = {
        "Workspace": str,
        "C2TransferBody": object,
        "Response": object,
        "Depends": lambda value: None,
        "get_current_user": lambda: None,
        "HTTPException": FakeHTTPException,
        "require_scoped_project_access": check_access,
        "require_permission": lambda *args: None,
        "require_admin": lambda *args: None,
        "PERMISSION_REVIEW": "review",
        "_cyber2_execution_actor": lambda user: "admin",
        "_cyber2_merge_store_for":
            lambda *args: MergeStore(),
        "_project_base_path":
            lambda **kwargs: "capture/Demo/Payroll",
        "_processing_container_client": lambda: container,
        "inspect_cyber2_c2_transfer_readiness": ready,
        "_load_cyber2_merge_processing_set":
            lambda **kwargs: {
                "records": deepcopy(state["records"])
            },
    }

    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)

    exec(compile(module, str(API), "exec"), namespace)

    state["route"] = namespace[
        "transfer_cyber2_merge_set_to_c2"
    ]
    return state


def call(state, merge_id=MERGE_A):
    body = SimpleNamespace(
        client="Demo",
        project="Payroll",
        merge_set_id=merge_id,
    )
    response = SimpleNamespace(headers={})
    return state["route"](
        "capture", body, response, object()
    )


def approve(state, merge_id=MERGE_A):
    return save_c2_origin_approval(
        container=state["container"],
        project_base_path="capture/Demo/Payroll",
        merge_set=state["merges"][merge_id],
        approved_mapping=state["mapping"],
        reviewed_doc_ids=["DOC1", "DOC2"],
        reviewer="admin",
        attested_non_ai=True,
        content_settings_factory=lambda: object(),
    )


def snapshots(state):
    return {
        key: value
        for key, value in state["container"].data.items()
        if "/cyber2/c2/header_sets/" in key
    }


def test_successful_transfer_preserves_records(monkeypatch):
    state = environment(monkeypatch)
    approve(state)

    result = call(state)

    assert result["status"] == "transferred"
    assert result["working_record_count"] == 1
    assert result["original_source_record_count"] == 2
    assert state["ready"] == 2
    assert len(snapshots(state)) == 1

    saved = json.loads(next(iter(snapshots(state).values())))
    record = saved["projection"]["records"][0]

    assert record["source_ucids"] == ["U1", "U2"]
    assert record["field_provenance"]["Gross Pay"][1][
        "original_value"
    ] == "1512.42"


def test_exact_replay_is_idempotent(monkeypatch):
    state = environment(monkeypatch)
    approve(state)

    assert call(state)["status"] == "transferred"
    assert call(state)["status"] == "already_transferred"
    assert len(snapshots(state)) == 1


def test_missing_approval_prevents_write(monkeypatch):
    state = environment(monkeypatch)

    with pytest.raises(FakeHTTPException) as err:
        call(state)

    assert err.value.status_code == 409
    assert snapshots(state) == {}


def test_corrupt_approval_prevents_write(monkeypatch):
    state = environment(monkeypatch)
    approve(state)

    key = next(iter(state["container"].data))
    document = json.loads(state["container"].data[key])
    document["decision"] = "approved_ai"
    state["container"].data[key] = json.dumps(
        document
    ).encode("utf-8")

    with pytest.raises(FakeHTTPException) as err:
        call(state)

    assert err.value.status_code == 409
    assert snapshots(state) == {}


def test_denied_project_access_prevents_reads_and_writes(monkeypatch):
    state = environment(monkeypatch)
    state["deny"] = True

    with pytest.raises(FakeHTTPException) as err:
        call(state)

    assert err.value.status_code == 403
    assert state["ready"] == 0
    assert state["container"].data == {}


def test_failing_readiness_prevents_write(monkeypatch):
    state = environment(monkeypatch)
    approve(state)
    state["block_ready"] = True

    with pytest.raises(FakeHTTPException) as err:
        call(state)

    assert err.value.status_code == 409
    assert snapshots(state) == {}


def test_conflicting_merge_set_cannot_replace_c2(monkeypatch):
    state = environment(monkeypatch)
    approve(state)
    assert call(state)["status"] == "transferred"

    other = deepcopy(state["merges"][MERGE_A])
    other["merge_set_id"] = MERGE_B
    other["integrity_sha256"] = "b" * 64
    state["merges"][MERGE_B] = other
    approve(state, MERGE_B)

    with pytest.raises(FakeHTTPException) as err:
        call(state, MERGE_B)

    assert err.value.status_code == 409
    assert len(snapshots(state)) == 1
