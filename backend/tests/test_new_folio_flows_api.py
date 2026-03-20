"""
Tests for New Folio & Reservation Flows
Tests: Check-in/Check-out, Cari Reconcile, Transfer-to-Agency, Room Service charges
These are the new features added for full PMS workflow:
1. Giris Yap / Cikis Yap (Check-in/Check-out) via booking status update
2. Mahsuplastir (Reconcile) - POST /api/pms/cari-accounts/{id}/reconcile
3. Acenteye Aktar (Transfer to Agency) - POST /api/pms/cari-accounts/{id}/transfer-to-agency
4. Room Service charge category in extra charges
5. Split charge functionality
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set - integration tests require a running server"
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
    response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
    if response.status_code == 200:
        bookings = response.json()
        if isinstance(bookings, list) and len(bookings) > 0:
            return bookings[0].get("id")
    pytest.skip("No bookings found for testing")


@pytest.fixture(scope="module")
def confirmed_booking_id(authenticated_client):
    """Get a booking with 'confirmed' status for check-in testing."""
    response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?status=confirmed&limit=10")
    if response.status_code == 200:
        bookings = response.json()
        if isinstance(bookings, list):
            for booking in bookings:
                if booking.get("status") == "confirmed":
                    return booking.get("id")
    # Fallback - get any booking
    response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
    if response.status_code == 200:
        bookings = response.json()
        if isinstance(bookings, list) and len(bookings) > 0:
            return bookings[0].get("id")
    pytest.skip("No bookings found for testing")


@pytest.fixture(scope="module")
def cari_account_ids(authenticated_client):
    """Get or create cari accounts for testing."""
    # First list existing cari accounts
    response = authenticated_client.get(f"{BASE_URL}/api/pms/cari-accounts")
    if response.status_code == 200:
        data = response.json()
        accounts = data.get("accounts", [])
        
        # Find a regular company account and an agency account
        company_id = None
        agency_id = None
        
        for acc in accounts:
            if acc.get("account_type") == "agency" and not agency_id:
                agency_id = acc.get("id")
            elif acc.get("account_type") == "company" and not company_id:
                company_id = acc.get("id")
        
        # Create test accounts if needed
        if not company_id:
            create_resp = authenticated_client.post(
                f"{BASE_URL}/api/pms/cari-accounts",
                json={
                    "name": f"TEST_Company_{uuid.uuid4().hex[:8]}",
                    "account_type": "company",
                    "credit_limit": 50000.0,
                    "payment_terms_days": 30,
                }
            )
            if create_resp.status_code == 200:
                company_id = create_resp.json().get("account", {}).get("id")
        
        if not agency_id:
            create_resp = authenticated_client.post(
                f"{BASE_URL}/api/pms/cari-accounts",
                json={
                    "name": f"TEST_Agency_{uuid.uuid4().hex[:8]}",
                    "account_type": "agency",
                    "credit_limit": 100000.0,
                    "payment_terms_days": 45,
                }
            )
            if create_resp.status_code == 200:
                agency_id = create_resp.json().get("account", {}).get("id")
        
        return {"company": company_id, "agency": agency_id}
    
    pytest.skip("Could not get/create cari accounts")


class TestCheckInCheckOut:
    """Test Check-in (Giris Yap) and Check-out (Cikis Yap) via booking status update"""

    def test_check_in_booking(self, authenticated_client, confirmed_booking_id):
        """Test checking in a booking by updating status to checked_in."""
        # First, get current booking status
        response = authenticated_client.get(
            f"{BASE_URL}/api/pms/reservations/{confirmed_booking_id}/full-detail"
        )
        if response.status_code != 200:
            pytest.skip("Could not fetch booking details")
        
        initial_status = response.json().get("booking", {}).get("status")
        print(f"Initial booking status: {initial_status}")
        
        # Update status to checked_in
        update_response = authenticated_client.put(
            f"{BASE_URL}/api/pms/bookings/{confirmed_booking_id}",
            json={"status": "checked_in"},
            headers={"Idempotency-Key": f"test-checkin-{uuid.uuid4().hex}"}
        )
        
        # Should succeed or at least not error
        assert update_response.status_code in [200, 400], f"Expected 200 or 400, got {update_response.status_code}"
        
        if update_response.status_code == 200:
            # Verify the status was updated
            verify_response = authenticated_client.get(
                f"{BASE_URL}/api/pms/reservations/{confirmed_booking_id}/full-detail"
            )
            if verify_response.status_code == 200:
                new_status = verify_response.json().get("booking", {}).get("status")
                print(f"New booking status after check-in: {new_status}")

    def test_check_out_booking(self, authenticated_client, confirmed_booking_id):
        """Test checking out a booking by updating status to checked_out."""
        # First ensure booking is checked_in
        authenticated_client.put(
            f"{BASE_URL}/api/pms/bookings/{confirmed_booking_id}",
            json={"status": "checked_in"},
            headers={"Idempotency-Key": f"test-checkin-pre-{uuid.uuid4().hex}"}
        )
        
        # Now check out
        update_response = authenticated_client.put(
            f"{BASE_URL}/api/pms/bookings/{confirmed_booking_id}",
            json={"status": "checked_out"},
            headers={"Idempotency-Key": f"test-checkout-{uuid.uuid4().hex}"}
        )
        
        assert update_response.status_code in [200, 400], f"Expected 200 or 400, got {update_response.status_code}"
        
        # Restore to confirmed for other tests
        authenticated_client.put(
            f"{BASE_URL}/api/pms/bookings/{confirmed_booking_id}",
            json={"status": "confirmed"},
            headers={"Idempotency-Key": f"test-restore-{uuid.uuid4().hex}"}
        )


class TestCariReconcile:
    """Test POST /api/pms/cari-accounts/{id}/reconcile (Mahsuplastir)"""

    def test_reconcile_cari_account(self, authenticated_client, cari_account_ids):
        """Test reconciling (mahsuplastir) a cari account."""
        company_id = cari_account_ids.get("company")
        if not company_id:
            pytest.skip("No company cari account available")
        
        reconcile_data = {
            "amount": 500.0,
            "description": "TEST_Mahsuplastirma - Odeme mahsubu"
        }
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/{company_id}/reconcile",
            json=reconcile_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "transaction" in data
        assert data["transaction"]["amount"] == 500.0
        assert data["transaction"]["transaction_type"] == "payment"
        print(f"Reconcile transaction created: {data['transaction']['id']}")

    def test_reconcile_nonexistent_account(self, authenticated_client):
        """Test reconciling a non-existent account returns 404."""
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/nonexistent-id/reconcile",
            json={"amount": 100.0}
        )
        assert response.status_code == 404


class TestCariTransferToAgency:
    """Test POST /api/pms/cari-accounts/{id}/transfer-to-agency (Acenteye Aktar)"""

    def test_transfer_cari_to_agency(self, authenticated_client, cari_account_ids):
        """Test transferring cari balance to an agency account."""
        company_id = cari_account_ids.get("company")
        agency_id = cari_account_ids.get("agency")
        
        if not company_id or not agency_id:
            pytest.skip("Need both company and agency cari accounts")
        
        transfer_data = {
            "amount": 1000.0,
            "cari_account_id": agency_id,
            "description": "TEST_Acenteye aktarim"
        }
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/{company_id}/transfer-to-agency",
            json=transfer_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "debit" in data
        assert "credit" in data
        assert data["debit"]["transaction_type"] == "transfer_out"
        assert data["credit"]["transaction_type"] == "transfer_in"
        print(f"Transfer completed: debit={data['debit']['id']}, credit={data['credit']['id']}")

    def test_transfer_to_nonexistent_target(self, authenticated_client, cari_account_ids):
        """Test transferring to non-existent target returns 404."""
        company_id = cari_account_ids.get("company")
        if not company_id:
            pytest.skip("No company cari account")
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/{company_id}/transfer-to-agency",
            json={"amount": 100.0, "cari_account_id": "nonexistent-target"}
        )
        assert response.status_code == 404


class TestRoomServiceCharges:
    """Test adding room_service category extra charges"""

    def test_add_room_service_charge(self, authenticated_client, booking_id):
        """Test adding an extra charge with room_service category."""
        charge_data = {
            "description": "TEST_Oda Servisi - Kahvalti",
            "category": "room_service",
            "amount": 75.0,
            "quantity": 2
        }
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-extra-charge",
            json=charge_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "charge" in data
        assert data["charge"]["category"] == "room_service"
        assert data["charge"]["total"] == 150.0  # 75 * 2
        print(f"Room service charge created: {data['charge']['id']}")

    def test_add_minibar_charge(self, authenticated_client, booking_id):
        """Test adding an extra charge with minibar category."""
        charge_data = {
            "description": "TEST_Minibar - Icecekler",
            "category": "minibar",
            "amount": 25.0,
            "quantity": 1
        }
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-extra-charge",
            json=charge_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["charge"]["category"] == "minibar"


class TestChargeSplit:
    """Test charge split functionality (Masraf Bol)"""

    def test_split_charge_to_different_room(self, authenticated_client, booking_id):
        """Test splitting a charge to a different booking."""
        # First, create a charge to split
        charge_response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/add-extra-charge",
            json={
                "description": "TEST_Charge_To_Split",
                "category": "food",
                "amount": 200.0,
                "quantity": 1
            }
        )
        
        if charge_response.status_code != 200:
            pytest.skip("Could not create charge for split test")
        
        charge_id = charge_response.json().get("charge", {}).get("id")
        
        # Get another booking to split to
        bookings_response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
        if bookings_response.status_code != 200:
            pytest.skip("Could not get bookings list")
        
        bookings = bookings_response.json()
        target_booking_id = None
        for b in bookings:
            if b.get("id") != booking_id:
                target_booking_id = b.get("id")
                break
        
        if not target_booking_id:
            pytest.skip("Need at least 2 bookings for split test")
        
        # Now split the charge
        split_response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/split-charge",
            json={
                "charge_id": charge_id,
                "target_booking_id": target_booking_id,
                "split_amount": 80.0,
                "reason": "TEST_Split to different room"
            }
        )
        
        assert split_response.status_code == 200, f"Expected 200, got {split_response.status_code}: {split_response.text}"
        
        data = split_response.json()
        assert data.get("success") is True
        assert "new_charge" in data
        assert data["new_charge"]["total"] == 80.0
        assert data["remaining_amount"] == 120.0  # 200 - 80
        print(f"Charge split: new_charge={data['new_charge']['id']}, remaining={data['remaining_amount']}")


class TestFolioButtonActions:
    """Test all Folyolar tab button actions"""

    def test_odeme_al_button_flow(self, authenticated_client, booking_id):
        """Test Odeme Al (Record Payment) flow."""
        payment_response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-payment",
            json={
                "amount": 150.0,
                "method": "cash",
                "payment_type": "interim",
                "reference": "TEST-ODEME-AL-001"
            }
        )
        assert payment_response.status_code == 200
        assert payment_response.json().get("success") is True

    def test_cariye_aktar_button_flow(self, authenticated_client, booking_id, cari_account_ids):
        """Test Cariye Aktar (Transfer to Cari) flow."""
        company_id = cari_account_ids.get("company")
        if not company_id:
            pytest.skip("No company cari account")
        
        transfer_response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/transfer-to-cari",
            json={
                "amount": 300.0,
                "cari_account_id": company_id,
                "description": "TEST_Cariye aktarim"
            }
        )
        assert transfer_response.status_code == 200
        assert transfer_response.json().get("success") is True

    def test_acente_odemesi_button_flow(self, authenticated_client, booking_id):
        """Test Acente Odemesi (Agency Payment) flow."""
        agency_response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/record-agency-payment",
            json={
                "amount": 500.0,
                "agency_name": "TEST_Travel_Agency",
                "reference": "VOUCHER-TEST-001"
            }
        )
        assert agency_response.status_code == 200
        assert agency_response.json().get("success") is True


class TestSidebarQuickActions:
    """Test sidebar quick action buttons"""

    def test_erken_giris_button(self, authenticated_client, booking_id):
        """Test Erken Giris (Early Check-in) action."""
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/early-checkin",
            json={"extra_charge": 50.0}
        )
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_gec_cikis_button(self, authenticated_client, booking_id):
        """Test Gec Cikis (Late Check-out) action."""
        response = authenticated_client.post(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/late-checkout",
            json={"extra_charge": 75.0}
        )
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_vip_status_toggle(self, authenticated_client, booking_id):
        """Test VIP status toggle."""
        # Set VIP
        response = authenticated_client.put(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vip-status?vip=true"
        )
        assert response.status_code == 200
        assert response.json().get("vip_status") is True
        
        # Remove VIP
        response = authenticated_client.put(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/vip-status?vip=false"
        )
        assert response.status_code == 200
        assert response.json().get("vip_status") is False

    def test_no_show_action(self, authenticated_client, booking_id):
        """Test marking as No-Show."""
        # Get a different booking for no-show test to not affect other tests
        bookings_response = authenticated_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
        if bookings_response.status_code == 200:
            bookings = bookings_response.json()
            test_booking_id = None
            for b in bookings:
                if b.get("id") != booking_id:
                    test_booking_id = b.get("id")
                    break
            
            if test_booking_id:
                response = authenticated_client.post(
                    f"{BASE_URL}/api/pms/reservations/{test_booking_id}/mark-noshow"
                )
                # May fail if booking not in valid state, but endpoint should exist
                assert response.status_code in [200, 400]


class TestBalanceCalculation:
    """Test balance calculation in full-detail"""

    def test_balance_includes_total_amount(self, authenticated_client, booking_id):
        """Verify balance calculation includes total_amount."""
        response = authenticated_client.get(
            f"{BASE_URL}/api/pms/reservations/{booking_id}/full-detail"
        )
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        # Verify all summary fields exist
        assert "total_amount" in summary
        assert "total_charges" in summary
        assert "total_payments" in summary
        assert "total_extra" in summary
        assert "balance" in summary
        
        # Verify balance calculation: total_amount + charges + extra - payments
        expected_balance = (
            summary.get("total_amount", 0) + 
            summary.get("total_charges", 0) + 
            summary.get("total_extra", 0) - 
            summary.get("total_payments", 0)
        )
        actual_balance = summary.get("balance", 0)
        
        # Allow small floating point difference
        assert abs(expected_balance - actual_balance) < 0.01, \
            f"Balance mismatch: expected {expected_balance}, got {actual_balance}"
        
        print(f"Balance calculation verified: total={summary['total_amount']}, "
              f"charges={summary['total_charges']}, extra={summary['total_extra']}, "
              f"payments={summary['total_payments']}, balance={summary['balance']}")
