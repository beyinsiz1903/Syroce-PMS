import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from domains.admin.router.stress import _gates


def test_gates_valid_stress_tid():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123", "E2E_ALLOW_DESTRUCTIVE_STRESS": "true"}):
        result = _gates("stress-123")
        assert result["target_matches_stress_tid"] is True
        assert result["env_stress_tid_present"] is True

def test_gates_valid_pos_tid():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123", "E2E_ALLOW_DESTRUCTIVE_STRESS": "true"}):
        result = _gates("pos-123")
        assert result["target_matches_stress_tid"] is True

def test_gates_random_tenant_rejected():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123"}):
        with pytest.raises(HTTPException) as exc:
            _gates("random-456")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)

def test_gates_empty_tenant_rejected():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123", "STRESS_POS_TENANT_ID": "pos-123"}):
        with pytest.raises(HTTPException) as exc:
            _gates("")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)

def test_gates_empty_tenant_rejected_when_pos_env_missing():
    with patch.dict(os.environ, {"E2E_STRESS_TENANT_ID": "stress-123"}, clear=True):
        with pytest.raises(HTTPException) as exc:
            _gates("")
        assert exc.value.status_code == 403
        assert "not an allowed stress tenant" in str(exc.value.detail)


class _Tenants:
    def __init__(self, rows=(), boom=False):
        self.rows, self.boom = list(rows), boom

    async def find_one(self, query):
        if self.boom:
            raise RuntimeError("db down")
        wanted = {cond.get("id") or cond.get("hotel_id") for cond in query["$or"]}
        return next((r for r in self.rows if r["id"] in wanted or r.get("hotel_id") in wanted), None)


def _sysdb(monkeypatch, **kw):
    from types import SimpleNamespace

    import core.tenant_db as tenant_db

    monkeypatch.setattr(tenant_db, "get_system_db", lambda: SimpleNamespace(tenants=_Tenants(**kw)))


@pytest.mark.asyncio
async def test_resolver_maps_hotel_id_to_tenant_uuid(monkeypatch):
    from domains.admin.router.stress import _resolve_stress_tid_async

    _sysdb(monkeypatch, rows=[{"id": "uuid-1", "hotel_id": "343281"}])
    assert await _resolve_stress_tid_async("343281", require_existing=True) == "uuid-1"


@pytest.mark.asyncio
async def test_seed_refuses_a_stress_tenant_that_does_not_exist(monkeypatch):
    """Deleted stress tenant: the raw hotel_id must never become a tenant_id."""
    from domains.admin.router.stress import _resolve_stress_tid_async

    _sysdb(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await _resolve_stress_tid_async("343281", require_existing=True)
    assert exc.value.status_code == 412 and "orphan" in exc.value.detail
    _sysdb(monkeypatch, boom=True)
    with pytest.raises(HTTPException) as exc:
        await _resolve_stress_tid_async("343281", require_existing=True)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_cleanup_keeps_the_fallback_to_sweep_leftovers(monkeypatch):
    from domains.admin.router.stress import _resolve_stress_tid_async

    _sysdb(monkeypatch)
    assert await _resolve_stress_tid_async("343281") == "343281"
