"""
Sprint 2 — Booking Holds REST API Tests
=========================================
Tests the booking holds REST API endpoints:
  - POST /api/booking-holds — Create a hold on room nights with TTL
  - POST /api/booking-holds/confirm — Upgrade hold to confirmed booking lock
  - DELETE /api/booking-holds?booking_id=X — Release a hold manually
  - GET /api/booking-holds/status?booking_id=X — Get hold status
  - POST /api/booking-holds/sweep — Manual trigger expired hold cleanup

Also tests PMS room-blocks INV-5 integration:
  - POST /api/pms/room-blocks — Should also write to room_night_locks
  - POST /api/pms/room-blocks/{id}/cancel — Should also release room_night_locks
"""
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

API_URL = os.environ.get("VITE_BACKEND_URL", "https://tenant-pms-v2.preview.emergentagent.com")

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


async def get_test_guest(client, headers):
    """Get first guest."""
    resp = await client.get(f"{API_URL}/api/pms/guests?limit=1", headers=headers)
    guests = resp.json()
    if isinstance(guests, dict):
        guests = guests.get("guests", guests.get("data", []))
    return guests[0] if guests else None


# ═══════════════════════════════════════════════════════════════
# TEST 1: Create Booking Hold via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_booking_hold_api():
    """POST /api/booking-holds should create a hold with TTL."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        booking_id = f"hold-api-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-01-10"
        check_out = f"{_RUN_TAG}-01-12"

        resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
                "ttl_minutes": 10,
            },
        )

        assert resp.status_code == 200, f"Create hold failed: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert len(data.get("nights_held", [])) == 2
        assert "hold_expires_at" in data
        assert data.get("ttl_minutes") == 10

        # Cleanup: release the hold
        await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id, "reason": "test_cleanup"},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 2: Get Hold Status via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_hold_status_api():
    """GET /api/booking-holds/status should return hold details."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        booking_id = f"hold-status-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-02-10"
        check_out = f"{_RUN_TAG}-02-13"

        # Create hold
        create_resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert create_resp.status_code == 200

        # Get status
        status_resp = await client.get(
            f"{API_URL}/api/booking-holds/status",
            headers=headers,
            params={"booking_id": booking_id},
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data.get("has_hold") is True
        assert status_data.get("booking_id") == booking_id
        assert status_data.get("room_id") == room["id"]
        assert status_data.get("night_count") == 3
        assert "hold_expires_at" in status_data

        # Cleanup
        await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 3: Confirm Hold via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_confirm_hold_api():
    """POST /api/booking-holds/confirm should upgrade hold to booking lock."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        booking_id = f"hold-confirm-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-03-10"
        check_out = f"{_RUN_TAG}-03-12"

        # Create hold
        create_resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert create_resp.status_code == 200

        # Confirm hold
        confirm_resp = await client.post(
            f"{API_URL}/api/booking-holds/confirm",
            headers=headers,
            json={"booking_id": booking_id},
        )
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        assert confirm_data.get("success") is True
        assert confirm_data.get("confirmed_count") == 2

        # Verify hold status shows no hold (it's now a booking)
        status_resp = await client.get(
            f"{API_URL}/api/booking-holds/status",
            headers=headers,
            params={"booking_id": booking_id},
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data.get("has_hold") is False  # No longer a hold


# ═══════════════════════════════════════════════════════════════
# TEST 4: Release Hold via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_release_hold_api():
    """DELETE /api/booking-holds should release the hold."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        booking_id = f"hold-release-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-04-10"
        check_out = f"{_RUN_TAG}-04-12"

        # Create hold
        create_resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert create_resp.status_code == 200

        # Release hold
        release_resp = await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id, "reason": "user_cancelled"},
        )
        assert release_resp.status_code == 200
        release_data = release_resp.json()
        assert release_data.get("success") is True
        assert release_data.get("released_count") == 2

        # Verify hold is gone
        status_resp = await client.get(
            f"{API_URL}/api/booking-holds/status",
            headers=headers,
            params={"booking_id": booking_id},
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data.get("has_hold") is False


# ═══════════════════════════════════════════════════════════════
# TEST 5: Hold Prevents Booking Conflict
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hold_prevents_booking_conflict():
    """A hold should prevent another booking from claiming the same room+dates."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        booking_id = f"hold-conflict-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-05-10"
        check_out = f"{_RUN_TAG}-05-12"

        # Create hold
        create_resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert create_resp.status_code == 200

        # Try to create a regular booking on same dates — should fail
        book_resp = await client.post(
            f"{API_URL}/api/pms/quick-booking",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "Conflict Test",
                "room_id": room["id"],
                "check_in": f"{_RUN_TAG}-05-10T14:00:00+00:00",
                "check_out": f"{_RUN_TAG}-05-12T11:00:00+00:00",
                "total_amount": 500.0,
                "guest_id": guest["id"],
            },
        )
        assert book_resp.status_code == 409, f"Booking should conflict with hold: {book_resp.text}"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 6: Manual Sweep Expired Holds
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sweep_expired_holds_api():
    """POST /api/booking-holds/sweep should clean up expired holds."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        # Trigger sweep (may or may not find expired holds)
        sweep_resp = await client.post(
            f"{API_URL}/api/booking-holds/sweep",
            headers=headers,
        )
        assert sweep_resp.status_code == 200
        sweep_data = sweep_resp.json()
        assert "expired_count" in sweep_data
        assert "bookings_affected" in sweep_data


# ═══════════════════════════════════════════════════════════════
# TEST 7: Room Blocks API (OOO/OOS) — INV-5 Integration
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_api_ooo():
    """POST /api/room-blocks should create OOO block in room_night_locks."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        start_date = f"{_RUN_TAG}-06-01"
        end_date = f"{_RUN_TAG}-06-03"

        # Apply OOO block
        ooo_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room["id"],
                "block_type": "ooo",
                "start_date": start_date,
                "end_date": end_date,
                "reason": "Water leak repair",
            },
        )
        assert ooo_resp.status_code == 200, f"OOO apply failed: {ooo_resp.text}"
        ooo_data = ooo_resp.json()
        assert ooo_data.get("success") is True
        assert len(ooo_data.get("nights_blocked", [])) == 2

        # List blocks to verify
        list_resp = await client.get(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={"room_id": room["id"], "block_type": "ooo"},
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data.get("count", 0) >= 2

        # Release OOO block
        release_resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={
                "room_id": room["id"],
                "block_type": "ooo",
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        assert release_resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# TEST 8: OOO Block Prevents Booking
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ooo_block_prevents_booking_api():
    """OOO block should prevent booking on same room+dates."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        start_date = f"{_RUN_TAG}-07-01"
        end_date = f"{_RUN_TAG}-07-03"

        # Apply OOO block
        ooo_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room["id"],
                "block_type": "ooo",
                "start_date": start_date,
                "end_date": end_date,
                "reason": "Renovation",
            },
        )
        assert ooo_resp.status_code == 200

        # Try to book — should fail
        book_resp = await client.post(
            f"{API_URL}/api/pms/quick-booking",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "OOO Conflict Test",
                "room_id": room["id"],
                "check_in": f"{_RUN_TAG}-07-01T14:00:00+00:00",
                "check_out": f"{_RUN_TAG}-07-03T11:00:00+00:00",
                "total_amount": 500.0,
                "guest_id": guest["id"],
            },
        )
        assert book_resp.status_code == 409, f"Booking should conflict with OOO: {book_resp.text}"

        # Release OOO
        await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={
                "room_id": room["id"],
                "block_type": "ooo",
                "start_date": start_date,
                "end_date": end_date,
            },
        )


