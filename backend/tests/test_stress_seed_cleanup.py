"""
F5 — Stress Seed/Cleanup gate tests.

These tests validate the fail-closed gates without touching the DB.
They use FastAPI's dependency_overrides to bypass the super_admin
auth and exercise the env/payload guards.

The "happy path" insert/delete flow is validated in the F5 runtime
smoke recorded in `docs/drill_reports/20260513_stress_f5_seed_cleanup_smoke.md`.
"""
import os
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

STRESS_TID = "23377306-a501-4232-adc8-8aea50e243c0"
PILOT_TID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"


@pytest.fixture
def stress_client(monkeypatch):
    """Build an isolated FastAPI app that mounts only the stress router
    and overrides the super_admin dependency to a no-op."""
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS_TID)
    monkeypatch.setenv("PILOT_TENANT_ID", PILOT_TID)

    # Reload to pick up env (require_super_admin_guard is constructed at import)
    from core import helpers as _helpers
    importlib.reload(_helpers)
    import domains.admin.router.stress as stress_mod
    importlib.reload(stress_mod)

    # Override super_admin dep to no-op user
    class _FakeUser:
        id = "fake"
        role = "super_admin"
        tenant_id = STRESS_TID

    async def _fake_admin():
        return _FakeUser()

    app = FastAPI()
    app.include_router(stress_mod.router)
    app.dependency_overrides[stress_mod.require_super_admin] = _fake_admin
    return TestClient(app)


SEED_PATH = "/api/admin/stress/seed"
CLEANUP_PATH = "/api/admin/stress/cleanup"


def test_seed_rejects_wrong_tenant_id(stress_client, monkeypatch):
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    r = stress_client.post(
        SEED_PATH,
        json={"target_tenant_id": "00000000-0000-0000-0000-000000000000", "room_count": 1},
    )
    assert r.status_code == 403, r.text
    assert "does not match" in r.json()["detail"]


def test_seed_rejects_pilot_tenant_id(stress_client, monkeypatch):
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    # If anything tries to seed the pilot tenant_id, the stress_tid
    # mismatch gate fires first (since stress_tid != pilot_tid).
    r = stress_client.post(
        SEED_PATH,
        json={"target_tenant_id": PILOT_TID, "room_count": 1},
    )
    assert r.status_code == 403, r.text


def test_seed_rejects_when_destructive_flag_off(stress_client, monkeypatch):
    monkeypatch.delenv("E2E_ALLOW_DESTRUCTIVE_STRESS", raising=False)
    r = stress_client.post(
        SEED_PATH,
        json={"target_tenant_id": STRESS_TID, "room_count": 1},
    )
    assert r.status_code == 403, r.text
    assert "E2E_ALLOW_DESTRUCTIVE_STRESS" in r.json()["detail"]


def test_seed_rejects_when_stress_tid_env_missing(stress_client, monkeypatch):
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    monkeypatch.delenv("E2E_STRESS_TENANT_ID", raising=False)
    r = stress_client.post(
        SEED_PATH,
        json={"target_tenant_id": STRESS_TID, "room_count": 1},
    )
    assert r.status_code == 412, r.text
    assert "E2E_STRESS_TENANT_ID" in r.json()["detail"]


def test_seed_rejects_room_count_above_cap(stress_client, monkeypatch):
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    r = stress_client.post(
        SEED_PATH,
        json={"target_tenant_id": STRESS_TID, "room_count": 500},
    )
    # Pydantic 422 (Field le=25)
    assert r.status_code == 422, r.text


def test_cleanup_rejects_wrong_tenant_id(stress_client, monkeypatch):
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    r = stress_client.post(
        CLEANUP_PATH,
        json={"target_tenant_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 403, r.text


def test_cleanup_rejects_when_destructive_flag_off(stress_client, monkeypatch):
    monkeypatch.delenv("E2E_ALLOW_DESTRUCTIVE_STRESS", raising=False)
    r = stress_client.post(
        CLEANUP_PATH,
        json={"target_tenant_id": STRESS_TID},
    )
    assert r.status_code == 403, r.text


def test_cleanup_rejects_unbounded_delete_without_prefix(stress_client, monkeypatch):
    """Defense-in-depth: cleanup without data_prefix AND without
    explicit confirm_full_wipe must be refused (400)."""
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    r = stress_client.post(
        CLEANUP_PATH,
        json={"target_tenant_id": STRESS_TID},
    )
    assert r.status_code == 400, r.text
    assert "data_prefix" in r.json()["detail"]
    assert "confirm_full_wipe" in r.json()["detail"]


def test_cleanup_full_wipe_explicit_passes_gate(stress_client, monkeypatch):
    """Explicit confirm_full_wipe=true (no prefix) is allowed — the
    request reaches the deletion stage. We monkeypatch tenant_context
    + db to avoid touching a real Mongo here."""
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    import domains.admin.router.stress as stress_mod
    from contextlib import contextmanager

    class _StubColl:
        async def delete_many(self, flt):
            class R: deleted_count = 0
            return R()

    class _StubDb:
        def __getattr__(self, _name): return _StubColl()

    @contextmanager
    def _noop_ctx(_tid): yield
    monkeypatch.setattr(stress_mod, "tenant_context", _noop_ctx)
    import core.database as _coredb
    monkeypatch.setattr(_coredb, "db", _StubDb())

    r = stress_client.post(
        CLEANUP_PATH,
        json={"target_tenant_id": STRESS_TID, "confirm_full_wipe": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_wipe"] is True
    # Idempotency: every collection returns 0 from stub
    assert all(v == 0 for v in body["deleted_counts"].values())
    assert body["idempotent"] is True
