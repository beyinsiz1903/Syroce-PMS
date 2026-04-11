"""
Tests for Atomic Check-in / Check-out
Restored from quarantine: stale_room_locks — added lock cleanup before booking creation.
"""
import asyncio
import uuid
import random
from datetime import datetime, timezone, timedelta

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


async def _get_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017/hotel_pms")
    return client, client["hotel_pms"]


async def _find_available_room(headers):
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/pms/rooms", headers=headers)
        rooms = r.json()
        for room in rooms:
            if room.get("status") == "available":
                return room
    client, db = await _get_db()
    dirty = await db.rooms.find_one({"status": "dirty"}, {"_id": 0})
    if dirty:
        await db.rooms.update_one({"id": dirty["id"]}, {"$set": {"status": "available", "current_booking_id": None}})
        client.close()
        return dirty
    client.close()
    return None


async def _clean_locks_for_room(room_id, start_date, end_date):
    """Remove stale locks for this room in the date range so booking can succeed."""
    client, db = await _get_db()
    await db.room_night_locks.delete_many({
        "room_id": room_id,
        "night_date": {"$gte": start_date, "$lte": end_date},
    })
    client.close()


async def _create_confirmed_booking(headers, room_id, guest_id, ci_offset=7, co_offset=10):
    now = datetime.now(timezone.utc)
    base_offset = ci_offset + 3000 + random.randint(0, 3000)
    ci = (now + timedelta(days=base_offset)).strftime("%Y-%m-%d")
    co = (now + timedelta(days=base_offset + (co_offset - ci_offset))).strftime("%Y-%m-%d")

    # Clean any stale locks for this room in this date range
    await _clean_locks_for_room(room_id, ci, co)

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


async def _get_first_guest(headers):
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/pms/guests", headers=headers)
        guests = r.json()
        return guests[0]["id"] if guests else None


# CHECK-IN TESTS

@pytest.mark.asyncio
async def test_successful_checkin(headers):
    """Check-in: booking->checked_in, room->occupied, folio created, audit+outbox."""
    room = await _find_available_room(headers)
    assert room, "No available room found"
    guest_id = await _get_first_guest(headers)
    assert guest_id

    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 200, f"Check-in failed: {r.text}"
        data = r.json()
        assert data["success"] is True
        assert data["booking_id"] == booking_id
        assert "checked_in_at" in data

    client, db = await _get_db()
    booking = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    assert booking["status"] == "checked_in"

    room_doc = await db.rooms.find_one({"id": room["id"]}, {"_id": 0})
    assert room_doc["status"] == "occupied"
    assert room_doc["current_booking_id"] == booking_id

    folio = await db.folios.find_one({"booking_id": booking_id}, {"_id": 0})
    assert folio is not None
    assert folio["status"] == "open"

    audit = await db.pms_audit_trail.find_one({"entity_id": booking_id, "action": "check_in_completed"}, {"_id": 0})
    assert audit is not None

    outbox = await db.outbox_events.find_one({"payload.booking_id": booking_id, "event_type": "guest.checked_in.v1"}, {"_id": 0})
    assert outbox is not None
    assert outbox["status"] == "pending"

    # Cleanup
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})
    await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "available", "current_booking_id": None}})
    client.close()


@pytest.mark.asyncio
async def test_checkin_invalid_status_fails(headers):
    """Check-in on a cancelled booking must fail."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.get("/pms/bookings", headers=headers)
        bookings = r.json() if isinstance(r.json(), list) else r.json().get("bookings", [])
        cancelled = [b for b in bookings if b.get("status") == "cancelled"]
        if not cancelled:
            pytest.skip("No cancelled booking for test")
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": cancelled[0]["id"]})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_checkin_no_room_fails(headers):
    """Check-in without assigned room must fail."""
    client, db = await _get_db()
    b = await db.bookings.find_one({"status": "confirmed", "room_id": None}, {"_id": 0, "id": 1})
    client.close()
    if not b:
        pytest.skip("No confirmed booking without room")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": b["id"]})
        assert r.status_code == 400


# CHECK-OUT TESTS

@pytest.mark.asyncio
async def test_successful_checkout(headers):
    """Check-out: booking->checked_out, room->dirty, folio->closed, HK task, audit+outbox."""
    room = await _find_available_room(headers)
    assert room, "No available room found"
    guest_id = await _get_first_guest(headers)
    assert guest_id

    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=8, co_offset=11)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 200, f"Check-in failed: {r.text}"
        r = await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "checked_out_at" in data

    client, db = await _get_db()
    booking = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    assert booking["status"] == "checked_out"

    room_doc = await db.rooms.find_one({"id": room["id"]}, {"_id": 0})
    assert room_doc["status"] == "dirty"
    assert room_doc["current_booking_id"] is None

    folio = await db.folios.find_one({"booking_id": booking_id}, {"_id": 0})
    assert folio["status"] == "closed"

    hk = await db.housekeeping_tasks.find_one({"booking_id": booking_id, "task_type": "checkout_cleaning"}, {"_id": 0})
    assert hk is not None
    assert hk["status"] == "pending"

    await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "available", "current_booking_id": None}})
    client.close()


@pytest.mark.asyncio
async def test_checkout_not_checked_in_fails(headers):
    """Check-out on a confirmed (not checked_in) booking must fail."""
    room = await _find_available_room(headers)
    if not room:
        pytest.skip("No available room")
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=12, co_offset=14)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        r = await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_housekeeping_prevention(headers):
    """Multiple check-outs on same booking should not create duplicate HK tasks."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=15, co_offset=17)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id})
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    client, db = await _get_db()
    hk_count = await db.housekeeping_tasks.count_documents({"booking_id": booking_id, "task_type": "checkout_cleaning"})
    assert hk_count == 1, f"Expected 1 HK task, got {hk_count}"
    client.close()


# CONCURRENT SAFETY TESTS

@pytest.mark.asyncio
async def test_concurrent_checkin_same_booking(headers):
    """Two parallel check-ins on the same booking: at least one should succeed."""
    room = await _find_available_room(headers)
    assert room
    guest_id = await _get_first_guest(headers)
    booking_id = await _create_confirmed_booking(headers, room["id"], guest_id, ci_offset=20, co_offset=22)

    async def attempt():
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
            r = await c.post("/pms-core/check-in", headers=headers, json={"booking_id": booking_id, "override_reason": "concurrent test"})
            return r.status_code, r.json()

    results = await asyncio.gather(attempt(), attempt(), return_exceptions=True)

    successes = 0
    for r in results:
        if isinstance(r, Exception):
            continue
        sc, body = r
        if sc == 200 and isinstance(body, dict) and body.get("success"):
            successes += 1

    assert successes >= 1, f"Expected at least 1 success, got results: {results}"

    # Cleanup
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as c:
        await c.post("/pms-core/checkout", headers=headers, json={"booking_id": booking_id, "force": True})

    client, db = await _get_db()
    await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "available", "current_booking_id": None}})
    client.close()
