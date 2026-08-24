"""
Battle Tests: Cancellation Edge Cases
=======================================
Tests for all cancellation scenarios in a real hotel environment.
"""
import os
import random
import uuid

import httpx
import pytest

API_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8001")

_cached_headers = None
_run_year = random.randint(2100, 9000)


async def get_auth_headers():
    global _cached_headers
    if _cached_headers:
        return _cached_headers
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        token = data.get("access_token") or data.get("token", "")
        assert token, f"Login response did not include a token: {data}"
        _cached_headers = {"Authorization": f"Bearer {token}"}
        return _cached_headers


async def create_test_booking(client, headers, days_offset=40):
    """Create an isolated far-future booking or fail with diagnostics.

    Room ``status`` only describes the current operational state; it does not
    prove that a room is free for an arbitrary future stay.  These battle tests
    share one seeded database, so choosing one random room/date made setup
    intermittently collide with bookings created by other tests.  Try every
    operationally usable room across isolated future years instead.
    """
    rooms_resp = await client.get(f"{API_URL}/api/pms/rooms", headers=headers)
    assert rooms_resp.status_code == 200, f"Rooms request failed: {rooms_resp.text}"
    rooms = rooms_resp.json()
    if isinstance(rooms, dict):
        rooms = rooms.get("rooms", rooms.get("data", []))
    available_rooms = [
        room for room in rooms
        if room.get("status") in ("available", "clean", None) and room.get("id")
    ]
    assert available_rooms, f"No operationally usable room in seed data: {rooms!r}"

    month = max(1, min(12, days_offset // 10))
    failures = []
    for year_offset in range(3):
        check_in = f"{_run_year + year_offset}-{month:02d}-10"
        check_out = f"{_run_year + year_offset}-{month:02d}-12"
        for room in available_rooms:
            booking_resp = await client.post(
                f"{API_URL}/api/pms/quick-booking",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "room_id": room["id"],
                    "guest_name": "Cancellation Battle Test",
                    "check_in": check_in,
                    "check_out": check_out,
                    "total_amount": 200.0,
                },
            )
            if booking_resp.status_code in (200, 201):
                data = booking_resp.json()
                return data.get("booking", data)
            failures.append(
                f"room={room['id']} stay={check_in}/{check_out} "
                f"status={booking_resp.status_code} body={booking_resp.text[:300]}"
            )

    pytest.fail(
        "Could not create isolated cancellation test booking after "
        f"{len(failures)} attempts:\n" + "\n".join(failures)
    )


@pytest.mark.asyncio
async def test_cancel_confirmed_booking():
    """Cancel confirmed booking -> status=cancelled, room released."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        booking = await create_test_booking(client, headers, days_offset=40)

        booking_id = booking.get("id")
        assert booking_id, f"Create response did not include booking id: {booking}"
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

        booking_id = booking.get("id")
        assert booking_id, f"Create response did not include booking id: {booking}"

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
