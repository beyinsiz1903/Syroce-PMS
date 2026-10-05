from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from channel_manager.application import reservation_import_service as import_module
from channel_manager.application.reservation_import_service import ReservationImportService
from channel_manager.domain.models.reservation_import import ImportedReservation


@pytest.mark.asyncio
async def test_channel_stay_change_writes_visible_and_immutable_audit(monkeypatch):
    bookings = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "booking-1",
                "tenant_id": "tenant-1",
                "check_in": "2026-09-05T14:00:00+03:00",
                "check_out": "2026-09-06T12:00:00+03:00",
                "adults": 2,
                "children": 0,
                "total_amount": 4200.0,
                "special_requests": "",
                "external_reservation_id": "ext-1",
            }
        ),
        update_one=AsyncMock(),
    )
    activity_log = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(import_module, "db", SimpleNamespace(bookings=bookings, reservation_activity_log=activity_log))
    audit_log = AsyncMock()
    publish_change = AsyncMock()
    monkeypatch.setattr(import_module, "audit_log", audit_log)
    monkeypatch.setattr(import_module, "publish_booking_change", publish_change)

    imported = ImportedReservation(
        tenant_id="tenant-1",
        property_id="property-1",
        connector_id="connector-1",
        batch_id="batch-1",
        external_reservation_id="ext-1",
        pms_booking_id="booking-1",
        channel_name="Expedia",
        arrival_date="2026-09-05T14:00:00+03:00",
        departure_date="2026-09-07T12:00:00+03:00",
        adult_count=2,
        child_count=0,
        total_amount=8400.0,
    )

    await ReservationImportService()._modify_pms_booking("tenant-1", imported)

    activity = activity_log.insert_one.await_args.args[0]
    assert activity["action"] == "stay_dates_updated"
    assert activity["actor"] == "Expedia"
    assert activity["details"]["source"] == "Kanal / OTA"
    assert activity["details"]["changes"]["check_out"] == {
        "from": "2026-09-06T12:00:00+03:00",
        "to": "2026-09-07T12:00:00+03:00",
    }

    audit = audit_log.await_args.kwargs
    assert audit["entity_id"] == "booking-1"
    assert audit["metadata"]["activity_action"] == "stay_dates_updated"
    assert audit["metadata"]["changes"]["total_amount"] == {"from": 4200.0, "to": 8400.0}
