"""
E2E Test: Overbooking Prevention via Public API
================================================
Tests the room-night locking pattern through the public API endpoints.
Uses far-future dates (2050+) to avoid collisions with existing data.

Tests:
  1. Concurrent booking (10 parallel) → exactly 1 wins, 9 get 409
  2. Adjacent dates allowed (checkout day = next checkin day)
  3. Partial overlap blocked
  4. Full overlap blocked
  5. Cancel then rebook same dates → should succeed
  6. Different rooms same dates → both succeed
"""
import asyncio
import os
import random
import uuid

import pytest
import httpx

# Use public URL from environment
BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://hotelrunner-sync-2.preview.emergentagent.com").rstrip("/")
AUTH_CREDS = {"email": "demo@hotel.com", "password": "demo123"}

# Use unique year range per run to avoid collisions
_RUN_TAG = random.randint(2050, 2090)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def auth_headers():
    """Get auth token from public API."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post("/api/auth/login", json=AUTH_CREDS)
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        token = data.get("token") or data.get("access_token")
        assert token, f"No token in response: {data}"
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def test_room(auth_headers):
    """Get first available room for testing."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/api/pms/rooms", headers=auth_headers)
        assert resp.status_code == 200, f"Failed to get rooms: {resp.text}"
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
async def two_rooms(auth_headers):
    """Get two different rooms."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/api/pms/rooms", headers=auth_headers)
        assert resp.status_code == 200
        rooms = resp.json()
        if isinstance(rooms, dict) and "rooms" in rooms:
            rooms = rooms["rooms"]
        if len(rooms) < 2:
            pytest.skip("Need at least 2 rooms")
        return rooms[0], rooms[1]


@pytest.fixture(scope="module")
async def test_guest(auth_headers):
    """Get or create a test guest."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/api/pms/guests?limit=1", headers=auth_headers)
        assert resp.status_code == 200
        guests = resp.json()
        if isinstance(guests, dict) and "guests" in guests:
            guests = guests["guests"]
        if guests and len(guests) > 0:
            return guests[0]
    pytest.skip("No guest available for testing")


async def _book(client, auth_headers, room_id, guest_id, check_in, check_out, amount=500.0, name="Test"):
    """Helper to create a booking via quick-booking endpoint."""
    return await client.post(
        "/api/pms/quick-booking",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "guest_name": name,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "total_amount": amount,
            "guest_id": guest_id,
        },
    )


async def _cancel(auth_headers, booking_id):
    """Cancel a test booking via the PMS cancel endpoint."""
    if not booking_id:
        return
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
        # Use the proper pms-core cancel endpoint
        resp = await client.post(
            "/api/pms-core/cancel",
            headers=auth_headers,
            json={"booking_id": booking_id, "reason": "test_cleanup"},
        )
        if resp.status_code not in (200, 404):
            # Fallback: direct status update
            await client.put(
                f"/api/pms/bookings/{booking_id}",
                headers={**auth_headers, "Idempotency-Key": f"cancel-{booking_id}"},
                json={"status": "cancelled"},
            )


# ────────────────────────────────────────────────────────────
# Test 1: Concurrent booking — only 1 should win
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_concurrent_booking_only_one_wins(auth_headers, test_room, test_guest):
    """10 simultaneous requests for the same room/date. Only 1 succeeds."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]
    ci = f"{_RUN_TAG}-01-10T14:00:00+00:00"
    co = f"{_RUN_TAG}-01-12T11:00:00+00:00"

    async def attempt(client, i):
        return await _book(client, auth_headers, room_id, guest_id, ci, co, name=f"Concurrent {i}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        results = await asyncio.gather(*[attempt(client, i) for i in range(10)], return_exceptions=True)

    successes, conflicts, errors = [], [], []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif r.status_code == 200:
            successes.append(r.json())
        elif r.status_code == 409:
            conflicts.append(r.json())
        else:
            errors.append(f"status={r.status_code} body={r.text}")

    print(f"\nConcurrency Test: {len(successes)} success, {len(conflicts)} conflict, {len(errors)} error")

    # Exactly 1 should succeed
    assert len(successes) == 1, f"Expected 1 success but got {len(successes)}: {successes}"
    # The rest should be 409 conflicts
    assert len(conflicts) == 9, f"Expected 9 conflicts but got {len(conflicts)}"

    # Cleanup
    await _cancel(auth_headers, successes[0].get("id"))


# ────────────────────────────────────────────────────────────
# Test 2: Adjacent dates (check_out == next check_in) → ALLOWED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_adjacent_dates_allowed(auth_headers, test_room, test_guest):
    """Booking 1: day 1-3, Booking 2: day 3-5. NOT a conflict."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp1 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-02-10T14:00:00+00:00", f"{_RUN_TAG}-02-12T11:00:00+00:00",
                            name="Adjacent 1")
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        b1 = resp1.json().get("id")

        resp2 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-02-12T14:00:00+00:00", f"{_RUN_TAG}-02-14T11:00:00+00:00",
                            name="Adjacent 2")
        assert resp2.status_code == 200, f"Adjacent booking should succeed: {resp2.text}"
        b2 = resp2.json().get("id")

    # Cleanup
    await _cancel(auth_headers, b1)
    await _cancel(auth_headers, b2)


