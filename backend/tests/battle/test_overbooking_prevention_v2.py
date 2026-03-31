"""
Overbooking Prevention v2 — Sprint 1 Hardening Test Suite
============================================================
Tests all features from Sprint 1 of Overbooking Prevention v2:
  - Room Blocks REST API (OOO/OOS/Maintenance)
  - Room-night locking with full audit trail
  - Full-stay all-or-nothing atomicity
  - Optimistic locking on booking updates
  - Timeline audit events

Test Categories:
  1. Room Blocks API (POST/DELETE/GET)
  2. OOO blocks booking prevention
  3. OOO release then booking succeeds
  4. Timeline audit trail verification
  5. Concurrent booking race conditions
  6. Multi-night partial contention
  7. Cancel then rebook
  8. Adjacent dates (no false positive)
  9. Different rooms same dates
  10. Double cancel idempotency
  11. Idempotency key prevents duplicates
"""
import asyncio
import os
import random
import uuid

import httpx
import pytest

# Use public URL from environment
API_URL = os.environ.get("VITE_BACKEND_URL", "https://shadow-readiness.preview.emergentagent.com").rstrip("/")

# Use unique year range per test run to avoid date collisions
_RUN_TAG = random.randint(2100, 9999)

# ── Shared Auth ────────────────────────────────────────────────

_cached_headers = None
_cached_tenant_id = None


async def get_auth():
    """Returns (headers_dict, tenant_id)."""
    global _cached_headers, _cached_tenant_id
    if _cached_headers:
        return _cached_headers, _cached_tenant_id
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        data = resp.json()
        token = data.get("access_token") or data.get("token", "")
        _cached_tenant_id = data.get("user", {}).get("tenant_id", "")
        _cached_headers = {"Authorization": f"Bearer {token}"}
        return _cached_headers, _cached_tenant_id


async def get_test_room(client, headers):
    """Get first available room."""
    resp = await client.get(f"{API_URL}/api/pms/rooms", headers=headers)
    rooms = resp.json()
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms", rooms.get("data", []))
    for r in rooms:
        if r.get("status") in ("available", "clean", None):
            return r
    return rooms[0] if rooms else None


async def get_two_rooms(client, headers):
    """Get two different rooms."""
    resp = await client.get(f"{API_URL}/api/pms/rooms", headers=headers)
    rooms = resp.json()
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms", rooms.get("data", []))
    if len(rooms) < 2:
        return None, None
    return rooms[0], rooms[1]


async def get_test_guest(client, headers):
    """Get first guest."""
    resp = await client.get(f"{API_URL}/api/pms/guests?limit=1", headers=headers)
    guests = resp.json()
    if isinstance(guests, dict):
        guests = guests.get("guests", guests.get("data", []))
    return guests[0] if guests else None


async def book(client, headers, room_id, guest_id, check_in, check_out,
               amount=500.0, name="OverbookingTest", idempotency_key=None):
    """Create a booking via quick-booking."""
    idem_key = idempotency_key or str(uuid.uuid4())
    return await client.post(
        f"{API_URL}/api/pms/quick-booking",
        headers={**headers, "Idempotency-Key": idem_key},
        json={
            "guest_name": name,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "total_amount": amount,
            "guest_id": guest_id,
        },
    )


async def cancel_booking(client, headers, booking_id):
    """Cancel a booking via update endpoint."""
    if not booking_id:
        return None
    return await client.put(
        f"{API_URL}/api/pms/bookings/{booking_id}",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"status": "cancelled"},
    )


# ═══════════════════════════════════════════════════════════════
# TEST 1: Room Blocks API — POST (Apply OOO Block)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_post_apply_ooo():
    """POST /api/room-blocks — apply OOO block on a room."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-11-01"
        end = f"{_RUN_TAG}-11-05"

        # Apply OOO block
        resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO block for Sprint 1",
            },
        )
        assert resp.status_code == 200, f"POST /api/room-blocks failed: {resp.text}"
        data = resp.json()
        assert data.get("success") is True, f"OOO block not successful: {data}"
        assert len(data.get("nights_blocked", [])) > 0, "No nights blocked"

        # Cleanup: release the block
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo", "start_date": start, "end_date": end},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 2: Room Blocks API — DELETE (Release OOO Block)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_delete_release_ooo():
    """DELETE /api/room-blocks — release OOO block."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-11-10"
        end = f"{_RUN_TAG}-11-15"

        # Apply OOO block first
        await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO for release",
            },
        )

        # Release the block
        resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo", "start_date": start, "end_date": end},
        )
        assert resp.status_code == 200, f"DELETE /api/room-blocks failed: {resp.text}"
        data = resp.json()
        assert data.get("success") is True, f"OOO release not successful: {data}"


