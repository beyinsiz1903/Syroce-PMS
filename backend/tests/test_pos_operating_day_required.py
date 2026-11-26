"""A missing hotel operating day must never become a calendar-dated sale."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.test_pos_final_consistency_replica import ctx, menu, paid

pytest_plugins = ("tests.test_pos_final_consistency_replica",)


@pytest.mark.asyncio
@pytest.mark.parametrize("business_date", [None, "", "invalid", "2026-02-30"])
async def test_new_pos_order_requires_a_valid_operating_day(db, service, business_date):
    await menu(db)
    await db.tenant_settings.update_one({"tenant_id": "t"}, {"$set": {"business_date": business_date}})
    service._enqueue_kot = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await service.create_order(ctx(), "bar", items=[{"item_id": "tea", "quantity": 1}])
    assert error.value.status_code == 409
    assert await db.pos_orders.count_documents({}) == 0
    assert await db.kitchen_orders.count_documents({}) == 0
    service._enqueue_kot.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_operating_day_rejects_refund_without_changing_the_sale(db, service):
    await paid(db)
    await db.tenant_settings.delete_many({"tenant_id": "t"})
    with pytest.raises(HTTPException) as error:
        await service.refund_order(ctx(), "paid", 10, "Yerel eksik iş günü denemesi", "missing-day")
    assert error.value.status_code == 409
    assert await db.pos_transactions.count_documents({"payment_type": "refund"}) == 0
    assert (await db.pos_orders.find_one({"id": "paid"}))["payment_status"] == "paid"
