from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_dispatch_materializes_before_draining_same_database(monkeypatch):
    from celery_tasks import _dispatch_and_deliver_messaging
    from modules.messaging import automation, whatsapp_lifecycle

    db = object()
    order = []

    async def materialize(*, db):
        order.append("materialize")
        return {"processed": 1}

    async def drain():
        assert order == ["materialize"]
        order.append("drain")
        return {"attempted": 1}

    events = AsyncMock(side_effect=materialize)
    delivery = MagicMock()
    delivery.drain = AsyncMock(side_effect=drain)
    factory = MagicMock(return_value=delivery)
    monkeypatch.setattr(automation, "dispatch_due_booking_events", events)
    monkeypatch.setattr(whatsapp_lifecycle, "WhatsAppDelivery", factory)
    result = await _dispatch_and_deliver_messaging(db)
    events.assert_awaited_once_with(db=db)
    factory.assert_called_once_with(db)
    delivery.drain.assert_awaited_once_with()
    assert result == {"events": {"processed": 1}, "deliveries": {"attempted": 1}}


def test_recovery_sweeps_are_seconds_not_minutes():
    from celery_app import celery_app

    for name in ("messaging-automation-dispatch", "messaging-delivery-retry"):
        assert celery_app.conf.beat_schedule[name]["schedule"] == 5.0
