"""Test TARai audit approval using a real in-memory SQLAlchemy database."""

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ai.tarai_criteria import TARaiCriteriaApprovalError

Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "tarai_test_audit_logs"

    id = Column(Integer, primary_key=True)
    actor_username = Column(String)
    actor_email = Column(String)
    actor_role = Column(String)
    action = Column(String)
    target_type = Column(String)
    target_id = Column(String)
    workspace = Column(String)
    client = Column(String)
    project = Column(String)
    details = Column(Text)


def write_audit_log(
    db, action, actor=None, request=None,
    target_type="", target_id="", workspace="",
    client="", project="", details=None,
):
    record = AuditLog(
        actor_username=actor.username if actor else "",
        actor_email=getattr(actor, "email", ""),
        actor_role=getattr(actor, "role", ""),
        action=action,
        target_type=target_type,
        target_id=target_id,
        workspace=workspace,
        client=client,
        project=project,
        details=json.dumps(details or {}),
    )
    db.add(record)
    db.commit()
    return record


@pytest.fixture
def approval_environment(monkeypatch):
    model_module = types.ModuleType("app.models.audit_log")
    model_module.AuditLog = AuditLog

    service_module = types.ModuleType("app.services.audit_service")
    service_module.write_audit_log = write_audit_log

    monkeypatch.setitem(
        sys.modules, "app.models.audit_log", model_module
    )
    monkeypatch.setitem(
        sys.modules, "app.services.audit_service", service_module
    )

    path = ROOT / "backend/app/services/ai/tarai_approval.py"
    spec = importlib.util.spec_from_file_location(
        "tarai_approval_sqlite_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield SimpleNamespace(db=db, module=module)

    engine.dispose()


CRITERIA = b"Synthetic attorney-client privilege criteria."


def approve(env):
    return env.module.approve_criteria(
        db=env.db,
        actor=SimpleNamespace(
            username="test-approver",
            email="test@example.invalid",
            role="INSYT Admin",
        ),
        client="INSYT_DEMO",
        project="Project_Ingestion",
        criteria_bytes=CRITERIA,
    )


def verify(env, content=CRITERIA, client="INSYT_DEMO",
           project="Project_Ingestion"):
    return env.module.verify_approved_criteria(
        db=env.db,
        client=client,
        project=project,
        criteria_bytes=content,
    )


def test_approval_persists_and_verifies(approval_environment):
    env = approval_environment
    digest = approve(env)

    record = env.db.query(AuditLog).one()
    assert record.target_id == digest
    assert record.actor_username == "test-approver"
    assert verify(env) == CRITERIA.decode()


def test_missing_approval_rejected(approval_environment):
    with pytest.raises(TARaiCriteriaApprovalError):
        verify(approval_environment)


def test_modified_criteria_rejected(approval_environment):
    env = approval_environment
    approve(env)

    with pytest.raises(TARaiCriteriaApprovalError):
        verify(env, CRITERIA + b" Changed")


def test_other_project_rejected(approval_environment):
    env = approval_environment
    approve(env)

    with pytest.raises(TARaiCriteriaApprovalError):
        verify(env, project="Other_Project")


def test_revocation_blocks_approval(approval_environment):
    env = approval_environment
    approve(env)

    write_audit_log(
        env.db,
        action=env.module.REVOCATION_ACTION,
        actor=SimpleNamespace(
            username="test-approver",
            email="",
            role="INSYT Admin",
        ),
        workspace="discovery",
        client="INSYT_DEMO",
        project="Project_Ingestion",
    )

    with pytest.raises(TARaiCriteriaApprovalError):
        verify(env)


def test_tampered_actor_rejected(approval_environment):
    env = approval_environment
    approve(env)

    record = env.db.query(AuditLog).one()
    record.actor_username = "different-user"
    env.db.commit()

    with pytest.raises(TARaiCriteriaApprovalError):
        verify(env)