# ═══════════════════════════════════════════════════════════════
# TEST 3: Room Blocks API — GET (List Active Blocks)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_get_list():
    """GET /api/room-blocks — list active blocks."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-11-20"
        end = f"{_RUN_TAG}-11-25"

        # Apply OOO block
        await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO for listing",
            },
        )

        # List blocks
        resp = await client.get(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo"},
        )
        assert resp.status_code == 200, f"GET /api/room-blocks failed: {resp.text}"
        data = resp.json()
        assert "blocks" in data, f"Response missing 'blocks' key: {data}"
        assert data.get("count", 0) > 0, "No blocks found"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo", "start_date": start, "end_date": end},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 4: OOO Room Blocks Booking Attempt — Returns 409
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ooo_room_blocks_booking_returns_409():
    """OOO room blocks booking attempt: returns 409."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-12-01"
        end = f"{_RUN_TAG}-12-05"

        # Apply OOO block
        ooo_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO blocks booking",
            },
        )
        assert ooo_resp.status_code == 200

        # Try to book — must fail with 409
        ci = f"{_RUN_TAG}-12-02T14:00:00+00:00"
        co = f"{_RUN_TAG}-12-04T11:00:00+00:00"
        book_resp = await book(client, headers, room_id, guest["id"], ci, co, name="OOO_Block_Test")
        assert book_resp.status_code == 409, f"Booking OOO room should return 409, got {book_resp.status_code}"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo", "start_date": start, "end_date": end},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 5: OOO Release Then Booking — Succeeds After Block Removed
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ooo_release_then_booking_succeeds():
    """OOO release then booking: succeeds after block removed."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-12-10"
        end = f"{_RUN_TAG}-12-15"

        # Apply OOO block
        await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO release then book",
            },
        )

        # Release the block
        release_resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "ooo", "start_date": start, "end_date": end},
        )
        assert release_resp.status_code == 200

        # Now booking should succeed
        ci = f"{_RUN_TAG}-12-11T14:00:00+00:00"
        co = f"{_RUN_TAG}-12-14T11:00:00+00:00"
        book_resp = await book(client, headers, room_id, guest["id"], ci, co, name="After_OOO_Release")
        assert book_resp.status_code == 200, f"Booking after OOO release should succeed: {book_resp.text}"

        # Cleanup
        bid = book_resp.json().get("id")
        await cancel_booking(client, headers, bid)


# ═══════════════════════════════════════════════════════════════
# TEST 6: Timeline Audit Trail — lock_acquired and lock_released
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_timeline_audit_trail_lock_events():
    """Timeline audit trail: lock_acquired and lock_released events appear."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        ci = f"{_RUN_TAG}-12-20T14:00:00+00:00"
        co = f"{_RUN_TAG}-12-22T11:00:00+00:00"

        # Create booking
        resp = await book(client, headers, room["id"], guest["id"], ci, co, name="TimelineAuditTest")
        assert resp.status_code == 200
        booking_id = resp.json().get("id")

        # Wait for async timeline write
        await asyncio.sleep(0.5)

        # Check timeline for lock_acquired event
        timeline_resp = await client.get(
            f"{API_URL}/api/ops/timeline/booking/{booking_id}",
            headers=headers,
        )
        if timeline_resp.status_code == 200:
            tl_data = timeline_resp.json()
            if isinstance(tl_data, dict):
                events = tl_data.get("timeline", tl_data.get("events", tl_data.get("data", [])))
            else:
                events = tl_data
            lock_acquired = [e for e in events if e.get("stage") == "lock_acquired"]
            assert len(lock_acquired) >= 1, f"No lock_acquired event found for {booking_id}"

        # Cancel booking
        await cancel_booking(client, headers, booking_id)
        await asyncio.sleep(0.5)

        # Check for lock_released event
        timeline_resp2 = await client.get(
            f"{API_URL}/api/ops/timeline/booking/{booking_id}",
            headers=headers,
        )
        if timeline_resp2.status_code == 200:
            tl_data2 = timeline_resp2.json()
            if isinstance(tl_data2, dict):
                events2 = tl_data2.get("timeline", tl_data2.get("events", tl_data2.get("data", [])))
            else:
                events2 = tl_data2
            lock_released = [e for e in events2 if e.get("stage") == "lock_released"]
            assert len(lock_released) >= 1, f"No lock_released event found after cancel for {booking_id}"


