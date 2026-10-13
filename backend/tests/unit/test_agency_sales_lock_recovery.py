from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import marketplace_b2b as marketplace


@pytest.mark.asyncio
async def test_modification_lock_evidence_resolves_proposal_to_its_booking():
    negotiations = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "proposal-1", "reservation_id": "booking-1", "status": "awaiting_hotel",
    }))
    bookings = SimpleNamespace(find_one=AsyncMock(return_value={"id": "booking-1", "status": "confirmed"}))
    database = SimpleNamespace(marketplace_negotiations=negotiations, bookings=bookings)

    evidence = await marketplace._sales_lock_evidence(database, {
        "tenant_id": "hotel-1", "agency_id": "agency-1", "operation": "marketplace_modification",
        "reference_id": "proposal-1", "idempotency_key": None,
    })

    assert evidence["proposal"]["reservation_id"] == "booking-1"
    assert evidence["booking"]["id"] == "booking-1"
    assert bookings.find_one.call_args.args[0]["id"] == "booking-1"


@pytest.mark.asyncio
async def test_recovery_never_deletes_lock_when_audit_record_cannot_be_saved(monkeypatch):
    lock = {"_id": "lock-1", "owner": "owner-123", "tenant_id": "hotel-1", "agency_id": "agency-1"}
    mutexes = SimpleNamespace(
        find_one=AsyncMock(return_value=lock),
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
    )
    database = SimpleNamespace(
        agency_sale_mutexes=mutexes,
        agency_sales_lock_recoveries=SimpleNamespace(insert_one=AsyncMock(side_effect=RuntimeError("storage unavailable"))),
    )
    monkeypatch.setattr(marketplace, "get_system_db", lambda: database)
    monkeypatch.setattr(marketplace, "_sales_lock_evidence", AsyncMock(return_value={"booking": None, "idempotency": None, "proposal": None}))

    data = marketplace.AgencySalesLockReconcile(
        owner="owner-123", resolution="no_booking_committed", reason="Original writer was stopped safely", writer_stopped_confirmed=True,
    )
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await marketplace.admin_reconcile_agency_sales_lock("lock-1", data, True)
    mutexes.delete_one.assert_not_awaited()
