"""Room upgrades must not bypass the financial correction workflow."""

from types import SimpleNamespace

import pytest

from modules.pms_core import front_desk_service


class _Bookings:
    async def find_one(self, query, projection):
        assert query == {"id": "booking-1", "tenant_id": "tenant-1"}
        return {"id": "booking-1", "status": "checked_in", "total_amount": 10000}


@pytest.mark.asyncio
async def test_room_upgrade_rejects_rate_adjustment_before_room_move(monkeypatch):
    service = front_desk_service.FrontDeskService()
    monkeypatch.setattr(
        front_desk_service,
        "db",
        SimpleNamespace(bookings=_Bookings()),
    )

    async def must_not_move(*args, **kwargs):
        raise AssertionError("Finansal koruma öncesinde oda taşıma çalışmamalı")

    monkeypatch.setattr(service, "room_move", must_not_move)

    result = await service.room_upgrade(
        tenant_id="tenant-1",
        booking_id="booking-1",
        new_room_id="room-2",
        reason="Daha geniş oda talebi",
        rate_adjustment=500,
        user_id="user-1",
        user_name="Yetkili",
    )

    assert result["success"] is False
    assert result["code"] == "rate_adjustment_requires_financial_workflow"
    assert "günlük fiyat düzeltmesi" in result["error"].lower()
