"""HTTP-level TARai tests without database, storage, or AI access."""

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.storage_paths import build_project_path
from app.services.ai.tarai_protocol import (
    TARaiProtocolError,
    resolve_privilege_fields,
)

API_PATH = ROOT / "backend/app/api/tarai.py"

CLIENT = "INSYT_DEMO"
PROJECT = "Project_Ingestion"
DOC_ID = "INSYT000000001"

PAYLOAD = {
    "client": CLIENT,
    "project": PROJECT,
    "doc_id": DOC_ID,
}


def stub_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def environment(monkeypatch):
    events = []

    def authenticate():
        events.append("authenticate")
        raise HTTPException(401, "Not authenticated")

    def check_scope(user, workspace, client, project):
        events.append("scope")
        if getattr(user, "deny_scope", False):
            raise HTTPException(403, "Project access denied")

    def check_review(user, permission):
        events.append("permission")
        if permission == "Can: Review" and getattr(user, "deny_review", False):
            raise HTTPException(403, "Review access denied")
        if permission == "Can: Manage Protocol" and getattr(
            user, "deny_protocol", False
        ):
            raise HTTPException(403, "Protocol management denied")

    class DisabledError(Exception):
        pass

    class ConfigurationError(Exception):
        pass

    class ResponseError(Exception):
        pass

    dependencies = {
        "app.database.connection": stub_module(
            "app.database.connection",
            get_db=lambda: None,
        ),
        "app.services.ai.tarai_approval": stub_module(
            "app.services.ai.tarai_approval",
            approve_criteria=Mock(return_value="synthetic-sha256"),
            verify_approved_criteria=Mock(
                return_value="Synthetic approved criteria."
            ),
        ),
        "app.services.security": stub_module(
            "app.services.security",
            get_current_user=authenticate,
        ),
        "app.services.authorization": stub_module(
            "app.services.authorization",
            PERMISSION_REVIEW="Can: Review",
            PERMISSION_MANAGE_PROTOCOL="Can: Manage Protocol",
            require_permission=check_review,
            require_scoped_project_access=check_scope,
        ),
        "app.services.ai.tarai_analyzer": stub_module(
            "app.services.ai.tarai_analyzer",
            analyze_privilege=Mock(),
            tarai_enabled=lambda: True,
            TARaiDisabledError=DisabledError,
            TARaiConfigurationError=ConfigurationError,
            TARaiResponseError=ResponseError,
        ),
        "app.api.review": stub_module(
            "app.api.review",
            load_review_document_by_doc_id=Mock(),
        ),
        "app.api.workspace_protocols": stub_module(
            "app.api.workspace_protocols",
            get_workspace_protocol=Mock(),
            get_live_source_container_client=Mock(),
            build_project_path=build_project_path,
        ),
    }

    for name, module in dependencies.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "tarai_isolated_endpoint_test",
        API_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    app = FastAPI()
    app.include_router(module.router)

    document = {
        "workspace": "discovery",
        "project_id": PROJECT,
        "doc_id": DOC_ID,
        "native_storage_source": "live_source",
        "native_blob": build_project_path(
            "discovery", CLIENT, PROJECT,
            "source/native", DOC_ID + ".pdf",
        ),
        "text_blob": build_project_path(
            "discovery", CLIENT, PROJECT,
            "source/text", DOC_ID + ".txt",
        ),
        "text": "Synthetic legal advice request.",
        "text_truncated": False,
    }

    module.load_review_document_by_doc_id.return_value = document

    module.get_workspace_protocol.return_value = {
        "has_protocol": True,
        "protocol": {
            "fields": [
                {
                    "section": "Privilege",
                    "data_element": "Privileged",
                    "format": "Tag",
                },
                {
                    "section": "Privilege",
                    "data_element": "Not Privileged",
                    "format": "Tag",
                },
            ]
        },
    }

    module.load_approved_privilege_criteria = Mock(
        return_value="Synthetic approved privilege criteria."
    )

    module.analyze_privilege.return_value = SimpleNamespace(
        model_dump=lambda: {
            "classification": "needs_review",
            "reviewer_status": "pending",
        }
    )

    def logged_in(user=None):
        app.dependency_overrides[authenticate] = (
            lambda: user or SimpleNamespace()
        )

    return SimpleNamespace(
        app=app,
        client=TestClient(app),
        module=module,
        events=events,
        logged_in=logged_in,
    )


def post(env, payload=None):
    return env.client.post(
        "/api/discovery/tarai/privilege/suggest",
        json=PAYLOAD if payload is None else payload,
    )


def test_unauthenticated_cannot_read_or_infer(environment):
    env = environment

    response = post(env)

    assert response.status_code == 401
    assert env.events == ["authenticate"]
    env.module.load_review_document_by_doc_id.assert_not_called()
    env.module.analyze_privilege.assert_not_called()


