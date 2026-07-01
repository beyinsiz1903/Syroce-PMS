# QUARANTINED: 2026-03-24
# REASON: Cascading stale room-night locks. Tests are interdependent - earlier tests
#         create bookings that later tests depend on (checkin/checkout/audit).
#         Root cause: Room not available errors from leftover room_night_locks.
#         8/14 tests fail (3 directly + 5 cascading). Fix: Add cleanup fixtures.
# ORIGINAL: tests/test_day2_hardening.py
# CATEGORY: stale_room_locks

"""
Day 2-3 Hardening Tests
========================
Tests for:
1. Atomic check-in/check-out via API endpoints
2. Walk-in with atomic check-in
3. Early check-in with atomic transaction
4. Group booking check-in/check-out all
5. Mobile staff quick check-in
6. Housekeeping task deduplication
7. Deep health check endpoint
8. Performance indexes verification
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import random

import pytest
import httpx

BASE_URL = "http://localhost:8001/api"
AUTH_CREDS = {"email": "demo@hotel.com", "password": "demo123"}


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def token(event_loop):
    async def _get():
        async with httpx.AsyncClient(base_url=BASE_URL) as c:
            r = await c.post("/auth/login", json=AUTH_CREDS)
            return r.json()["access_token"]
    return event_loop.run_until_complete(_get())


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _idem():
    return {"Idempotency-Key": str(uuid.uuid4())}


# ── Helpers ──

async def _find_available_room(headers):
    """Find an available room or reset a dirty one."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/pms/rooms", headers=headers)
        rooms = r.json()
        for room in rooms:
            if room.get("status") == "available":
                return room
    # Fallback: reset a dirty room
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]
    dirty = await db.rooms.find_one({"status": "dirty"}, {"_id": 0})
    if dirty:
        await db.rooms.update_one({"id": dirty["id"]}, {"$set": {"status": "available", "current_booking_id": None}})
        client.close()
        return dirty
    client.close()
    return None


async def _get_first_guest(headers):
    """Get first guest from the system."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/pms/guests", headers=headers)
        guests = r.json()
        return guests[0]["id"] if guests else None


async def _create_confirmed_booking(headers, room_id, guest_id, ci_offset=7, co_offset=10):
    """Create a confirmed booking with dates far in the future."""
    now = datetime.now(timezone.utc)
    base_offset = ci_offset + 300 + random.randint(0, 500)
    ci = (now + timedelta(days=base_offset)).strftime("%Y-%m-%d")
    co = (now + timedelta(days=base_offset + (co_offset - ci_offset))).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms/bookings", headers={**headers, **_idem()}, json={
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": ci,
            "check_out": co,
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "total_amount": 300,
            "status": "confirmed",
            "channel": "direct",
        })
        assert r.status_code == 200, f"Booking create failed: {r.text}"
        return r.json()["id"]


async def _cleanup_room(room_id):
    """Reset room to available."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]
    await db.rooms.update_one({"id": room_id}, {"$set": {"status": "available", "current_booking_id": None}})
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  1. API ENDPOINT TESTS: /api/pms-core/check-in and /checkout
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_api_checkin_endpoint(headers):
    """Test POST /api/pms-core/check-in endpoint."""
    room = await _find_available_room(headers)
    assert room, "No available room"
    guest_id = await _get_first_guest(headers)
    assert guest_id

    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=30, co_offset=33)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 200, f"Check-in failed: {r.text}"
        data = r.json()
        assert data["success"] is True
        assert data["booking_id"] == booking_id
        assert "checked_in_at" in data

        # Cleanup: checkout
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    await _cleanup_room(room["id"])


