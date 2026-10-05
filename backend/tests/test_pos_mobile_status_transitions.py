from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import pos_mobile


class _Orders:
    def __init__(self, status="pending"):
        self.doc = {"id": "order-1", "tenant_id": "tenant-1", "status": status, "status_history": []}

    async def find_one(self, query):
        if query.get("id") == self.doc["id"] and query.get("tenant_id") == self.doc["tenant_id"]:
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        if query.get("status") != self.doc["status"]:
            return SimpleNamespace(modified_count=0)
        self.doc.update(update["$set"])
        self.doc.setdefault("status_history", []).append(update["$push"]["status_history"])
        return SimpleNamespace(modified_count=1)


def _user():
    return SimpleNamespace(tenant_id="tenant-1", username="manager", role="fnb_manager")


async def _current_user(_credentials):
    return _user()


@pytest.mark.asyncio
async def test_mobile_order_status_advances_one_step_and_records_history(monkeypatch):
    orders = _Orders("pending")
    monkeypatch.setattr(pos_mobile, "db", SimpleNamespace(pos_orders=orders))
    monkeypatch.setattr(pos_mobile, "get_current_user", _current_user)

    result = await pos_mobile.update_order_status(
        "order-1",
        pos_mobile.UpdateOrderStatusRequest(status="preparing", notes="Mutfak aldı"),
        credentials=object(),
    )

    assert result["new_status"] == "preparing"
    assert orders.doc["status"] == "preparing"
    assert orders.doc["status_history"][0]["from_status"] == "pending"


@pytest.mark.asyncio
async def test_mobile_order_status_rejects_skipped_or_backward_transition(monkeypatch):
    orders = _Orders("ready")
    monkeypatch.setattr(pos_mobile, "db", SimpleNamespace(pos_orders=orders))
    monkeypatch.setattr(pos_mobile, "get_current_user", _current_user)

    with pytest.raises(HTTPException) as exc:
        await pos_mobile.update_order_status(
            "order-1",
            pos_mobile.UpdateOrderStatusRequest(status="preparing"),
            credentials=object(),
        )

    assert exc.value.status_code == 409
    assert orders.doc["status"] == "ready"


@pytest.mark.asyncio
async def test_mobile_order_terminal_status_is_immutable(monkeypatch):
    orders = _Orders("served")
    monkeypatch.setattr(pos_mobile, "db", SimpleNamespace(pos_orders=orders))
    monkeypatch.setattr(pos_mobile, "get_current_user", _current_user)

    with pytest.raises(HTTPException) as exc:
        await pos_mobile.update_order_status(
            "order-1",
            pos_mobile.UpdateOrderStatusRequest(status="cancelled"),
            credentials=object(),
        )

    assert exc.value.status_code == 409
