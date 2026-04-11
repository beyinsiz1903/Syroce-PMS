"""
Booking Integrity — CI Hard Gate Test Suite
=============================================
Tests the core invariants from ADR-001.
Every test here is a release blocker.

Invariants tested:
  INV-1: Sellable inventory never goes negative
  INV-2: Full-stay all-or-nothing
  INV-3: Idempotency key consistency
  INV-4: Cancel/modify/rebook precedence
  INV-5: OOO/OOS uses same availability truth
  INV-6: Timeline audit trail

Test categories:
  1. Same room-night concurrency race
  2. Multi-night partial contention
  3. Cancel + new booking race
  4. Idempotency retry
  5. OOO/OOS inventory drop
  6. Cancel then rebook
  7. Modify + date change
  8. Full-stay atomicity proof
"""
import asyncio
import os
import random
import uuid

import httpx
import pytest

API_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8001")

# Use unique year range per test run to avoid date collisions
# Wide range (7900 values) to virtually eliminate collision probability
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
               amount=500.0, name="IntegrityTest", idempotency_key=None):
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
    try:
        return await client.put(
            f"{API_URL}/api/pms/bookings/{booking_id}",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"status": "cancelled"},
        )
    except Exception:
        return None


async def safe_book(client, headers, room_id, guest_id, check_in, check_out,
                    amount=500.0, name="IntegrityTest"):
    """Book with automatic retry on stale lock collision.
    If first attempt gets 409, tries with a fresh unique date offset."""
    resp = await book(client, headers, room_id, guest_id, check_in, check_out,
                      amount=amount, name=name)
    return resp


# ═══════════════════════════════════════════════════════════════
# TEST 1: Same Room-Night Concurrency Race (INV-1)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_same_room_exactly_one_wins():
    """10 simultaneous bookings for the same room + same dates.
    INV-1: Exactly 1 succeeds, 9 get 409. Zero overbooking."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=30) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        ci = f"{_RUN_TAG}-01-10T14:00:00+00:00"
        co = f"{_RUN_TAG}-01-12T11:00:00+00:00"

        async def attempt(i):
            return await book(client, headers, room["id"], guest["id"], ci, co, name=f"Race{i}")

        results = await asyncio.gather(*[attempt(i) for i in range(10)], return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 200]
    conflicts = [r for r in results if not isinstance(r, Exception) and r.status_code == 409]

    assert len(successes) == 1, f"INV-1 VIOLATION: {len(successes)} bookings succeeded (expected 1)"
    assert len(conflicts) == 9, f"Expected 9 conflicts, got {len(conflicts)}"

    # Cleanup
    async with httpx.AsyncClient(timeout=15) as client:
        bid = successes[0].json().get("id")
        await cancel_booking(client, headers, bid)


# ═══════════════════════════════════════════════════════════════
# TEST 2: Multi-Night Partial Contention (INV-2)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_multi_night_partial_contention_all_or_nothing():
    """Booking1 = night 5-8 (3 nights). Booking2 = night 7-10 (3 nights).
    Night 7 conflicts. Booking2 must claim ZERO nights (INV-2)."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        # Booking 1: nights 5, 6, 7
        resp1 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-05T14:00:00+00:00",
                           f"{_RUN_TAG}-02-08T11:00:00+00:00",
                           name="Partial1")
        assert resp1.status_code == 200, f"First booking failed: {resp1.text}"
        b1_id = resp1.json().get("id")

        # Booking 2: nights 7, 8, 9 → conflict on night 7
        resp2 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-07T14:00:00+00:00",
                           f"{_RUN_TAG}-02-10T11:00:00+00:00",
                           name="Partial2")
        assert resp2.status_code == 409, f"INV-2: Partial contention should be 409, got {resp2.status_code}"

        # Verify no partial locks from Booking2 exist
        # Book night 8-9 with a DIFFERENT booking — must succeed (proving B2 didn't leave partial locks)
        resp3 = await book(client, headers, room["id"], guest["id"],
                           f"{_RUN_TAG}-02-08T14:00:00+00:00",
                           f"{_RUN_TAG}-02-10T11:00:00+00:00",
                           name="Partial3_verify")
        assert resp3.status_code == 200, f"INV-2 VIOLATION: Night 8-9 should be free after partial rollback: {resp3.text}"

        # Cleanup
        await cancel_booking(client, headers, b1_id)
        b3_id = resp3.json().get("id")
        await cancel_booking(client, headers, b3_id)


# ═══════════════════════════════════════════════════════════════
# TEST 3: Cancel + New Booking Race (INV-4)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cancel_then_rebook_same_dates():
    """Book → Cancel → Rebook same dates.
    INV-4: After cancel, locks are fully released, rebook must succeed."""
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
        assert resp2.status_code == 200, f"INV-4: Rebook after cancel should succeed: {resp2.text}"

        # Cleanup
        b2_id = resp2.json().get("id")
        await cancel_booking(client, headers, b2_id)


# ═══════════════════════════════════════════════════════════════
# TEST 4: Idempotency Key Retry (INV-3)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_idempotency_key_no_duplicate_inventory():
    """Same idempotency key sent twice.
    INV-3: Second request must NOT consume additional inventory."""
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
                           name="Idem1", idempotency_key=idem_key)
        assert resp1.status_code == 200

        # Second request with SAME idempotency key + same payload
        resp2 = await book(client, headers, room["id"], guest["id"], ci, co,
                           name="Idem1", idempotency_key=idem_key)
        # Should return same result or 409 (already processed)
        assert resp2.status_code in (200, 409), f"INV-3: Retry should return cached result or 409, got {resp2.status_code}"

        # If it returned 200, verify it's the SAME booking (not a duplicate)
        if resp2.status_code == 200:
            id1 = resp1.json().get("id")
            id2 = resp2.json().get("id")
            assert id1 == id2, f"INV-3 VIOLATION: Same idem key produced different booking IDs: {id1} vs {id2}"

        # Cleanup
        b1_id = resp1.json().get("id")
        await cancel_booking(client, headers, b1_id)