@pytest.mark.parametrize("denied", ["scope", "review"])
def test_authorization_denied_before_access(environment, denied):
    env = environment
    env.logged_in(SimpleNamespace(
        deny_scope=(denied == "scope"),
        deny_review=(denied == "review"),
    ))

    response = post(env)

    assert response.status_code == 403
    env.module.get_workspace_protocol.assert_not_called()
    env.module.load_review_document_by_doc_id.assert_not_called()
    env.module.analyze_privilege.assert_not_called()


def test_feature_disabled(environment):
    env = environment
    env.logged_in()
    env.module.tarai_enabled = lambda: False

    response = post(env)

    assert response.status_code == 503
    env.module.get_workspace_protocol.assert_not_called()
    env.module.analyze_privilege.assert_not_called()


def test_missing_project_criteria(environment):
    env = environment
    env.logged_in()
    env.module.load_approved_privilege_criteria.side_effect = (
        HTTPException(409, "Missing criteria")
    )

    response = post(env)

    assert response.status_code == 409
    env.module.load_review_document_by_doc_id.assert_not_called()
    env.module.analyze_privilege.assert_not_called()


@pytest.mark.parametrize("change", [
    {"doc_id": "OTHER_DOC"},
    {"workspace": "capture"},
    {"project_id": "Other_Project"},
    {"native_storage_source": "review_storage"},
    {"text_blob": "OTHER_CLIENT/discovery/Project_Ingestion/source/text/x.txt"},
])
def test_document_identity_rejected(environment, change):
    env = environment
    env.logged_in()

    document = dict(
        env.module.load_review_document_by_doc_id.return_value
    )
    document.update(change)
    env.module.load_review_document_by_doc_id.return_value = document

    response = post(env)

    assert response.status_code == 409
    env.module.analyze_privilege.assert_not_called()


@pytest.mark.parametrize("change", [
    {"text_truncated": True},
    {"text": ""},
    {"text": "x" * 50001},
])
def test_invalid_text_rejected(environment, change):
    env = environment
    env.logged_in()

    document = dict(
        env.module.load_review_document_by_doc_id.return_value
    )
    document.update(change)
    env.module.load_review_document_by_doc_id.return_value = document

    response = post(env)

    assert response.status_code == 422
    env.module.analyze_privilege.assert_not_called()


def test_success_is_read_only(environment):
    env = environment
    env.logged_in()

    response = post(env)

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["workspace"] == "discovery"
    assert data["doc_id"] == DOC_ID
    assert data["saved_to_review"] is False
    assert data["requires_reviewer_approval"] is True
    assert data["suggestion"]["reviewer_status"] == "pending"

    env.module.analyze_privilege.assert_called_once()
    assert env.events == ["scope", "permission"]


def test_browser_cannot_supply_native_blob_or_text(environment):
    env = environment
    env.logged_in()

    response = post(env, {
        **PAYLOAD,
        "native_blob": "OTHER_CLIENT/document.pdf",
        "document_text": "Injected document text",
    })

    assert response.status_code == 422
    env.module.analyze_privilege.assert_not_called()

def test_approval_requires_authentication(environment):
    env = environment
    env.module.read_project_criteria_bytes = Mock(
        return_value=b"Synthetic criteria."
    )

    response = env.client.post(
        "/api/discovery/tarai/privilege/criteria/approve",
        json={"client": CLIENT, "project": PROJECT},
    )

    assert response.status_code == 401
    env.module.read_project_criteria_bytes.assert_not_called()
    env.module.approve_criteria.assert_not_called()


@pytest.mark.parametrize("denied", ["scope", "permission"])
def test_approval_requires_project_and_protocol_permission(
    environment, denied
):
    env = environment
    env.logged_in(SimpleNamespace(
        deny_scope=(denied == "scope"),
        deny_protocol=(denied == "permission"),
    ))
    env.module.read_project_criteria_bytes = Mock(
        return_value=b"Synthetic criteria."
    )

    response = env.client.post(
        "/api/discovery/tarai/privilege/criteria/approve",
        json={"client": CLIENT, "project": PROJECT},
    )

    assert response.status_code == 403
    env.module.read_project_criteria_bytes.assert_not_called()
    env.module.approve_criteria.assert_not_called()


def test_approval_uses_authenticated_actor(environment):
    env = environment
    actor = SimpleNamespace(username="authorized-test-approver")
    env.logged_in(actor)
    env.module.read_project_criteria_bytes = Mock(
        return_value=b"Synthetic criteria."
    )

    response = env.client.post(
        "/api/discovery/tarai/privilege/criteria/approve",
        json={"client": CLIENT, "project": PROJECT},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

    call = env.module.approve_criteria.call_args
    assert call.kwargs["actor"] is actor
    assert call.kwargs["criteria_bytes"] == b"Synthetic criteria."
    assert call.kwargs["client"] == CLIENT
    assert call.kwargs["project"] == PROJECT


def test_approval_rejects_browser_approver_identity(environment):
    env = environment
    env.logged_in()

    response = env.client.post(
        "/api/discovery/tarai/privilege/criteria/approve",
        json={
            "client": CLIENT,
            "project": PROJECT,
            "approved_by": "forged-user",
            "sha256": "forged-hash",
        },
    )

    assert response.status_code == 422
    env.module.approve_criteria.assert_not_called()
