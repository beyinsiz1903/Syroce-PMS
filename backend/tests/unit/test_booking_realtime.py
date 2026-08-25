from unittest.mock import AsyncMock

import pytest

from core.booking_realtime import publish_booking_change


@pytest.mark.asyncio
async def test_publish_booking_change_uses_tenant_scoped_booking_event(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr("websocket_server.broadcast_booking_update", broadcast)

    published = await publish_booking_change(
        tenant_id="tenant-a",
        booking_id="booking-1",
        event_type="cancel",
        status="cancelled",
        source="hotelrunner_callback",
        external_reservation_id="hr-1",
    )

    assert published is True
    broadcast.assert_awaited_once_with(
        {
            "id": "booking-1",
            "status": "cancelled",
            "source": "hotelrunner_callback",
            "external_reservation_id": "hr-1",
        },
        event_type="cancel",
        tenant_id="tenant-a",
    )


@pytest.mark.asyncio
async def test_publish_booking_change_is_best_effort(monkeypatch):
    broadcast = AsyncMock(side_effect=RuntimeError("transport unavailable"))
    monkeypatch.setattr("websocket_server.broadcast_booking_update", broadcast)

    published = await publish_booking_change(
        tenant_id="tenant-a",
        booking_id="booking-1",
        event_type="update",
    )

    assert published is False


@pytest.mark.asyncio
async def test_publish_booking_change_requires_tenant_and_booking():
    assert await publish_booking_change(
        tenant_id="",
        booking_id="booking-1",
        event_type="update",
    ) is False
    assert await publish_booking_change(
        tenant_id="tenant-a",
        booking_id="",
        event_type="update",
    ) is False
