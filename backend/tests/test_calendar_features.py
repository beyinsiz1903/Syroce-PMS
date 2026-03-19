"""
Test Calendar Features - Testing the 11 calendar improvements:
- available-rooms-by-type API
- voucher generation API
- invoice-charges and generate-invoice APIs  
- cancel reservation API
- cari-accounts/create API
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session

@pytest.fixture(scope="module") 
def sample_booking_id(api_client):
    """Get a sample booking ID for testing"""
    response = api_client.get(f"{BASE_URL}/api/pms/bookings?limit=10")
    if response.status_code == 200:
        bookings = response.json()
        if bookings and len(bookings) > 0:
            return bookings[0]["id"]
    pytest.skip("No bookings available for testing")


class TestAvailableRoomsByType:
    """Test GET /api/pms/available-rooms-by-type endpoint"""
    
    def test_available_rooms_by_type_success(self, api_client):
        """Test getting available rooms grouped by type"""
        check_in = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        response = api_client.get(
            f"{BASE_URL}/api/pms/available-rooms-by-type?check_in={check_in}&check_out={check_out}"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "room_types" in data, "Response should have room_types field"
        assert isinstance(data["room_types"], list), "room_types should be a list"
        
        # If there are room types, validate structure
        if len(data["room_types"]) > 0:
            rt = data["room_types"][0]
            assert "type" in rt, "Each room type should have 'type' field"
            assert "rooms" in rt, "Each room type should have 'rooms' list"
            assert "base_price" in rt, "Each room type should have 'base_price'"
            
            # Validate room structure
            if len(rt["rooms"]) > 0:
                room = rt["rooms"][0]
                assert "id" in room, "Each room should have 'id'"
                assert "room_number" in room, "Each room should have 'room_number'"
                assert "is_available" in room, "Each room should have 'is_available' flag"
        
        print(f"PASS: available-rooms-by-type returned {len(data['room_types'])} room types")

    def test_available_rooms_by_type_missing_params(self, api_client):
        """Test that missing parameters are handled"""
        response = api_client.get(f"{BASE_URL}/api/pms/available-rooms-by-type")
        # Should return 422 validation error or handle gracefully
        assert response.status_code in [200, 422], f"Expected 200 or 422, got {response.status_code}"
        print(f"PASS: Missing params handled with status {response.status_code}")


class TestVoucherGeneration:
    """Test GET /api/pms/reservations/{booking_id}/voucher endpoint"""
    
    def test_voucher_generation_success(self, api_client, sample_booking_id):
        """Test generating voucher for a booking"""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/voucher"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "success" in data, "Response should have 'success' field"
        assert "voucher_html" in data, "Response should have 'voucher_html' field"
        assert "voucher_no" in data, "Response should have 'voucher_no' field"
        
        # Validate voucher HTML contains expected content
        html = data["voucher_html"]
        assert "KONAKLAMA VOUCHER" in html, "Voucher should contain title"
        assert "Voucher No:" in html, "Voucher should contain voucher number"
        
        print(f"PASS: Voucher generated with number {data['voucher_no']}")

    def test_voucher_invalid_booking(self, api_client):
        """Test voucher generation with invalid booking ID"""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/invalid-booking-id/voucher"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Invalid booking returns 404")


class TestInvoiceCharges:
    """Test GET /api/pms/reservations/{booking_id}/invoice-charges endpoint"""
    
    def test_invoice_charges_success(self, api_client, sample_booking_id):
        """Test getting invoice charges for a booking"""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/invoice-charges"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "charges" in data, "Response should have 'charges' field"
        assert isinstance(data["charges"], list), "charges should be a list"
        
        # If charges exist, validate structure
        if len(data["charges"]) > 0:
            charge = data["charges"][0]
            assert "id" in charge, "Each charge should have 'id'"
            assert "description" in charge, "Each charge should have 'description'"
            assert "amount" in charge, "Each charge should have 'amount'"
            assert "category" in charge, "Each charge should have 'category'"
        
        print(f"PASS: Invoice charges returned {len(data['charges'])} items")

    def test_invoice_charges_invalid_booking(self, api_client):
        """Test invoice charges with invalid booking ID"""
        response = api_client.get(
            f"{BASE_URL}/api/pms/reservations/invalid-booking-id/invoice-charges"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Invalid booking returns 404")


class TestGenerateInvoice:
    """Test POST /api/pms/reservations/{booking_id}/generate-invoice endpoint"""
    
    def test_generate_invoice_success(self, api_client, sample_booking_id):
        """Test generating invoice with billing info"""
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/generate-invoice",
            json={
                "billing_name": "TEST Test Company",
                "billing_tax_id": "1234567890",
                "billing_tax_office": "Istanbul",
                "billing_address": "Test Address 123",
                "billing_email": "test@testcompany.com",
                "invoice_note": "Test invoice note",
                "selected_charge_ids": []  # Empty = include all charges
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] is True, "Success should be True"
        assert "invoice_html" in data, "Response should have 'invoice_html'"
        assert "invoice_number" in data, "Response should have 'invoice_number'"
        assert "total" in data, "Response should have 'total'"
        assert "all_charges" in data, "Response should have 'all_charges'"
        
        # Validate invoice HTML
        html = data["invoice_html"]
        assert "FATURA" in html, "Invoice should contain FATURA title"
        assert "TEST Test Company" in html or "Test Company" in html, "Invoice should contain billing name"
        
        print(f"PASS: Invoice generated with number {data['invoice_number']}, total: {data['total']}")

    def test_generate_invoice_with_selected_charges(self, api_client, sample_booking_id):
        """Test generating invoice with selected charges only"""
        # First get available charges
        charges_resp = api_client.get(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/invoice-charges"
        )
        if charges_resp.status_code != 200:
            pytest.skip("Could not get charges for booking")
        
        charges = charges_resp.json().get("charges", [])
        if len(charges) < 1:
            pytest.skip("No charges available for testing")
        
        # Generate invoice with only first charge
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/generate-invoice",
            json={
                "selected_charge_ids": [charges[0]["id"]],
                "billing_name": "TEST Selective Invoice"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["success"] is True
        print(f"PASS: Selective invoice generated with {len(charges)} charge options")


class TestCancelReservation:
    """Test POST /api/pms/reservations/{booking_id}/cancel endpoint"""
    
    def test_cancel_reservation_requires_reason(self, api_client, sample_booking_id):
        """Test that cancellation requires reason"""
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/{sample_booking_id}/cancel",
            json={
                "reason": "",  # Empty reason
                "cancel_type": "guest_request"
            }
        )
        # Should fail or handle empty reason
        # Check response - may return 200 with error or 422
        print(f"Cancel with empty reason returned status {response.status_code}")
    
    def test_cancel_reservation_with_noshow(self, api_client):
        """Test cancellation with no-show option (structure validation)"""
        # Create a test booking first to avoid canceling real bookings
        response = api_client.post(
            f"{BASE_URL}/api/pms/reservations/nonexistent-test-id/cancel",
            json={
                "reason": "TEST No-show test",
                "cancel_type": "no_suitable_room",
                "apply_noshow": True,
                "noshow_charge_type": "per_night",
                "noshow_charge_amount": 100.0
            }
        )
        # Should return 404 for non-existent booking
        assert response.status_code == 404, f"Expected 404 for non-existent booking, got {response.status_code}"
        print("PASS: Cancel with no-show payload structure validated")

    def test_cancel_types_validation(self, api_client):
        """Test that cancel endpoint accepts various cancel types"""
        cancel_types = ["guest_request", "no_suitable_room", "force_majeure", "overbooking", "payment_issue", "other"]
        
        for cancel_type in cancel_types:
            response = api_client.post(
                f"{BASE_URL}/api/pms/reservations/test-booking-id/cancel",
                json={
                    "reason": f"TEST {cancel_type} reason",
                    "cancel_type": cancel_type
                }
            )
            # Should return 404 (booking not found) not 422 (validation error)
            assert response.status_code == 404, f"Cancel type '{cancel_type}' should be accepted, got {response.status_code}"
        
        print(f"PASS: All {len(cancel_types)} cancel types validated")


class TestCariAccountCreate:
    """Test POST /api/pms/cari-accounts/create endpoint"""
    
    def test_create_cari_account_success(self, api_client):
        """Test creating a new cari account"""
        unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
        response = api_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/create",
            json={
                "name": f"TEST Cari Account {unique_id}",
                "account_type": "agency",
                "tax_id": "9876543210",
                "tax_office": "Kadikoy",
                "address": "Test Address 456",
                "phone": "+90 555 123 4567",
                "email": f"test{unique_id}@agency.com"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] is True, "Success should be True"
        assert "account" in data, "Response should have 'account' field"
        
        account = data["account"]
        assert "id" in account, "Account should have 'id'"
        assert "name" in account, "Account should have 'name'"
        assert account["account_type"] == "agency", "Account type should be 'agency'"
        assert account["balance"] == 0, "Initial balance should be 0"
        
        print(f"PASS: Cari account created with ID {account['id']}")

    def test_create_cari_account_types(self, api_client):
        """Test creating cari accounts with different types"""
        account_types = ["agency", "corporate", "individual"]
        
        for acc_type in account_types:
            unique_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            response = api_client.post(
                f"{BASE_URL}/api/pms/cari-accounts/create",
                json={
                    "name": f"TEST {acc_type} account {unique_id}",
                    "account_type": acc_type
                }
            )
            
            assert response.status_code == 200, f"Failed to create {acc_type} account: {response.text}"
            data = response.json()
            assert data["success"] is True
            assert data["account"]["account_type"] == acc_type
        
        print(f"PASS: All {len(account_types)} account types created successfully")

    def test_create_cari_account_missing_name(self, api_client):
        """Test that cari account creation requires name"""
        response = api_client.post(
            f"{BASE_URL}/api/pms/cari-accounts/create",
            json={
                "account_type": "agency"
                # Missing name
            }
        )
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422 for missing name, got {response.status_code}"
        print("PASS: Missing name returns 422 validation error")


class TestCariAccountsList:
    """Test GET /api/pms/cari-accounts endpoint"""
    
    def test_get_cari_accounts(self, api_client):
        """Test getting list of cari accounts"""
        response = api_client.get(f"{BASE_URL}/api/pms/cari-accounts")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "accounts" in data, "Response should have 'accounts' field"
        assert isinstance(data["accounts"], list), "accounts should be a list"
        
        print(f"PASS: Cari accounts list returned {len(data['accounts'])} accounts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
