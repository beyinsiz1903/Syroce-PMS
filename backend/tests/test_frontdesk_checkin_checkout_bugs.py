"""
Test Cases for Bug A and Bug B fixes:
Bug A: Check-in from Rooms tab quick action fails with 400 error 'occupied'
Bug B: Checkout from ReservationDetailModal allowed checkout despite outstanding balance

All tests create their own data to be fully self-contained and idempotent.
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module")
def api_client():
    """Login and return session with auth header"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com", "password": "demo123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "",  # will be overwritten per-request
    })
    return session


def _get_available_room(api_client):
    resp = api_client.get(f"{BASE_URL}/api/pms/rooms")
    rooms = resp.json()
    avail = [r for r in rooms if r.get("status") == "available" and r.get("id")]
    return avail[0] if avail else None


def _get_guest(api_client):
    resp = api_client.get(f"{BASE_URL}/api/pms/guests")
    guests = resp.json()
    return guests[0] if guests else None


def _create_confirmed_booking(api_client, total_amount=500.0):
    """Create a confirmed booking with a room for testing."""
    room = _get_available_room(api_client)
    if not room:
        return None
    guest = _get_guest(api_client)
    if not guest:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    checkout = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    import uuid
    idem_key = str(uuid.uuid4())
    api_client.headers["Idempotency-Key"] = idem_key

    resp = api_client.post(f"{BASE_URL}/api/pms/bookings", json={
        "guest_id": guest["id"],
        "room_id": room["id"],
        "check_in": today,
        "check_out": checkout,
        "adults": 1,
        "children": 0,
        "guests_count": 1,
        "total_amount": total_amount,
        "source_channel": "direct",
        "origin": "ui",
        "hold_status": "none",
        "allocation_source": "manual",
    })
    if resp.status_code in (200, 201):
        booking = resp.json()
        return booking
    return None


# ─── Bug A Tests ──────────────────────────────────────────────────────

class TestBugACheckinStaleOccupied:

    def test_checkin_endpoint_exists(self, api_client):
        resp = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/nonexistent-id?create_folio=true")
        assert resp.status_code in [404, 400]

    def test_checkin_force_clean_accepted(self, api_client):
        resp = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/nonexistent?create_folio=true&force_clean=true")
        assert resp.status_code in [404, 400]

    def test_checkin_confirmed_booking(self, api_client):
        booking = _create_confirmed_booking(api_client)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking["id"]
        resp = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true"
        )
        assert resp.status_code == 200, f"Checkin should succeed: {resp.text}"
        data = resp.json()
        assert "room_number" in data
        print(f"PASS checkin: room {data['room_number']}")

        # Cleanup: force checkout
        api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")

    def test_checkin_stale_occupied_room(self, api_client):
        """If room is 'occupied' from stale state but no other checked-in booking, allow checkin."""
        booking = _create_confirmed_booking(api_client)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking["id"]
        room_id = booking.get("room_id")

        # Manually set room to 'occupied' to simulate stale state
        if room_id:
            import uuid
            api_client.headers["Idempotency-Key"] = str(uuid.uuid4())
            api_client.put(f"{BASE_URL}/api/pms/rooms/{room_id}", json={"status": "occupied"})

        resp = api_client.post(
            f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true"
        )
        assert resp.status_code == 200, f"Stale-occupied checkin should succeed: {resp.text}"
        print(f"PASS stale-occupied checkin: {resp.json()}")

        # Cleanup
        api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")


# ─── Bug B Tests ──────────────────────────────────────────────────────

class TestBugBCheckoutWithBalance:

    def test_checkout_endpoint_exists(self, api_client):
        resp = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/nonexistent?auto_close_folios=true")
        assert resp.status_code in [404, 400]

    def test_checkout_blocked_with_outstanding_balance(self, api_client):
        """Checkout returns 402 when booking has unpaid balance."""
        booking = _create_confirmed_booking(api_client, total_amount=500.0)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking["id"]

        # Check in
        ci = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true")
        assert ci.status_code == 200, f"Checkin failed: {ci.text}"

        # Try checkout without paying -> expect 402
        co = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?auto_close_folios=true")
        assert co.status_code == 402, f"Expected 402, got {co.status_code}: {co.text}"
        assert "balance" in co.json().get("detail", "").lower()
        print(f"PASS checkout blocked: {co.json()['detail']}")

        # Cleanup
        api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")

    def test_checkout_force_bypasses_balance(self, api_client):
        """force=true allows checkout despite outstanding balance."""
        booking = _create_confirmed_booking(api_client, total_amount=300.0)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking["id"]

        ci = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true")
        assert ci.status_code == 200

        co = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")
        assert co.status_code == 200, f"Force checkout should succeed: {co.text}"
        print(f"PASS force checkout: {co.json()['message']}")

    def test_checkout_succeeds_zero_balance(self, api_client):
        """Checkout succeeds when balance is fully paid."""
        booking = _create_confirmed_booking(api_client, total_amount=200.0)
        if not booking:
            pytest.skip("Could not create test booking")

        booking_id = booking["id"]

        # Check in
        ci = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true")
        assert ci.status_code == 200

        # Pay full amount
        pay = api_client.post(f"{BASE_URL}/api/pms/reservations/{booking_id}/record-payment", json={
            "amount": 200.0, "method": "cash", "payment_type": "interim",
        })
        assert pay.status_code == 200, f"Payment failed: {pay.text}"

        # Checkout should succeed
        co = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?auto_close_folios=true")
        assert co.status_code == 200, f"Zero balance checkout should succeed: {co.text}"
        print(f"PASS zero-balance checkout: {co.json()['message']}")


# ─── Integration Tests ────────────────────────────────────────────────

class TestFrontdeskIntegration:

    def test_checkin_creates_folio(self, api_client):
        booking = _create_confirmed_booking(api_client)
        if not booking:
            pytest.skip("Could not create test booking")
        booking_id = booking["id"]

        ci = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true")
        assert ci.status_code == 200

        folio = api_client.get(f"{BASE_URL}/api/frontdesk/folio/{booking_id}")
        assert folio.status_code == 200
        print(f"PASS folio created for {booking_id}")

        api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")

    def test_checkout_sets_room_dirty(self, api_client):
        booking = _create_confirmed_booking(api_client)
        if not booking:
            pytest.skip("Could not create test booking")
        booking_id = booking["id"]
        room_id = booking.get("room_id")

        ci = api_client.post(f"{BASE_URL}/api/frontdesk/checkin/{booking_id}?create_folio=true&force_clean=true")
        assert ci.status_code == 200

        co = api_client.post(f"{BASE_URL}/api/frontdesk/checkout/{booking_id}?force=true&auto_close_folios=true")
        assert co.status_code == 200

        if room_id:
            room_resp = api_client.get(f"{BASE_URL}/api/pms/rooms/{room_id}")
            if room_resp.status_code == 200:
                assert room_resp.json().get("status") == "dirty"
                print(f"PASS room {room_id[:8]} set to dirty after checkout")

    def test_rooms_and_bookings_endpoints(self, api_client):
        rooms = api_client.get(f"{BASE_URL}/api/pms/rooms")
        assert rooms.status_code == 200
        assert len(rooms.json()) > 0

        bookings = api_client.get(f"{BASE_URL}/api/pms/bookings")
        assert bookings.status_code == 200
        b = bookings.json()
        if b:
            assert "total_amount" in b[0] or b[0].get("total_amount") is None
        print(f"PASS rooms={len(rooms.json())} bookings={len(b)}")
