"""Service-layer regression for `PosFnbService.complete_kitchen_order`.

Mirrors `test_kitchen_order_complete_tenant_guard.py` (router-layer
regression) at the service layer so the tenant-scoped filter + not-found
fail code stay protected even if a future router rewires through the
service rather than calling Mongo directly.

Context: original router bug was a cross-tenant IDOR — the service
already had the same unscoped `update_one({"id": order_id}, ...)`
pattern as latent risk. Fix scoped by `tenant_id` and returns
`ServiceResult.fail(..., code="not_found")` on miss.
"""
from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb.pos_fnb_service import PosFnbService


class _FakeKitchenColl:
    def __init__(self, matched: int):
        self._matched = matched
        self.last_filter = None
        self.last_update = None

    async def update_one(self, flt, upd):
        self.last_filter = flt
        self.last_update = upd
        return SimpleNamespace(matched_count=self._matched, modified_count=self._matched)


class _FakeDB:
    def __init__(self, matched: int):
        self.kitchen_orders = _FakeKitchenColl(matched)


def _make_service(matched: int) -> PosFnbService:
    svc = PosFnbService()
    svc._db = _FakeDB(matched)
    return svc


@pytest.fixture
def ctx():
    # OperationContext duck-type: only tenant_id is read by the method.
    return SimpleNamespace(
        tenant_id="tenant-A",
        actor_id="u1",
        user_id="u1",
        request_id="r1",
        correlation_id="c1",
        ip="127.0.0.1",
        user_agent="pytest",
    )


async def test_service_complete_filter_includes_tenant_id(ctx):
    svc = _make_service(matched=1)
    await svc.complete_kitchen_order(ctx, "order-123")
    coll = svc._db.kitchen_orders
    assert coll.last_filter == {"id": "order-123", "tenant_id": "tenant-A"}


async def test_service_complete_returns_not_found_when_cross_tenant(ctx):
    svc = _make_service(matched=0)
    result = await svc.complete_kitchen_order(ctx, "order-of-other-tenant")
    assert result.ok is False
    assert result.code == "not_found"


async def test_service_complete_happy_path_returns_success(ctx):
    svc = _make_service(matched=1)
    result = await svc.complete_kitchen_order(ctx, "order-123")
    assert result.ok is True
    assert result.data["success"] is True
    coll = svc._db.kitchen_orders
    assert coll.last_update["$set"]["status"] == "ready"
    assert "ready_at" in coll.last_update["$set"]
