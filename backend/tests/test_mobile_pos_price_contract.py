"""Regression coverage for the mobile POS menu-price contract."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import pos


@pytest.mark.asyncio
async def test_price_update_keeps_canonical_menu_prices_in_sync(monkeypatch):
    menu_items = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "item-1", "name": "Kahve", "price": 50.0, "unit_price": 50.0}),
        update_one=AsyncMock(),
    )
    audit_logs = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        pos,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="cashier", user_id="user-1")),
    )
    monkeypatch.setattr(pos, "db", SimpleNamespace(pos_menu_items=menu_items, audit_logs=audit_logs))

    await pos.update_menu_item_price_mobile("item-1", pos.MenuPriceUpdateRequest(new_price=79.995), credentials=None)

    values = menu_items.update_one.await_args.args[1]["$set"]
    assert values["price"] == 80.0
    assert values["unit_price"] == 80.0


@pytest.mark.asyncio
async def test_price_update_rejects_negative_price_before_lookup(monkeypatch):
    monkeypatch.setattr(
        pos,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="cashier", user_id="user-1")),
    )
    monkeypatch.setattr(pos, "db", SimpleNamespace())

    with pytest.raises(HTTPException) as error:
        await pos.update_menu_item_price_mobile("item-1", pos.MenuPriceUpdateRequest(new_price=-1), credentials=None)

    assert error.value.status_code == 400