# ═══════════════════════════════════════════════════════════════
# TEST 9: OOS Block via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_api_oos():
    """POST /api/room-blocks should create OOS block."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        start_date = f"{_RUN_TAG}-08-01"
        end_date = f"{_RUN_TAG}-08-03"

        # Apply OOS block
        oos_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room["id"],
                "block_type": "oos",
                "start_date": start_date,
                "end_date": end_date,
                "reason": "Deep cleaning",
            },
        )
        assert oos_resp.status_code == 200, f"OOS apply failed: {oos_resp.text}"
        oos_data = oos_resp.json()
        assert oos_data.get("success") is True

        # Release OOS block
        release_resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={
                "room_id": room["id"],
                "block_type": "oos",
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        assert release_resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# TEST 10: Maintenance Block via API
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_room_blocks_api_maintenance():
    """POST /api/room-blocks should create maintenance block."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        start_date = f"{_RUN_TAG}-09-01"
        end_date = f"{_RUN_TAG}-09-03"

        # Apply maintenance block
        maint_resp = await client.post(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            json={
                "room_id": room["id"],
                "block_type": "maintenance",
                "start_date": start_date,
                "end_date": end_date,
                "reason": "AC repair",
            },
        )
        assert maint_resp.status_code == 200, f"Maintenance apply failed: {maint_resp.text}"
        maint_data = maint_resp.json()
        assert maint_data.get("success") is True

        # Release maintenance block
        release_resp = await client.delete(
            f"{API_URL}/api/room-blocks",
            headers=headers,
            params={
                "room_id": room["id"],
                "block_type": "maintenance",
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        assert release_resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# TEST 11: Hold Conflict with Another Hold
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hold_conflict_with_another_hold():
    """Two holds on same room+dates should conflict."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        if not room:
            pytest.skip("No room available")

        booking_id_1 = f"hold-first-{uuid.uuid4().hex[:8]}"
        booking_id_2 = f"hold-second-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-10-10"
        check_out = f"{_RUN_TAG}-10-12"

        # First hold succeeds
        resp1 = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id_1,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert resp1.status_code == 200

        # Second hold on same dates should fail
        resp2 = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id_2,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert resp2.status_code == 409, f"Second hold should conflict: {resp2.text}"

        # Cleanup
        await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id_1},
        )


# ═══════════════════════════════════════════════════════════════
# TEST 12: Release After Booking Succeeds
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_release_hold_then_booking_succeeds():
    """After releasing a hold, booking on same dates should succeed."""
    headers, tenant_id = await get_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        room = await get_test_room(client, headers)
        guest = await get_test_guest(client, headers)
        if not room or not guest:
            pytest.skip("No room/guest available")

        booking_id = f"hold-release-book-{uuid.uuid4().hex[:8]}"
        check_in = f"{_RUN_TAG}-11-10"
        check_out = f"{_RUN_TAG}-11-12"

        # Create hold
        create_resp = await client.post(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            json={
                "booking_id": booking_id,
                "room_id": room["id"],
                "check_in": check_in,
                "check_out": check_out,
            },
        )
        assert create_resp.status_code == 200

        # Release hold
        release_resp = await client.delete(
            f"{API_URL}/api/booking-holds",
            headers=headers,
            params={"booking_id": booking_id},
        )
        assert release_resp.status_code == 200

        # Now booking should succeed
        book_resp = await client.post(
            f"{API_URL}/api/pms/quick-booking",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "guest_name": "After Hold Release",
                "room_id": room["id"],
                "check_in": f"{_RUN_TAG}-11-10T14:00:00+00:00",
                "check_out": f"{_RUN_TAG}-11-12T11:00:00+00:00",
                "total_amount": 500.0,
                "guest_id": guest["id"],
            },
        )
        assert book_resp.status_code == 200, f"Booking after hold release should succeed: {book_resp.text}"

        # Cleanup: cancel the booking
        bid = book_resp.json().get("id")
        if bid:
            await client.put(
                f"{API_URL}/api/pms/bookings/{bid}",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"status": "cancelled"},
            )
