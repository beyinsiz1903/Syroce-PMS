"""
Runtime Stress Tests — OTA Reservation Burst
Simulates burst of OTA reservation requests to validate queue/service stability.
"""
import asyncio
import pytest
import uuid
from datetime import datetime, timezone, timedelta


async def test_ota_reservation_burst(db):
    """Burst 100 reservations concurrently and verify all persisted."""
    tid = "stress-ota-burst-" + uuid.uuid4().hex[:8]

    async def create_booking(idx):
        booking = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "guest_id": f"guest-{idx}",
            "guest_name": f"Stress Guest {idx}",
            "room_id": f"room-{idx % 50}",
            "check_in": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "check_out": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "status": "confirmed",
            "total_amount": 200.0 + idx,
            "channel": "booking_com",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.bookings.insert_one(booking)
        return booking

    tasks = [create_booking(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    count = await db.bookings.count_documents({"tenant_id": tid})
    assert count == 100

    await db.bookings.delete_many({"tenant_id": tid})


async def test_concurrent_checkin_same_room(db):
    """Two concurrent check-ins to the same room."""
    tid = "stress-checkin-" + uuid.uuid4().hex[:8]
    room_id = str(uuid.uuid4())
    await db.rooms.insert_one({"id": room_id, "tenant_id": tid, "room_number": "101", "status": "available"})
    booking_ids = []
    for i in range(2):
        bid = str(uuid.uuid4())
        booking_ids.append(bid)
        await db.bookings.insert_one({
            "id": bid, "tenant_id": tid, "guest_id": f"g-{i}",
            "room_id": room_id, "status": "confirmed",
            "check_in": datetime.now(timezone.utc).isoformat(),
            "check_out": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        })

    async def do_checkin(bid):
        room = await db.rooms.find_one({"id": room_id})
        if room and room["status"] in ("available", "inspected"):
            await db.bookings.update_one({"id": bid}, {"$set": {"status": "checked_in"}})
            await db.rooms.update_one({"id": room_id}, {"$set": {"status": "occupied"}})
            return True
        return False

    results = await asyncio.gather(do_checkin(booking_ids[0]), do_checkin(booking_ids[1]))
    assert any(results)

    await db.rooms.delete_many({"tenant_id": tid})
    await db.bookings.delete_many({"tenant_id": tid})
