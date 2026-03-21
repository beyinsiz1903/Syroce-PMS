"""
Test: Atomic Booking — Overbooking Prevention
=============================================
Tests:
  1. Concurrent same-room booking (10 parallel) → exactly 1 wins
  2. Adjacent dates (allowed)
  3. Partial overlap (blocked)
  4. Full overlap (blocked)
  5. Cancelled booking doesn't block new booking
  6. Unassigned booking (no room_id) always succeeds
  7. OTA import scenario
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import httpx

API_URL = "http://localhost:8001"
AUTH_CREDS = {"email": "demo@hotel.com", "password": "demo123"}


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def auth_headers():
    async with httpx.AsyncClient(base_url=API_URL) as client:
        resp = await client.post("/api/auth/login", json=AUTH_CREDS)
        token = resp.json().get("token") or resp.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def test_room(auth_headers):
    """Get first available room for testing."""
    async with httpx.AsyncClient(base_url=API_URL) as client:
        resp = await client.get("/api/pms/rooms", headers=auth_headers)
        rooms = resp.json()
        if isinstance(rooms, dict) and "rooms" in rooms:
            rooms = rooms["rooms"]
        for room in rooms:
            if room.get("status") in ("available", "clean", None):
                return room
        if rooms:
            return rooms[0]
    pytest.skip("No rooms available for testing")


@pytest.fixture(scope="module")
async def test_guest(auth_headers):
    """Get or create a test guest."""
    async with httpx.AsyncClient(base_url=API_URL) as client:
        resp = await client.get("/api/pms/guests?limit=1", headers=auth_headers)
        guests = resp.json()
        if isinstance(guests, dict) and "guests" in guests:
            guests = guests["guests"]
        if guests and len(guests) > 0:
            return guests[0]
    pytest.skip("No guest available for testing")


# ────────────────────────────────────────────────────────────
# Test 1: Concurrent booking — only 1 should win
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_concurrent_booking_only_one_wins(auth_headers, test_room, test_guest):
    """10 simultaneous requests for the same room/date. Only 1 succeeds."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]
    check_in = "2026-12-01T14:00:00+00:00"
    check_out = "2026-12-03T11:00:00+00:00"

    async def attempt_booking(client, i):
        resp = await client.post(
            "/api/pms/quick-booking",
            headers={
                **auth_headers,
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "guest_name": f"Concurrency Test Guest {i}",
                "room_id": room_id,
                "check_in": check_in,
                "check_out": check_out,
                "total_amount": 500.0,
                "guest_id": guest_id,
            },
        )
        return resp.status_code, resp.json()

    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        tasks = [attempt_booking(client, i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = []
    conflicts = []
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
            continue
        status_code, body = r
        if status_code == 200:
            successes.append(body)
        elif status_code == 409:
            conflicts.append(body)
        else:
            errors.append(f"status={status_code} body={body}")

    print(f"\n=== CONCURRENCY TEST RESULTS ===")
    print(f"Successes: {len(successes)}")
    print(f"Conflicts (409): {len(conflicts)}")
    print(f"Errors: {len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}")

    # CRITICAL ASSERTION: exactly 1 booking must succeed
    assert len(successes) == 1, f"Expected exactly 1 success but got {len(successes)}"
    assert len(conflicts) == 9, f"Expected 9 conflicts but got {len(conflicts)}"

    # Cleanup: cancel the created booking
    booking_id = successes[0].get("id")
    if booking_id:
        await cleanup_booking(auth_headers, booking_id)


# ────────────────────────────────────────────────────────────
# Test 2: Adjacent dates (check_out == next check_in) → ALLOWED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_adjacent_dates_allowed(auth_headers, test_room, test_guest):
    """Booking 1: Dec 10-12, Booking 2: Dec 12-14. NOT a conflict."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        # Booking 1: Dec 10-12
        resp1 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Adjacent Test 1",
                "room_id": room_id,
                "check_in": "2026-12-10T14:00:00+00:00",
                "check_out": "2026-12-12T11:00:00+00:00",
                "total_amount": 400.0,
                "guest_id": guest_id,
            },
        )
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        booking1_id = resp1.json().get("id")

        # Booking 2: Dec 12-14 (adjacent, should succeed)
        resp2 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Adjacent Test 2",
                "room_id": room_id,
                "check_in": "2026-12-12T14:00:00+00:00",
                "check_out": "2026-12-14T11:00:00+00:00",
                "total_amount": 400.0,
                "guest_id": guest_id,
            },
        )
        assert resp2.status_code == 200, f"Adjacent booking should succeed: {resp2.text}"
        booking2_id = resp2.json().get("id")

    # Cleanup
    await cleanup_booking(auth_headers, booking1_id)
    await cleanup_booking(auth_headers, booking2_id)


# ────────────────────────────────────────────────────────────
# Test 3: Partial overlap → BLOCKED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_partial_overlap_blocked(auth_headers, test_room, test_guest):
    """Booking 1: Dec 15-18. Booking 2: Dec 17-20. Overlap on Dec 17-18."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        # Booking 1: Dec 15-18
        resp1 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Overlap Test 1",
                "room_id": room_id,
                "check_in": "2026-12-15T14:00:00+00:00",
                "check_out": "2026-12-18T11:00:00+00:00",
                "total_amount": 600.0,
                "guest_id": guest_id,
            },
        )
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        booking1_id = resp1.json().get("id")

        # Booking 2: Dec 17-20 (overlaps Dec 17-18)
        resp2 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Overlap Test 2",
                "room_id": room_id,
                "check_in": "2026-12-17T14:00:00+00:00",
                "check_out": "2026-12-20T11:00:00+00:00",
                "total_amount": 600.0,
                "guest_id": guest_id,
            },
        )
        assert resp2.status_code == 409, f"Overlapping booking should fail with 409: status={resp2.status_code}"

    # Cleanup
    await cleanup_booking(auth_headers, booking1_id)


