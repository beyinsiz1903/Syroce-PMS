"""Real replica regressions for the reservation-card room-change button."""
import asyncio

import pytest

from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def wire_chain(acceptance, monkeypatch):
    from core import audit_chain, utils
    monkeypatch.setattr(audit_chain, "_system_db", lambda: acceptance.db)
    monkeypatch.setattr(utils, "db", acceptance.db)


async def target(a, **fields):
    await a.db.rooms.insert_one({"tenant_id": "qa", "id": "target", "room_number": "QA105",
                                "status": "available", "capacity": 2, **fields})
    await a.db.room_night_locks.create_index([("tenant_id", 1), ("room_id", 1), ("night_date", 1)], unique=True)


async def move(a, **fields):
    return await a.api.post("/api/pms/reservations/synthetic-stay/room-change", json={
        "new_room_id": "target", "reason": "Yerel QA oda değişimi", "extra_charge": 10, **fields})


@pytest.mark.parametrize("status", ["occupied", "dirty", "cleaning", "out_of_order", "out_of_service", "maintenance"])
async def test_unready_target_rejected_without_any_partial_mutation(acceptance, status):
    a = acceptance
    await target(a, status=status, current_booking_id="other" if status == "occupied" else None)
    before = await a.db.bookings.find_one({"id": "synthetic-stay"})
    response = await move(a)
    assert response.status_code == 409, response.text
    assert await a.db.bookings.find_one({"id": "synthetic-stay"}) == before
    assert await a.db.room_move_history.count_documents({}) == 0
    assert await a.db.folio_charges.count_documents({}) == 1


async def test_same_room_does_not_charge_or_dirty_current_room(acceptance):
    response = await move(acceptance, new_room_id="synthetic-room")
    assert response.status_code == 409, response.text
    assert await acceptance.db.folio_charges.count_documents({}) == 1


async def test_available_but_future_booked_target_rejected(acceptance):
    a = acceptance
    await target(a)
    await a.db.bookings.insert_one({"tenant_id": "qa", "id": "future", "room_id": "target",
        "status": "confirmed", "check_in": "2026-10-25T14:00:00Z", "check_out": "2026-10-28T12:00:00Z"})
    response = await move(a)
    assert response.status_code == 409, response.text
    assert (await a.db.bookings.find_one({"id": "synthetic-stay"}))["room_id"] == "synthetic-room"


async def test_pending_assignment_never_occupies_or_dirties_physical_rooms(acceptance):
    a = acceptance
    await target(a)
    await a.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {"status": "confirmed", "check_in": "2026-10-27", "check_out": "2026-10-29"}})
    await a.db.rooms.update_one({"id": "synthetic-room"}, {"$set": {"status": "available", "current_booking_id": None}})
    response = await move(a, extra_charge=0)
    assert response.status_code == 200, response.text
    assert (await a.db.rooms.find_one({"id": "target"}))["status"] == "available"
    assert (await a.db.rooms.find_one({"id": "synthetic-room"}))["status"] == "available"


async def test_late_failure_rolls_back_room_booking_locks_and_fee(acceptance, monkeypatch):
    a = acceptance
    await target(a)
    before = await a.db.bookings.find_one({"id": "synthetic-stay"})
    original = a.db.room_move_history.insert_one
    # Fail a durable history write after the physical assignment has started.
    async def fail_history(self, *args, **kwargs):
        if self.name == "room_move_history":
            raise RuntimeError("QA history write unavailable")
        return await original.__func__(self, *args, **kwargs)
    monkeypatch.setattr(type(a.db.room_move_history), "insert_one", fail_history)
    with pytest.raises(RuntimeError, match="history write unavailable"):
        await move(a)
    assert await a.db.bookings.find_one({"id": "synthetic-stay"}) == before
    assert (await a.db.rooms.find_one({"id": "target"}))["status"] == "available"
    assert await a.db.folio_charges.count_documents({}) == 1
    assert await a.db.room_night_locks.count_documents({}) == 0


