from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import kitchen


class _KitchenOrders:
    def __init__(self, status="pending"):
        self.doc = {"id": "order-1", "tenant_id": "tenant-1", "status": status}
        self.update = None

    async def find_one(self, query, _projection=None):
        if query.get("tenant_id") == self.doc["tenant_id"] and query.get("id") == self.doc["id"]:
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        if query.get("status") != self.doc["status"]:
            return SimpleNamespace(modified_count=0)
        self.update = update
        self.doc.update(update["$set"])
        return SimpleNamespace(modified_count=1)


def _user():
    return SimpleNamespace(tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_kitchen_status_follows_forward_only_lifecycle(monkeypatch):
    orders = _KitchenOrders("pending")
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=orders))
    monkeypatch.setattr(kitchen, "_broadcast_kitchen_queue", lambda _tenant: _noop())

    result = await kitchen.update_kitchen_order_status_v2("order-1", "preparing", current_user=_user())

    assert result["status"] == "preparing"
    assert orders.doc["status"] == "preparing"
    assert orders.doc.get("started_at")


@pytest.mark.asyncio
async def test_kitchen_status_rejects_backward_or_skipped_transition(monkeypatch):
    orders = _KitchenOrders("ready")
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=orders))

    with pytest.raises(HTTPException) as exc:
        await kitchen.update_kitchen_order_status_v2("order-1", "preparing", current_user=_user())

    assert exc.value.status_code == 409
    assert orders.doc["status"] == "ready"


@pytest.mark.asyncio
async def test_kitchen_status_rejects_unknown_value(monkeypatch):
    orders = _KitchenOrders("pending")
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=orders))

    with pytest.raises(HTTPException) as exc:
        await kitchen.update_kitchen_order_status_v2("order-1", "cancelled-by-screen", current_user=_user())

    assert exc.value.status_code == 422


async def _noop():
    return None