@pytest.mark.asyncio
async def test_api_checkout_endpoint(headers):
    """Test POST /api/pms-core/checkout endpoint."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=35, co_offset=38)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        # Check in first
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 200

        # Check out
        r = await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "checked_out_at" in data

    await _cleanup_room(room["id"])


@pytest.mark.asyncio
async def test_checkin_invalid_status_returns_400(headers):
    """Check-in on cancelled booking returns 400."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]
    cancelled = await db.bookings.find_one({"status": "cancelled"}, {"_id": 0, "id": 1})
    client.close()

    if not cancelled:
        pytest.skip("No cancelled booking for test")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": cancelled["id"]})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_checkout_not_checked_in_returns_400(headers):
    """Check-out on confirmed (not checked_in) booking returns 400."""
    room = await _find_available_room(headers)
    if not room:
        pytest.skip("No available room")
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=40, co_offset=42)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  2. WALK-IN WITH ATOMIC CHECK-IN
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_walkin_creates_booking_and_checks_in(headers):
    """Test POST /api/pms-core/walk-in creates booking and checks in atomically."""
    room = await _find_available_room(headers)
    assert room, "No available room"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/walk-in", headers=headers, json={
            "room_id": room["id"],
            "nights": 2,
            "rate": 150.0,
            "guest_name": f"Walk-in Test {uuid.uuid4().hex[:6]}",
            "guest_phone": "555-1234",
            "guest_email": f"walkin-{uuid.uuid4().hex[:6]}@test.dev",
            "adults": 1,
        })
        assert r.status_code == 200, f"Walk-in failed: {r.text}"
        data = r.json()
        assert data["success"] is True
        assert "booking_id" in data
        assert data["room_number"] == room["room_number"]

        # Verify booking is checked_in
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
        db = client["hotel_pms"]
        booking = await db.bookings.find_one({"id": data["booking_id"]}, {"_id": 0})
        assert booking["status"] == "checked_in"

        # Cleanup
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": data["booking_id"], "force": True})
        client.close()

    await _cleanup_room(room["id"])


# ═══════════════════════════════════════════════════════════════════
#  3. EARLY CHECK-IN WITH ATOMIC TRANSACTION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_early_checkin_uses_atomic_transaction(headers):
    """Test POST /api/pms/reservations/{id}/early-checkin uses atomic check-in."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=45, co_offset=48)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post(f"/pms/reservations/{booking_id}/early-checkin", headers=headers, json={
            "checkin_time": datetime.now(timezone.utc).isoformat(),
            "extra_charge": 50.0,
        })
        assert r.status_code == 200, f"Early check-in failed: {r.text}"
        data = r.json()
        assert data["success"] is True

        # Verify booking is checked_in
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
        db = client["hotel_pms"]
        booking = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
        assert booking["status"] == "checked_in"
        assert booking.get("early_checkin") is True

        # Cleanup
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})
        client.close()

    await _cleanup_room(room["id"])


# ═══════════════════════════════════════════════════════════════════
#  4. GROUP BOOKING CHECK-IN/CHECK-OUT ALL
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_group_checkin_all(headers):
    """Test POST /api/pms/group-bookings/{id}/check-in-all uses atomic check-in."""
    # Create 2 bookings and a group
    room1 = await _find_available_room(headers)
    assert room1
    guest_id = await _get_first_guest(headers)
    booking1 = await _create_confirmed_booking(headers, room1["id"], guest_id, ci_offset=50, co_offset=53)

    room2 = await _find_available_room(headers)
    if not room2 or room2["id"] == room1["id"]:
        # Reset room1 and skip
        await _cleanup_room(room1["id"])
        pytest.skip("Need 2 available rooms for group test")

    booking2 = await _create_confirmed_booking(headers, room2["id"], guest_id, ci_offset=50, co_offset=53)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        # Create group
        r = await c.post("/pms/group-bookings", headers=headers, json={
            "group_name": f"Test Group {uuid.uuid4().hex[:6]}",
            "booking_ids": [booking1, booking2],
        })
        assert r.status_code == 200
        group_id = r.json()["group"]["id"]

        # Check-in all
        r = await c.post(f"/pms/group-bookings/{group_id}/check-in-all", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["checked_in_count"] == 2

        # Verify both bookings are checked_in
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
        db = client["hotel_pms"]
        b1 = await db.bookings.find_one({"id": booking1}, {"_id": 0})
        b2 = await db.bookings.find_one({"id": booking2}, {"_id": 0})
        assert b1["status"] == "checked_in"
        assert b2["status"] == "checked_in"

        # Check-out all
        r = await c.post(f"/pms/group-bookings/{group_id}/check-out-all", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["checked_out_count"] == 2

        client.close()

    await _cleanup_room(room1["id"])
    await _cleanup_room(room2["id"])


# ═══════════════════════════════════════════════════════════════════
#  5. HOUSEKEEPING TASK DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_housekeeping_task_deduplication(headers):
    """Verify only one HK task per booking on checkout."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=55, co_offset=58)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        # Check in
        await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        # Check out
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    # Verify only 1 HK task
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]
    hk_count = await db.housekeeping_tasks.count_documents({
        "booking_id": booking_id,
        "task_type": "checkout_cleaning",
    })
    assert hk_count == 1, f"Expected 1 HK task, got {hk_count}"
    client.close()

    await _cleanup_room(room["id"])


