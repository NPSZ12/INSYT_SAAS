from types import SimpleNamespace

import pytest

from apc.worksheet_checkpoint_executor import (
    WorksheetCheckpointExecutor,
)


class FakeClaim:
    def __init__(self):
        self.released = False
        self.verified = 0

    def assert_active(self):
        self.verified += 1

    def renew(self):
        self.verified += 1

    def release(self):
        self.released = True


class FakeClaims:
    def __init__(self, claim):
        self.claim = claim
        self.calls = 0

    def try_acquire(self, checkpoint):
        self.calls += 1
        return self.claim


def make_executor(monkeypatch, claims, cached=None):
    executor = object.__new__(WorksheetCheckpointExecutor)
    executor.claim_store = claims

    monkeypatch.setattr(
        executor,
        "_fingerprint",
        lambda unit: "synthetic-fingerprint",
    )

    monkeypatch.setattr(
        executor,
        "_checkpoint",
        lambda unit, fingerprint: "synthetic-checkpoint",
    )

    monkeypatch.setattr(
        executor,
        "_restore",
        lambda unit, fingerprint: cached,
    )

    return executor


def test_completed_checkpoint_skips_claim(monkeypatch):
    claims = FakeClaims(FakeClaim())
    saved = {"candidates": [], "scan_complete": True}

    executor = make_executor(
        monkeypatch,
        claims,
        cached=saved,
    )

    result = executor(SimpleNamespace())

    assert result is saved
    assert claims.calls == 0


def test_claim_protects_execution_and_releases(monkeypatch):
    claim = FakeClaim()
    claims = FakeClaims(claim)
    executor = make_executor(monkeypatch, claims)

    calls = []
    expected_claim = claim

    def execute(unit, *, claim=None):
        assert claim is expected_claim
        calls.append(unit)
        return {"candidates": []}

    monkeypatch.setattr(
        executor,
        "_execute_unclaimed",
        execute,
    )

    unit = SimpleNamespace()
    result = executor(unit)

    assert result == {"candidates": []}
    assert calls == [unit]
    assert claims.calls == 1
    assert claim.verified >= 2
    assert claim.released is True


def test_competing_worker_does_not_execute(monkeypatch):
    claims = FakeClaims(None)
    executor = make_executor(monkeypatch, claims)

    executed = []

    monkeypatch.setattr(
        executor,
        "_execute_unclaimed",
        lambda unit: executed.append(unit),
    )

    with pytest.raises(
        RuntimeError,
        match="leased",
    ):
        executor(SimpleNamespace())

    assert claims.calls == 1
    assert executed == []


def test_claim_released_after_engine_failure(monkeypatch):
    claim = FakeClaim()
    executor = make_executor(
        monkeypatch,
        FakeClaims(claim),
    )

    def fail(unit, *, claim=None):
        raise RuntimeError("Synthetic engine failure")

    monkeypatch.setattr(
        executor,
        "_execute_unclaimed",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="Synthetic engine failure",
    ):
        executor(SimpleNamespace())

    assert claim.released is True