async def test_success_moves_all_nights_and_preserves_fee_currency_and_sealed_audit(acceptance):
    a = acceptance
    await target(a)
    response = await move(a)
    assert response.status_code == 200, response.text
    assert (await a.db.rooms.find_one({"id": "synthetic-room"}))["status"] == "dirty"
    assert (await a.db.rooms.find_one({"id": "target"}))["current_booking_id"] == "synthetic-stay"
    assert await a.db.room_night_locks.count_documents({"room_id": "target", "booking_id": "synthetic-stay"}) == 5
    fee = await a.db.folio_charges.find_one({"charge_type": "room_upgrade"})
    assert (fee["total"], fee["currency"], fee["business_date"]) == (10, "USD", "2026-10-26")
    audit = await a.db.audit_logs.find_one({"action": "room_changed"})
    assert audit["record_hash"] and audit["metadata"]["reason"] == "Yerel QA oda değişimi"


async def test_paid_upgrade_remains_additive_through_payment_and_checkout(acceptance):
    a = acceptance
    await target(a, room_type="Suite")
    await a.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {
        "total_amount": 6600, "currency": "TRY", "check_in": "2026-10-23", "check_out": "2026-10-26"}})
    await a.db.folios.update_one({"id": "synthetic-folio"}, {"$set": {"currency": "TRY", "balance": 0}})
    await a.db.folio_charges.delete_many({"booking_id": "synthetic-stay"})
    response = await move(a, extra_charge=2400)
    assert response.status_code == 200, response.text
    detail = await a.api.get("/api/pms/reservations/synthetic-stay/full-detail")
    assert detail.status_code == 200, detail.text
    summary = detail.json()["summary"]
    assert summary["gross_total"] == summary["reservation_total_due"] == 9000
    assert summary["unposted_room_amount"] == 6600
    assert summary["additional_charge_total"] == 2400
    assert summary["pricing_reconciliation_required"] is False
    rejected = await a.api.post("/api/frontdesk/checkout/synthetic-stay")
    assert rejected.status_code == 402, rejected.text
    assert await a.db.folio_charges.count_documents({"charge_type": "room_charge"}) == 0
    payment = await a.api.post("/api/frontdesk/folio/synthetic-stay/payment", json={
        "amount": 9000, "currency": "TRY", "method": "card", "payment_type": "final",
        "reference": "LOCAL-UPGRADE-NO-PSP"}, headers={"Idempotency-Key": "upgrade-final"})
    assert payment.status_code == 200, payment.text
    checkout = await a.api.post("/api/frontdesk/checkout/synthetic-stay")
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["total_balance"] == 0
    charges = await a.db.folio_charges.find({"booking_id": "synthetic-stay", "voided": False}).to_list(None)
    assert sum(row["total"] for row in charges) == 9000
    assert sum(row["total"] for row in charges if row["charge_type"] == "room_charge") == 6600
    assert sum(row["total"] for row in charges if row["charge_type"] == "room_upgrade") == 2400
    assert (await a.db.bookings.find_one({"id": "synthetic-stay"}))["total_amount"] == 6600


async def test_two_guests_cannot_concurrently_claim_same_target(acceptance):
    a = acceptance
    await target(a)
    second = await a.db.bookings.find_one({"id": "synthetic-stay"}, {"_id": 0})
    second.update(id="second", room_id="second-room", room_number="QA106")
    await a.db.bookings.insert_one(second)
    await a.db.rooms.insert_one({"id": "second-room", "tenant_id": "qa", "status": "occupied", "current_booking_id": "second"})
    responses = await asyncio.gather(move(a), a.api.post("/api/pms/reservations/second/room-change", json={
        "new_room_id": "target", "reason": "Yerel ikinci misafir testi", "extra_charge": 0}))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    assert await a.db.bookings.count_documents({"room_id": "target"}) == 1
    assert await a.db.room_move_history.count_documents({}) == 1