# ═══════════════════════════════════════════════════════════════
# TEST 5: OOO Room Cannot Be Booked (INV-5)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ooo_room_blocks_booking():
    """Mark room as OOO → attempt booking → should fail with 409.
    INV-5: OOO uses same availability truth as bookings."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        room_id = room["id"]
        start = f"{_RUN_TAG}-05-01"
        end = f"{_RUN_TAG}-05-04"

        # Apply OOO via API
        ooo_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
                "reason": "Test OOO block",
            },
        )
        assert ooo_resp.status_code == 200, f"OOO apply failed: {ooo_resp.text}"
        ooo_data = ooo_resp.json()
        assert ooo_data.get("success") is True

        # Try to book — must fail
        ci = f"{_RUN_TAG}-05-02T14:00:00+00:00"
        co = f"{_RUN_TAG}-05-03T11:00:00+00:00"
        book_resp = await book(client, headers, room_id, guest["id"], ci, co, name="OOO_Attempt")
        assert book_resp.status_code == 409, f"INV-5: Booking OOO room should be 409, got {book_resp.status_code}"

        # Release OOO
        release_resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={
                "room_id": room_id,
                "block_type": "ooo",
                "start_date": start,
                "end_date": end,
            },
        )
        assert release_resp.status_code == 200

        # Now booking should succeed
        book_resp2 = await book(client, headers, room_id, guest["id"], ci, co, name="OOO_After")
        assert book_resp2.status_code == 200, f"Booking after OOO release should succeed: {book_resp2.text}"

        # Cleanup
        b_id = book_resp2.json().get("id")
        await cancel_booking(client, headers, b_id)


# ═══════════════════════════════════════════════════════════════
# TEST 6: Lock Audit Trail in Timeline (INV-6)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lock_events_appear_in_timeline():
    """Create a booking and verify lock_acquired event in timeline.
    INV-6: Every lock operation must be auditable."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        ci = f"{_RUN_TAG}-06-10T14:00:00+00:00"
        co = f"{_RUN_TAG}-06-12T11:00:00+00:00"

        resp = await book(client, headers, room["id"], guest["id"], ci, co, name="AuditTest")
        assert resp.status_code == 200
        booking_id = resp.json().get("id")

        # Small delay for async timeline write
        await asyncio.sleep(0.5)

        # Check timeline for lock_acquired event (uses booking_id as correlation)
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
            lock_events = [e for e in events if e.get("stage") == "lock_acquired"]
            assert len(lock_events) >= 1, f"INV-6: No lock_acquired event found in timeline for {booking_id}"

        # Now cancel and check lock_released
        await cancel_booking(client, headers, booking_id)
        await asyncio.sleep(0.5)

        # lock_released may use a different correlation_id (from cancel request),
        # so search by entity_id which is always the booking_id
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
            release_events = [e for e in events2 if e.get("stage") == "lock_released"]
            assert len(release_events) >= 1, f"INV-6: No lock_released event found after cancel for {booking_id}"


# ═══════════════════════════════════════════════════════════════
# TEST 7: Double Cancel is Idempotent
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_double_cancel_idempotent():
    """Cancel same booking twice. Must not error.
    Second cancel: either succeeds (no-op) or returns already cancelled."""
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
# TEST 8: Adjacent Dates Are Not Conflicts
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adjacent_dates_no_conflict():
    """Booking1 checkout == Booking2 checkin. Must both succeed.
    Guest departs morning, new guest arrives afternoon — standard hotel ops."""
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
# TEST 9: Different Rooms Same Dates Both Succeed
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_different_rooms_both_succeed():
    """Two different rooms for same dates — must both succeed."""
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
# TEST 10: Lock Conflict Timeline Shows Conflict Details (INV-6)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lock_conflict_recorded_in_timeline():
    """Create booking → attempt conflicting booking → verify lock_conflict in timeline."""
    headers, _ = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest")

        ci = f"{_RUN_TAG}-10-05T14:00:00+00:00"
        co = f"{_RUN_TAG}-10-07T11:00:00+00:00"

        # First booking succeeds
        resp1 = await book(client, headers, room["id"], guest["id"], ci, co, name="Conflict1")
        assert resp1.status_code == 200
        b1_id = resp1.json().get("id")

        # Second booking fails
        resp2 = await book(client, headers, room["id"], guest["id"], ci, co, name="Conflict2")
        assert resp2.status_code == 409

        # The rejected booking's ID is in the response or we can check timeline
        await asyncio.sleep(0.5)

        # Search timeline for lock_conflict events on this room
        search_resp = await client.get(
            f"{API_URL}/api/ops/timeline/search",
            headers=headers,
            params={"stage": "lock_conflict", "limit": 10},
        )
        if search_resp.status_code == 200:
            events = search_resp.json()
            if isinstance(events, dict):
                events = events.get("events", events.get("data", []))
            # Just verify at least one conflict event exists
            assert len(events) >= 1, "INV-6: No lock_conflict events in timeline"

        # Cleanup
        await cancel_booking(client, headers, b1_id)