# ═══════════════════════════════════════════════════════════════
# TEST 7: Concurrent Booking — Exactly 1 Succeeds, Others Get 409
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_booking_exactly_one_wins():
    """Concurrent booking for same room-night: exactly 1 succeeds, others get 409."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=30) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        ci = f"{_RUN_TAG}-01-10T14:00:00+00:00"
        co = f"{_RUN_TAG}-01-12T11:00:00+00:00"

        async def attempt(i):
            return await book(client, headers, room["id"], guest["id"], ci, co, name=f"ConcurrentRace{i}")

        results = await asyncio.gather(*[attempt(i) for i in range(10)], return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 200]
    conflicts = [r for r in results if not isinstance(r, Exception) and r.status_code == 409]

    assert len(successes) == 1, f"Expected 1 success but got {len(successes)}"
    assert len(conflicts) == 9, f"Expected 9 conflicts but got {len(conflicts)}"

    # Cleanup
    async with httpx.AsyncClient(timeout=15) as client:
        bid = successes[0].json().get("id")
        await cancel_booking(client, headers, bid)


# ═══════════════════════════════════════════════════════════════
# TEST 8: Multi-Night Partial Contention — All-or-Nothing
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_multi_night_partial_contention_all_or_nothing():
    """Multi-night partial contention: full-stay all-or-nothing (no partial locks left behind)."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        # Booking 1: nights 5, 6, 7
        resp1 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-05T14:00:00+00:00",
                           f"{_RUN_TAG}-02-08T11:00:00+00:00",
                           name="PartialContention1")
        assert resp1.status_code == 200
        b1_id = resp1.json().get("id")

        # Booking 2: nights 7, 8, 9 → conflict on night 7
        resp2 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-07T14:00:00+00:00",
                           f"{_RUN_TAG}-02-10T11:00:00+00:00",
                           name="PartialContention2")
        assert resp2.status_code == 409, f"Partial contention should be 409, got {resp2.status_code}"

        # Verify no partial locks: book night 8-9 should succeed
        resp3 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-08T14:00:00+00:00",
                           f"{_RUN_TAG}-02-10T11:00:00+00:00",
                           name="PartialVerify")
        assert resp3.status_code == 200, f"Night 8-9 should be free after partial rollback: {resp3.text}"

        # Cleanup
        await cancel_booking(client, headers, b1_id)
        b3_id = resp3.json().get("id")
        await cancel_booking(client, headers, b3_id)


# ═══════════════════════════════════════════════════════════════
# TEST 9: Cancel Then Rebook Same Dates — Succeeds
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cancel_then_rebook_same_dates_succeeds():
    """Cancel then rebook same dates: rebook succeeds after cancel releases locks."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        ci = f"{_RUN_TAG}-03-15T14:00:00+00:00"
        co = f"{_RUN_TAG}-03-18T11:00:00+00:00"

        # Book
        resp1 = await book(client, headers, room["id"], guest["id"], ci, co, name="CancelRebook1")
        assert resp1.status_code == 200
        b1_id = resp1.json().get("id")

        # Cancel
        cancel_resp = await cancel_booking(client, headers, b1_id)
        assert cancel_resp.status_code in (200, 201)

        # Rebook same dates — must succeed
        resp2 = await book(client, headers, room["id"], guest["id"], ci, co, name="CancelRebook2")
        assert resp2.status_code == 200, f"Rebook after cancel should succeed: {resp2.text}"

        # Cleanup
        b2_id = resp2.json().get("id")
        await cancel_booking(client, headers, b2_id)


# ═══════════════════════════════════════════════════════════════
# TEST 10: Adjacent Dates — Both Bookings Succeed
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adjacent_dates_both_succeed():
    """Adjacent dates (checkout=checkin): both bookings succeed (no false positive conflicts)."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        # B1: nights 20, 21
        resp1 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-08-20T14:00:00+00:00",
                           f"{_RUN_TAG}-08-22T11:00:00+00:00",
                           name="Adjacent1")
        assert resp1.status_code == 200
        b1 = resp1.json().get("id")

        # B2: nights 22, 23 (checkout day of B1 = checkin day of B2)
        resp2 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-08-22T14:00:00+00:00",
                           f"{_RUN_TAG}-08-24T11:00:00+00:00",
                           name="Adjacent2")
        assert resp2.status_code == 200, f"Adjacent booking should succeed: {resp2.text}"
        b2 = resp2.json().get("id")

        await cancel_booking(client, headers, b1)
        await cancel_booking(client, headers, b2)


