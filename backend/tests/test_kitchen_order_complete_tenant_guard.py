"""Regression tests for `complete_kitchen_order` tenant-scoping fix.

P0 finding from CI 2026-05-25 (e2e-stress 98-pos-kds-inventory.spec.js
"C) cross-tenant KDS IDOR"): the handler issued

    db.kitchen_orders.update_one({'id': order_id}, ...)

with no `tenant_id` filter, letting any authenticated user mark another
tenant's kitchen ticket as ready. These tests pin the fix.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import kitchen


class _FakeKitchenColl:
    """Captures the filter passed to `update_one` and reports the
    matched_count we want for the test scenario."""

    def __init__(self, matched: int):
        self._matched = matched
        self.last_filter = None
        self.last_update = None

    async def update_one(self, flt, upd):
        self.last_filter = flt
        self.last_update = upd
        return SimpleNamespace(matched_count=self._matched, modified_count=self._matched)

    async def find_one(self, filter, projection=None):
        # We return None so that the 404 block is triggered as expected
        return None


class _FakeDB:
    def __init__(self, matched: int):
        self.kitchen_orders = _FakeKitchenColl(matched)


@pytest.fixture
def fake_user():
    return SimpleNamespace(id="u1", tenant_id="tenant-A")


async def _call_complete(monkeypatch, matched, fake_user, order_id="order-123"):
    fake_db = _FakeDB(matched)
    monkeypatch.setattr(kitchen, "db", fake_db)

    async def _noop_broadcast(_tenant_id):
        return None
    monkeypatch.setattr(kitchen, "_broadcast_kitchen_queue", _noop_broadcast)

    result = await kitchen.complete_kitchen_order(
        order_id=order_id,
        current_user=fake_user,
        _perm=None,
    )
    return result, fake_db.kitchen_orders


async def test_complete_filter_includes_tenant_id(monkeypatch, fake_user):
    """The mongo filter MUST scope by tenant — without this, any caller
    can flip another tenant's kitchen_order to ready (P0 IDOR)."""
    _result, coll = await _call_complete(monkeypatch, matched=1, fake_user=fake_user)
    assert coll.last_filter is not None
    assert coll.last_filter.get("tenant_id") == "tenant-A"
    assert coll.last_filter.get("id") == "order-123"


async def test_complete_returns_404_when_order_not_in_tenant(monkeypatch, fake_user):
    """Cross-tenant call: the order exists but not in caller's tenant →
    matched_count=0 → must 404, NOT silently succeed."""
    with pytest.raises(HTTPException) as exc:
        await _call_complete(monkeypatch, matched=0, fake_user=fake_user)
    assert exc.value.status_code == 404


async def test_complete_happy_path_returns_success(monkeypatch, fake_user):
    """Same-tenant call still works (no regression for the legitimate path)."""
    result, coll = await _call_complete(monkeypatch, matched=1, fake_user=fake_user)
    assert result["success"] is True
    assert coll.last_update["$set"]["status"] == "ready"
    assert "ready_at" in coll.last_update["$set"]
