"""
Runtime Stress Tests — Tenant Isolation Under Concurrent Load
"""
import asyncio
import uuid
from datetime import datetime, timezone


async def test_tenant_isolation_concurrent(db):
    """Two tenants operating concurrently should never see each other's data."""
    t1 = "isolation-t1-" + uuid.uuid4().hex[:8]
    t2 = "isolation-t2-" + uuid.uuid4().hex[:8]

    async def insert_bookings(tenant_id, count):
        for i in range(count):
            await db.bookings.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "guest_id": f"guest-{tenant_id}-{i}",
                "room_id": f"room-{i}",
                "status": "confirmed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    await asyncio.gather(insert_bookings(t1, 50), insert_bookings(t2, 30))

    t1_count = await db.bookings.count_documents({"tenant_id": t1})
    t2_count = await db.bookings.count_documents({"tenant_id": t2})

    assert t1_count == 50
    assert t2_count == 30

    t1_sees_t2 = await db.bookings.count_documents({"tenant_id": t1, "guest_id": {"$regex": f"guest-{t2}"}})
    assert t1_sees_t2 == 0

    await db.bookings.delete_many({"tenant_id": {"$in": [t1, t2]}})


async def test_tenant_update_isolation(db):
    """Updating tenant A's data should not affect tenant B."""
    ta = "isolation-a-" + uuid.uuid4().hex[:8]
    tb = "isolation-b-" + uuid.uuid4().hex[:8]

    for t in [ta, tb]:
        await db.rooms.insert_one({"id": f"room-{t}", "tenant_id": t, "room_number": "101", "status": "available"})

    await db.rooms.update_one({"tenant_id": ta}, {"$set": {"status": "occupied"}})

    room_a = await db.rooms.find_one({"tenant_id": ta}, {"_id": 0})
    room_b = await db.rooms.find_one({"tenant_id": tb}, {"_id": 0})

    assert room_a["status"] == "occupied"
    assert room_b["status"] == "available"

    await db.rooms.delete_many({"tenant_id": {"$in": [ta, tb]}})
