"""
Tests for Reservation Detail Module APIs
Tests: full-detail, payment recording, cari transfer, agency payment, notes, quick actions
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token via login."""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header."""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


@pytest.fixture(scope="module")
def booking_id(authenticated_client):
    """Get a valid booking ID for testing."""
    # Get bookings list to find a valid booking ID
    response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
    if response.status_code == 200:
        bookings = response.json()
        if isinstance(bookings, list) and len(bookings) > 0:
            return bookings[0].get("id")
    pytest.skip("No bookings found for testing")


class TestReservationFullDetail:
    """Test GET /api/pms/reservations/{id}/full-detail endpoint"""

    def test_get_full_detail_success(self, authenticated_client, booking_id):
        """Test fetching full reservation detail returns correct structure."""
        response = authenticated_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/full-detail"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify main structure
        assert "booking" in data, "Response should contain 'booking'"
        assert "guest" in data, "Response should contain 'guest'"
        assert "room" in data, "Response should contain 'room'"
        assert "folios" in data, "Response should contain 'folios'"
        assert "charges" in data, "Response should contain 'charges'"
        assert "payments" in data, "Response should contain 'payments'"
        assert "extra_charges" in data, "Response should contain 'extra_charges'"
        assert "notes" in data, "Response should contain 'notes'"
        assert "history" in data, "Response should contain 'history'"
        assert "daily_rates" in data, "Response should contain 'daily_rates'"
        assert "guests" in data, "Response should contain 'guests'"
        assert "summary" in data, "Response should contain 'summary'"

        # Verify summary structure
        summary = data["summary"]
        assert "total_amount" in summary
        assert "total_charges" in summary
        assert "total_payments" in summary
        assert "balance" in summary

        # Verify booking has key fields
        booking = data["booking"]
        assert booking.get("id") == booking_id

    def test_get_full_detail_not_found(self, authenticated_client):
        """Test fetching non-existent booking returns 404."""
        response = authenticated_client.get(
            f"{BASE_URL}/api/pms/reservations/non-existent-id/full-detail"
        )
        assert response.status_code == 404

    def test_get_full_detail_unauthorized(self, api_client):
        """Test fetching without auth returns 401."""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/some-id/full-detail",
            headers={"Authorization": ""},
        )
        assert response.status_code in [401, 403]


class TestPaymentRecording:
    """Test POST /api/pms/reservations/{id}/record-payment endpoint"""

    def test_record_payment_success(self, authenticated_client, booking_id):
        """Test recording a payment works correctly."""
        payment_data = {
            "amount": 100.0,
            "method": "cash",
            "payment_type": "interim",
            "reference": "TEST-REF-001",
            "notes": "Test payment",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-payment",
            json=payment_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "payment" in data
        assert data["payment"]["amount"] == 100.0
        assert data["payment"]["method"] == "cash"
        assert data["payment"]["payment_type"] == "interim"

    def test_record_payment_card(self, authenticated_client, booking_id):
        """Test recording a card payment."""
        payment_data = {
            "amount": 250.0,
            "method": "card",
            "payment_type": "prepayment",
            "reference": "CC-AUTH-123",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-payment",
            json=payment_data,
        )
        assert response.status_code == 200

        data = response.json()
        assert data.get("success") is True
        assert data["payment"]["method"] == "card"

    def test_record_payment_invalid_booking(self, authenticated_client):
        """Test recording payment on non-existent booking returns 404."""
        payment_data = {"amount": 100.0, "method": "cash", "payment_type": "interim"}
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/invalid-booking-id/record-payment",
            json=payment_data,
        )
        assert response.status_code == 404


class TestCariAccounts:
    """Test cari account endpoints"""

    def test_list_cari_accounts(self, authenticated_client):
        """Test listing cari accounts."""
        response = authenticated_client.get(f"{BASE_URL}/api/pms/cari-accounts")
        assert response.status_code == 200

        data = response.json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)

    def test_create_cari_account(self, authenticated_client):
        """Test creating a new cari account."""
        cari_data = {
            "name": f"TEST_Cari_{os.urandom(4).hex()}",
            "account_type": "company",
            "contact_person": "Test Contact",
            "contact_email": "test@cari.com",
            "credit_limit": 10000.0,
            "payment_terms_days": 30,
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/cari-accounts", json=cari_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "account" in data
        assert data["account"]["name"] == cari_data["name"]
        assert data["account"]["credit_limit"] == 10000.0


class TestCariTransfer:
    """Test cari transfer endpoint"""

    def test_transfer_to_cari(self, authenticated_client, booking_id):
        """Test transferring amount to cari account."""
        # First get a cari account or create one
        cari_response = authenticated_client.get(f"{BASE_URL}/api/pms/cari-accounts")
        cari_accounts = cari_response.json().get("accounts", [])

        if not cari_accounts:
            # Create one
            create_resp = authenticated_client.post(
                f"{BASE_URL}/api/pms/cari-accounts",
                json={"name": "TEST_Transfer_Cari", "account_type": "company"},
            )
            cari_account_id = create_resp.json()["account"]["id"]
        else:
            cari_account_id = cari_accounts[0]["id"]

        transfer_data = {
            "amount": 500.0,
            "cari_account_id": cari_account_id,
            "description": "Test transfer",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/transfer-to-cari",
            json=transfer_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "transaction" in data
        assert data["transaction"]["amount"] == 500.0


class TestAgencyPayment:
    """Test agency payment recording"""

    def test_record_agency_payment(self, authenticated_client, booking_id):
        """Test recording an agency payment."""
        agency_data = {
            "amount": 1000.0,
            "agency_name": "Test Travel Agency",
            "reference": "AGN-VOUCHER-001",
            "notes": "Agency commission payment",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-agency-payment",
            json=agency_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "payment" in data
        assert data["payment"]["amount"] == 1000.0
        assert data["payment"]["agency_name"] == "Test Travel Agency"


class TestNotes:
    """Test notes endpoint"""

    def test_add_note(self, authenticated_client, booking_id):
        """Test adding a note to reservation."""
        note_data = {
            "content": "Test note for reservation",
            "note_type": "general",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-note", json=note_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "note" in data
        assert data["note"]["content"] == "Test note for reservation"
        assert data["note"]["note_type"] == "general"

    def test_add_important_note(self, authenticated_client, booking_id):
        """Test adding an important note."""
        note_data = {
            "content": "IMPORTANT: VIP guest arriving",
            "note_type": "important",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-note", json=note_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["note"]["note_type"] == "important"


class TestQuickActions:
    """Test front office quick actions"""

    def test_early_checkin(self, authenticated_client, booking_id):
        """Test early check-in action."""
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/early-checkin",
            json={"extra_charge": 50.0},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True

    def test_late_checkout(self, authenticated_client, booking_id):
        """Test late check-out action."""
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/late-checkout",
            json={"extra_charge": 75.0},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True

    def test_vip_toggle(self, authenticated_client, booking_id):
        """Test VIP status toggle."""
        response = authenticated_client.put(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vip-status?vip=true"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert data.get("vip_status") is True

    def test_mark_noshow(self, authenticated_client, booking_id):
        """Test marking reservation as no-show."""
        # Note: This will change the booking status, so testing last
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/mark-noshow"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True


class TestExtraCharges:
    """Test extra charge functionality"""

    def test_add_extra_charge(self, authenticated_client, booking_id):
        """Test adding an extra charge to reservation."""
        charge_data = {
            "description": "Minibar consumption",
            "category": "minibar",
            "amount": 45.0,
            "quantity": 1.0,
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-extra-charge",
            json=charge_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "charge" in data
        assert data["charge"]["description"] == "Minibar consumption"
        assert data["charge"]["category"] == "minibar"


class TestDailyRates:
    """Test daily rates update"""

    def test_update_daily_rates(self, authenticated_client, booking_id):
        """Test updating daily rates for a reservation."""
        rates_data = {
            "rates": [
                {"date": "2026-03-20", "rate": 450.0},
                {"date": "2026-03-21", "rate": 500.0},
            ]
        }
        response = authenticated_client.put(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/daily-rates",
            json=rates_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert data.get("new_total") == 950.0


class TestDeposit:
    """Test deposit recording"""

    def test_record_deposit(self, authenticated_client, booking_id):
        """Test recording a deposit payment."""
        deposit_data = {
            "amount": 200.0,
            "method": "cash",
            "reference": "DEP-001",
        }
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-deposit",
            json=deposit_data,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True
        assert "deposit" in data
        assert data["deposit"]["amount"] == 200.0


class TestGuestUpdate:
    """Test guest information update"""

    def test_update_guest_info(self, authenticated_client, booking_id):
        """Test updating guest information."""
        guest_data = {
            "name": "Updated Guest Name",
            "email": "updated@test.com",
            "phone": "+90 555 111 2222",
        }
        response = authenticated_client.put(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/update-guest",
            json=guest_data,
        )
        # May fail if no guest_id is linked
        if response.status_code == 400:
            pytest.skip("No guest linked to this booking")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data.get("success") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
