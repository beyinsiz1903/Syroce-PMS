"""
Tests for Reservation Detail Module APIs
Tests: full-detail, payment recording, cari transfer, agency payment, notes, quick actions
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)

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
        import os
        from pymongo import MongoClient
        _mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms"))
        _db = _mongo[os.environ.get("DB_NAME", "hotel_pms")]
        # Find a confirmed booking (not no_show/cancelled/checked_out)
        booking = _db.bookings.find_one(
            {"id": booking_id}, {"_id": 0, "room_id": 1, "status": 1}
        )
        # If the booking isn't in a check-in-eligible state, reset it
        eligible = ['confirmed', 'guaranteed', 'pending']
        if booking and booking.get("status") not in eligible:
            _db.bookings.update_one({"id": booking_id}, {"$set": {"status": "confirmed"}})
        if booking:
            _db.rooms.update_one({"id": booking["room_id"]}, {"$set": {"status": "available", "current_booking_id": None}})
            _db.room_night_locks.delete_many({"room_id": booking["room_id"]})
        _mongo.close()

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


class TestEnsureFolioSplitFlow:
    """Folyo Böl: masraf-var-folio-yok uçtan uca akış (task #424).

    Onaylı bir rezervasyonda restoran masrafı bulunsa bile folio belgesi tembel
    oluşturulduğu için `db.folios` boş kalabilir; "Folyo Böl" o anda
    `/ensure-folio`'yu çağırır. Gerçek backend + canlı Mongo üzerinden:
      * masraf seed + ensure-folio → AÇIK guest folio oluşur, orphan masraf
        bağlanır (bound_charges >= 1),
      * ikinci çağrı idempotent (created=False, yeni folio yok),
      * full-detail folioyu + bağlı masrafı gösterir (bölme dialogu kalemleri
        listeleyebilir).

    İzole, kendi seed'ini yapan/temizleyen `E2E_` prefix'li bir rezervasyon
    kullanır; mevcut/pilot veriye dokunmaz.
    """

    @pytest.fixture
    def seeded_booking(self, booking_id):
        """Seed a fresh confirmed booking + restaurant charge with NO folio."""
        import uuid as _uuid
        from pymongo import MongoClient

        mongo = MongoClient(
            os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
        )
        mdb = mongo[os.environ.get("DB_NAME", "hotel_pms")]

        # Derive the tenant context from an existing booking the API can see.
        ref = mdb.bookings.find_one({"id": booking_id}, {"_id": 0, "tenant_id": 1})
        if not ref or not ref.get("tenant_id"):
            mongo.close()
            pytest.skip("No tenant context available for ensure-folio seed")
        tid = ref["tenant_id"]

        new_booking_id = f"E2E_ENSUREFOLIO_{_uuid.uuid4().hex[:8]}"
        charge_id = f"E2E_CHARGE_{_uuid.uuid4().hex[:8]}"

        mdb.bookings.insert_one({
            "id": new_booking_id,
            "tenant_id": tid,
            "status": "confirmed",
            "guest_id": None,
            "room_id": None,
            "booking_number": new_booking_id,
            "total_amount": 0.0,
            "guest_name": "E2E EnsureFolio Guest",
        })
        # Restoran masrafı: folio_id YOK (orphan) → ensure-folio bunu bağlamalı.
        mdb.folio_charges.insert_one({
            "id": charge_id,
            "tenant_id": tid,
            "booking_id": new_booking_id,
            "folio_id": None,
            "charge_category": "restaurant",
            "description": "Restoran - Aksam yemegi",
            "amount": 120.0,
            "quantity": 1.0,
            "total": 120.0,
            "voided": False,
        })

        yield {
            "booking_id": new_booking_id,
            "charge_id": charge_id,
            "tenant_id": tid,
        }

        # Cleanup — seed-only, tenant-scoped.
        mdb.bookings.delete_many({"id": new_booking_id, "tenant_id": tid})
        mdb.folio_charges.delete_many({"booking_id": new_booking_id, "tenant_id": tid})
        mdb.folios.delete_many({"booking_id": new_booking_id, "tenant_id": tid})
        mdb.folio_operations.delete_many({"from_booking_id": new_booking_id})
        mongo.close()

    def test_ensure_folio_creates_open_folio_and_binds_charge(
        self, authenticated_client, seeded_booking
    ):
        """charges-but-no-folio → open guest folio created + orphan charge bound."""
        bid = seeded_booking["booking_id"]
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{bid}/ensure-folio"
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data.get("success") is True
        assert data.get("created") is True, "A new folio should be created"
        assert data.get("bound_charges", 0) >= 1, "Orphan restaurant charge should bind"

        folio = data["folio"]
        assert folio["status"] == "open"
        assert folio["folio_type"] == "guest"
        assert folio["booking_id"] == bid
        assert folio.get("id")

    def test_ensure_folio_second_call_is_idempotent(
        self, authenticated_client, seeded_booking
    ):
        """Second ensure-folio returns the same open folio, created=False, no rebind."""
        bid = seeded_booking["booking_id"]

        first = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{bid}/ensure-folio"
        )
        assert first.status_code == 200, f"{first.status_code}: {first.text}"
        first_data = first.json()
        assert first_data.get("created") is True
        created_folio_id = first_data["folio"]["id"]

        second = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{bid}/ensure-folio"
        )
        assert second.status_code == 200, f"{second.status_code}: {second.text}"
        second_data = second.json()
        assert second_data.get("created") is False, "No second folio should be created"
        assert second_data.get("bound_charges") == 0
        assert second_data["folio"]["id"] == created_folio_id

    def test_full_detail_shows_folio_and_bound_charge(
        self, authenticated_client, seeded_booking
    ):
        """After ensure-folio, the split dialog source (full-detail) lists the folio + charge."""
        bid = seeded_booking["booking_id"]

        ensure = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{bid}/ensure-folio"
        )
        assert ensure.status_code == 200, f"{ensure.status_code}: {ensure.text}"
        folio_id = ensure.json()["folio"]["id"]

        detail = authenticated_client.get(
            f"{BASE_URL}/api/pms/reservations/{bid}/full-detail"
        )
        assert detail.status_code == 200, f"{detail.status_code}: {detail.text}"
        data = detail.json()

        folio_ids = [f.get("id") for f in data.get("folios", [])]
        assert folio_id in folio_ids, "Ensured folio should appear in full-detail"

        charges = data.get("charges", [])
        seeded_charge = next(
            (c for c in charges if c.get("id") == seeded_booking["charge_id"]), None
        )
        assert seeded_charge is not None, "Seeded restaurant charge should be listed"
        assert seeded_charge.get("folio_id") == folio_id, "Charge should be bound to the new folio"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