# ═══════════════════════════════════════════════════════════════
# TEST 11: Different Rooms Same Dates — Both Succeed
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_different_rooms_same_dates_both_succeed():
    """Different rooms same dates: both bookings succeed."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        r1, r2 = await get_two_rooms(client, headers)
        guest = await get_test_guest(client, headers)
        if not r1 or not r2 or not guest:
            pytest.skip("Need 2 rooms + guest")

        ci = f"{_RUN_TAG}-09-01T14:00:00+00:00"
        co = f"{_RUN_TAG}-09-03T11:00:00+00:00"

        resp1 = await book(client, headers, r1["id"], guest["id"], ci, co, name="DiffRoom1")
        assert resp1.status_code == 200
        resp2 = await book(client, headers, r2["id"], guest["id"], ci, co, name="DiffRoom2")
        assert resp2.status_code == 200

        await cancel_booking(client, headers, resp1.json().get("id"))
        await cancel_booking(client, headers, resp2.json().get("id"))


# ═══════════════════════════════════════════════════════════════
# TEST 12: Double Cancel — Second Cancel Does Not Error
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_double_cancel_no_error():
    """Double cancel: second cancel does not error."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        ci = f"{_RUN_TAG}-07-01T14:00:00+00:00"
        co = f"{_RUN_TAG}-07-03T11:00:00+00:00"

        resp = await book(client, headers, room["id"], guest["id"], ci, co, name="DoubleCxl")
        assert resp.status_code == 200
        bid = resp.json().get("id")

        # First cancel
        c1 = await cancel_booking(client, headers, bid)
        assert c1.status_code in (200, 201)

        # Second cancel — must not crash
        c2 = await cancel_booking(client, headers, bid)
        assert c2.status_code in (200, 201, 400, 409)


# ═══════════════════════════════════════════════════════════════
# TEST 13: Idempotency Key — Same Key Does Not Create Duplicate
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_idempotency_key_no_duplicate():
    """Idempotency key: same key does not create duplicate bookings."""
    headers, _ = await get_auth()
    idem_key = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        ci = f"{_RUN_TAG}-04-01T14:00:00+00:00"
        co = f"{_RUN_TAG}-04-03T11:00:00+00:00"

        # First request
        resp1 = await book(client, headers, room["id"], guest["id"], ci, co,
                           name="IdemTest", idempotency_key=idem_key)
        assert resp1.status_code == 200

        # Second request with SAME idempotency key + same payload
        resp2 = await book(client, headers, room["id"], guest["id"], ci, co,
                           name="IdemTest", idempotency_key=idem_key)
        # Should return same result or 409 (already processed)
        assert resp2.status_code in (200, 409), f"Retry should return cached result or 409, got {resp2.status_code}"

        # If it returned 200, verify it's the SAME booking (not a duplicate)
        if resp2.status_code == 200:
            id1 = resp1.json().get("id")
            id2 = resp2.json().get("id")
            assert id1 == id2, f"Same idem key produced different booking IDs: {id1} vs {id2}"

        # Cleanup
        b1_id = resp1.json().get("id")
        await cancel_booking(client, headers, b1_id)


# ═══════════════════════════════════════════════════════════════
# TEST 14: OOS Block Type Works
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_oos_block_type_works():
    """OOS (Out of Service) block type works correctly."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-12-25"
        end = f"{_RUN_TAG}-12-30"

        # Apply OOS block
        oos_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "oos",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOS block",
            },
        )
        assert oos_resp.status_code == 200
        assert oos_resp.json().get("success") is True

        # Try to book — must fail with 409
        ci = f"{_RUN_TAG}-12-26T14:00:00+00:00"
        co = f"{_RUN_TAG}-12-28T11:00:00+00:00"
        book_resp = await book(client, headers, room_id, guest["id"], ci, co, name="OOS_Block_Test")
        assert book_resp.status_code == 409, f"Booking OOS room should return 409, got {book_resp.status_code}"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "oos", "start_date": start, "end_date": end},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 15: Maintenance Block Type Works
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_maintenance_block_type_works():
    """Maintenance block type works correctly."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        room_id = room["id"]
        start = f"{_RUN_TAG}-12-05"
        end = f"{_RUN_TAG}-12-08"

        # Apply maintenance block
        maint_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "maintenance",
                "start_date": start,
                "end_date": end,
                "reason": "Test maintenance block",
            },
        )
        assert maint_resp.status_code == 200
        assert maint_resp.json().get("success") is True

        # Try to book — must fail with 409
        ci = f"{_RUN_TAG}-12-06T14:00:00+00:00"
        co = f"{_RUN_TAG}-12-07T11:00:00+00:00"
        book_resp = await book(client, headers, room_id, guest["id"], ci, co, name="Maint_Block_Test")
        assert book_resp.status_code == 409, f"Booking maintenance room should return 409, got {book_resp.status_code}"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room_id, "block_type": "maintenance", "start_date": start, "end_date": end},
        )