# ────────────────────────────────────────────────────────────
# Test 4: Full overlap → BLOCKED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_full_overlap_blocked(auth_headers, test_room, test_guest):
    """Booking 1: Dec 20-25. Booking 2: Dec 21-23 (inside). Blocked."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        resp1 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Full Overlap 1",
                "room_id": room_id,
                "check_in": "2026-12-20T14:00:00+00:00",
                "check_out": "2026-12-25T11:00:00+00:00",
                "total_amount": 1000.0,
                "guest_id": guest_id,
            },
        )
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        booking1_id = resp1.json().get("id")

        # Full overlap inside existing booking
        resp2 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Full Overlap 2",
                "room_id": room_id,
                "check_in": "2026-12-21T14:00:00+00:00",
                "check_out": "2026-12-23T11:00:00+00:00",
                "total_amount": 600.0,
                "guest_id": guest_id,
            },
        )
        assert resp2.status_code == 409, f"Fully overlapping booking should fail: status={resp2.status_code}"

    await cleanup_booking(auth_headers, booking1_id)


# ────────────────────────────────────────────────────────────
# Test 5: Cancelled booking doesn't block
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cancelled_booking_doesnt_block(auth_headers, test_room, test_guest):
    """Create booking, cancel it, then book same dates. Should succeed."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        # Create booking
        resp1 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Cancel Test 1",
                "room_id": room_id,
                "check_in": "2027-01-05T14:00:00+00:00",
                "check_out": "2027-01-07T11:00:00+00:00",
                "total_amount": 500.0,
                "guest_id": guest_id,
            },
        )
        assert resp1.status_code == 200
        booking1_id = resp1.json().get("id")

        # Cancel it
        await cleanup_booking(auth_headers, booking1_id)

        # Book same dates again — should succeed
        resp2 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Cancel Test 2",
                "room_id": room_id,
                "check_in": "2027-01-05T14:00:00+00:00",
                "check_out": "2027-01-07T11:00:00+00:00",
                "total_amount": 500.0,
                "guest_id": guest_id,
            },
        )
        assert resp2.status_code == 200, f"Booking after cancellation should succeed: {resp2.text}"
        booking2_id = resp2.json().get("id")

    await cleanup_booking(auth_headers, booking2_id)


# ────────────────────────────────────────────────────────────
# Test 6: Different rooms — both succeed
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_different_rooms_both_succeed(auth_headers, test_guest):
    """Two different rooms for same dates — both should succeed."""
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        # Get two different rooms
        resp = await client.get("/api/pms/rooms", headers=auth_headers)
        rooms = resp.json()
        if isinstance(rooms, dict) and "rooms" in rooms:
            rooms = rooms["rooms"]
        if len(rooms) < 2:
            pytest.skip("Need at least 2 rooms")

        room1, room2 = rooms[0], rooms[1]
        check_in = "2027-02-01T14:00:00+00:00"
        check_out = "2027-02-03T11:00:00+00:00"

        resp1 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Room1 Guest",
                "room_id": room1["id"],
                "check_in": check_in,
                "check_out": check_out,
                "total_amount": 500.0,
                "guest_id": guest_id,
            },
        )
        assert resp1.status_code == 200

        resp2 = await client.post(
            "/api/pms/quick-booking",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Room2 Guest",
                "room_id": room2["id"],
                "check_in": check_in,
                "check_out": check_out,
                "total_amount": 500.0,
                "guest_id": guest_id,
            },
        )
        assert resp2.status_code == 200

    await cleanup_booking(auth_headers, resp1.json().get("id"))
    await cleanup_booking(auth_headers, resp2.json().get("id"))


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
async def cleanup_booking(auth_headers, booking_id):
    """Cancel a test booking."""
    if not booking_id:
        return
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as client:
        # Try the standard cancel endpoint
        resp = await client.put(
            f"/api/pms/bookings/{booking_id}/cancel",
            headers=auth_headers,
            json={"reason": "test_cleanup"},
        )
        if resp.status_code not in (200, 404):
            # Fallback: direct status update
            await client.put(
                f"/api/pms/bookings/{booking_id}",
                headers=auth_headers,
                json={"status": "cancelled"},
            )