# ────────────────────────────────────────────────────────────
# Test 3: Partial overlap → BLOCKED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_partial_overlap_blocked(auth_headers, test_room, test_guest):
    """Booking 1: day 15-18. Booking 2: day 17-20. Overlap on 17-18."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp1 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-03-15T14:00:00+00:00", f"{_RUN_TAG}-03-18T11:00:00+00:00",
                            name="Overlap 1")
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        b1 = resp1.json().get("id")

        resp2 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-03-17T14:00:00+00:00", f"{_RUN_TAG}-03-20T11:00:00+00:00",
                            name="Overlap 2")
        assert resp2.status_code == 409, f"Overlapping booking should fail: status={resp2.status_code}"

    # Cleanup
    await _cancel(auth_headers, b1)


# ────────────────────────────────────────────────────────────
# Test 4: Full overlap → BLOCKED
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_full_overlap_blocked(auth_headers, test_room, test_guest):
    """Booking 1: day 20-25. Booking 2: day 21-23 (inside). Blocked."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp1 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-04-20T14:00:00+00:00", f"{_RUN_TAG}-04-25T11:00:00+00:00",
                            name="Full Overlap 1")
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        b1 = resp1.json().get("id")

        resp2 = await _book(client, auth_headers, room_id, guest_id,
                            f"{_RUN_TAG}-04-21T14:00:00+00:00", f"{_RUN_TAG}-04-23T11:00:00+00:00",
                            name="Full Overlap 2")
        assert resp2.status_code == 409, f"Full overlap should fail: status={resp2.status_code}"

    # Cleanup
    await _cancel(auth_headers, b1)


# ────────────────────────────────────────────────────────────
# Test 5: Cancelled booking doesn't block
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cancelled_booking_doesnt_block(auth_headers, test_room, test_guest):
    """Create booking, cancel it, then book same dates. Should succeed."""
    room_id = test_room["id"]
    guest_id = test_guest["id"]
    ci = f"{_RUN_TAG}-05-05T14:00:00+00:00"
    co = f"{_RUN_TAG}-05-07T11:00:00+00:00"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp1 = await _book(client, auth_headers, room_id, guest_id, ci, co, name="Cancel Test 1")
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        b1 = resp1.json().get("id")

    # Cancel the booking
    await _cancel(auth_headers, b1)

    # Wait a moment for cancellation to process
    await asyncio.sleep(0.5)

    # Now book the same dates again - should succeed
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp2 = await _book(client, auth_headers, room_id, guest_id, ci, co, name="Cancel Test 2")
        assert resp2.status_code == 200, f"Booking after cancellation should succeed: {resp2.text}"
        b2 = resp2.json().get("id")

    # Cleanup
    await _cancel(auth_headers, b2)


# ────────────────────────────────────────────────────────────
# Test 6: Different rooms — both succeed
# ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_different_rooms_both_succeed(auth_headers, two_rooms, test_guest):
    """Two different rooms for same dates — both should succeed."""
    room1, room2 = two_rooms
    guest_id = test_guest["id"]
    ci = f"{_RUN_TAG}-06-01T14:00:00+00:00"
    co = f"{_RUN_TAG}-06-03T11:00:00+00:00"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp1 = await _book(client, auth_headers, room1["id"], guest_id, ci, co, name="Room1 Guest")
        assert resp1.status_code == 200, f"Room1 booking failed: {resp1.text}"

        resp2 = await _book(client, auth_headers, room2["id"], guest_id, ci, co, name="Room2 Guest")
        assert resp2.status_code == 200, f"Room2 booking failed: {resp2.text}"

    # Cleanup
    await _cancel(auth_headers, resp1.json().get("id"))
    await _cancel(auth_headers, resp2.json().get("id"))