# ═══════════════════════════════════════════════════════════════════
#  6. DEEP HEALTH CHECK ENDPOINT
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_deep_health_check():
    """Test GET /health/deep returns mongo/redis/outbox/night_audit status."""
    # Note: /health/deep is only accessible internally (localhost:8001)
    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=10) as c:
        r = await c.get("/health/deep")
        # May return 200 or 503 depending on Redis
        assert r.status_code in [200, 503]
        data = r.json()
        assert "mongo" in data
        assert "redis" in data
        assert "outbox" in data
        assert "night_audit" in data
        assert "overall" in data
        # Mongo should be ok
        assert data["mongo"]["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════
#  7. PERFORMANCE INDEXES VERIFICATION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_performance_indexes_exist():
    """Verify performance indexes are created on startup."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]

    # Check bookings indexes
    booking_indexes = await db.bookings.index_information()
    assert any("tenant_id" in str(idx) and "status" in str(idx) for idx in booking_indexes.values()), \
        "Missing booking tenant_id+status index"

    # Check rooms indexes
    room_indexes = await db.rooms.index_information()
    assert any("tenant_id" in str(idx) for idx in room_indexes.values()), \
        "Missing room tenant_id index"

    # Check folios indexes
    folio_indexes = await db.folios.index_information()
    assert any("tenant_id" in str(idx) and "booking_id" in str(idx) for idx in folio_indexes.values()), \
        "Missing folio tenant_id+booking_id index"

    # Check outbox_events indexes
    outbox_indexes = await db.outbox_events.index_information()
    assert any("status" in str(idx) for idx in outbox_indexes.values()), \
        "Missing outbox status index"

    # Check housekeeping_tasks indexes
    hk_indexes = await db.housekeeping_tasks.index_information()
    assert any("tenant_id" in str(idx) for idx in hk_indexes.values()), \
        "Missing housekeeping tenant_id index"

    client.close()


# ═══════════════════════════════════════════════════════════════════
#  8. CHECKOUT PREVIEW ENDPOINT
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_checkout_preview(headers):
    """Test GET /api/pms-core/checkout-preview/{booking_id}."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=60, co_offset=63)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        # Check in first
        await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})

        # Get checkout preview
        r = await c.get(f"/pms-core/checkout-preview/{booking_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["booking_id"] == booking_id
        assert "folios" in data
        assert "balance_due" in data
        assert "can_checkout" in data

        # Cleanup
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    await _cleanup_room(room["id"])


# ═══════════════════════════════════════════════════════════════════
#  9. BLOCKED ROOM CHECK-IN FAILS
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_checkin_blocked_room_fails(headers):
    """Check-in on a room with out_of_order status should fail."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]

    # Find a room and set it to out_of_order
    room = await db.rooms.find_one({"status": "available"}, {"_id": 0})
    if not room:
        client.close()
        pytest.skip("No available room")

    original_status = room["status"]
    await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "out_of_order"}})

    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=65, co_offset=68)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 400, f"Expected 400 for blocked room, got {r.status_code}"

    # Restore room status
    await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": original_status}})
    client.close()


# ═══════════════════════════════════════════════════════════════════
#  10. AUDIT TRAIL VERIFICATION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_audit_trail_created_on_checkin_checkout(headers):
    """Verify audit trail entries are created for check-in and check-out."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=70, co_offset=73)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        # Check in
        await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        # Check out
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    # Verify audit entries
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]

    checkin_audit = await db.pms_audit_trail.find_one({
        "entity_id": booking_id,
        "action": "check_in_completed",
    }, {"_id": 0})
    assert checkin_audit is not None, "Missing check-in audit entry"

    checkout_audit = await db.pms_audit_trail.find_one({
        "entity_id": booking_id,
        "action": "check_out_completed",
    }, {"_id": 0})
    assert checkout_audit is not None, "Missing check-out audit entry"

    client.close()
    await _cleanup_room(room["id"])


# ═══════════════════════════════════════════════════════════════════
#  11. OUTBOX EVENT VERIFICATION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_outbox_events_created(headers):
    """Verify outbox events are created for check-in and check-out."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=75, co_offset=78)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    db = client["hotel_pms"]

    checkin_event = await db.outbox_events.find_one({
        "payload.booking_id": booking_id,
        "event_type": "guest.checked_in.v1",
    }, {"_id": 0})
    assert checkin_event is not None, "Missing check-in outbox event"
    assert checkin_event["status"] == "pending"

    checkout_event = await db.outbox_events.find_one({
        "payload.booking_id": booking_id,
        "event_type": "guest.checked_out.v1",
    }, {"_id": 0})
    assert checkout_event is not None, "Missing check-out outbox event"

    client.close()
    await _cleanup_room(room["id"])
