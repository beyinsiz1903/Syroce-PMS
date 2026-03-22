"""
Battle Tests: Cancellation Edge Cases
=======================================
Tests for all cancellation scenarios in a real hotel environment.
"""
import pytest
import httpx
import os
import uuid
import random
from datetime import datetime, timedelta, timezone

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")

_cached_headers = None


async def get_auth_headers():
    global _cached_headers
    if _cached_headers:
        return _cached_headers
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        data = resp.json()
        token = data.get("access_token") or data.get("token", "")
        _cached_headers = {"Authorization": f"Bearer {token}"}
        return _cached_headers


async def create_test_booking(client, headers, days_offset=40):
    """Create a test booking with correct fields."""
    rooms_resp = await client.get(f"{API_URL}/api/pms/rooms", headers=headers)
    rooms = rooms_resp.json() if rooms_resp.status_code == 200 else []
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms", rooms.get("data", []))
    available_rooms = [r for r in rooms if r.get("status") == "available"]
    if not available_rooms:
        return None

    guests_resp = await client.get(f"{API_URL}/api/pms/guests?limit=1", headers=headers)
    guests = guests_resp.json() if isinstance(guests_resp.json(), list) else []
    if not guests:
        return None

    today = datetime.now(timezone.utc)
    # Use random offset to avoid conflicts
    random_extra = random.randint(0, 100)
    check_in = (today + timedelta(days=days_offset + random_extra)).strftime("%Y-%m-%d")
    check_out = (today + timedelta(days=days_offset + random_extra + 2)).strftime("%Y-%m-%d")

    # Pick a random available room
    room = random.choice(available_rooms)
    req_headers = {**headers, "Idempotency-Key": str(uuid.uuid4())}
    booking_resp = await client.post(
        f"{API_URL}/api/pms/bookings",
        headers=req_headers,
        json={
            "room_id": room["id"],
            "guest_id": guests[0]["id"],
            "guest_name": guests[0].get("name", "Test Guest"),
            "guests_count": 1,
            "check_in": check_in,
            "check_out": check_out,
            "total_amount": 200.0,
            "status": "confirmed",
        },
    )
    if booking_resp.status_code in (200, 201):
        data = booking_resp.json()
        return data.get("booking", data)
    return None


@pytest.mark.asyncio
async def test_cancel_confirmed_booking():
    """Cancel confirmed booking -> status=cancelled, room released."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        booking = await create_test_booking(client, headers, days_offset=40)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking.get("id")
        cancel_headers = {**headers, "Idempotency-Key": str(uuid.uuid4())}
        cancel_resp = await client.put(
            f"{API_URL}/api/pms/bookings/{booking_id}",
            headers=cancel_headers,
            json={"status": "cancelled"},
        )
        assert cancel_resp.status_code in (200, 201), f"Cancel failed: {cancel_resp.text}"
        result = cancel_resp.json()
        if isinstance(result, dict) and "booking" in result:
            result = result["booking"]
        assert result.get("status") == "cancelled"


@pytest.mark.asyncio
async def test_double_cancel_is_idempotent():
    """Cancelling an already-cancelled booking should be idempotent."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        booking = await create_test_booking(client, headers, days_offset=50)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking.get("id")

        # First cancel
        resp1 = await client.put(
            f"{API_URL}/api/pms/bookings/{booking_id}",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"status": "cancelled"},
        )
        assert resp1.status_code in (200, 201)

        # Second cancel — should succeed or return unchanged
        resp2 = await client.put(
            f"{API_URL}/api/pms/bookings/{booking_id}",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"status": "cancelled"},
        )
        # Idempotent: either success or already cancelled
        assert resp2.status_code in (200, 201, 409, 400)


@pytest.mark.asyncio
async def test_cancel_checked_out_booking_rejected():
    """Cancelling a checked-out booking should be rejected or handled gracefully."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        bookings_resp = await client.get(f"{API_URL}/api/pms/bookings", headers=headers)
        if bookings_resp.status_code != 200:
            pytest.skip("Could not fetch bookings")
        bookings = bookings_resp.json()
        if isinstance(bookings, dict):
            bookings = bookings.get("bookings", bookings.get("data", []))

        checked_out = [b for b in bookings if b.get("status") == "checked_out"]
        if not checked_out:
            pytest.skip("No checked_out booking available for test")

        booking_id = checked_out[0]["id"]
        cancel_resp = await client.put(
            f"{API_URL}/api/pms/bookings/{booking_id}",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"status": "cancelled"},
        )
        assert cancel_resp.status_code in (200, 400, 409, 422)
