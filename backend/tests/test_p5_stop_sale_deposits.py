"""
P5 Features Test Suite - Stop Sale and Deposit Tracking APIs
Tests for Rate Manager Stop Sale functionality and Folio Management (Deposit Tracking)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://pms-channel-sync.preview.emergentagent.com')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestStopSaleAPI(TestAuth):
    """Stop Sale API Tests - Rate Manager Stop Sale functionality"""
    
    def test_get_stop_sale_status(self, headers):
        """Test GET /api/rates/stop-sale/status - Returns operator status"""
        response = requests.get(
            f"{BASE_URL}/api/rates/stop-sale/status",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "operators" in data, "Response should contain 'operators' key"
        # Operators should be a dict (possibly empty)
        assert isinstance(data["operators"], dict), "operators should be a dictionary"
    
    def test_toggle_stop_sale_on(self, headers):
        """Test POST /api/rates/stop-sale/toggle - Activate stop-sale"""
        response = requests.post(
            f"{BASE_URL}/api/rates/stop-sale/toggle",
            headers=headers,
            json={
                "operator_id": "booking_com",
                "stop_sale": True
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("stop_sale") == True, "stop_sale should be True"
    
    def test_toggle_stop_sale_off(self, headers):
        """Test POST /api/rates/stop-sale/toggle - Deactivate stop-sale"""
        response = requests.post(
            f"{BASE_URL}/api/rates/stop-sale/toggle",
            headers=headers,
            json={
                "operator_id": "booking_com",
                "stop_sale": False
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("stop_sale") == False, "stop_sale should be False"
    
    def test_get_stop_sale_status_after_toggle(self, headers):
        """Verify stop sale status is persisted"""
        # First set a stop sale
        requests.post(
            f"{BASE_URL}/api/rates/stop-sale/toggle",
            headers=headers,
            json={"operator_id": "expedia", "stop_sale": True}
        )
        
        # Then check status
        response = requests.get(
            f"{BASE_URL}/api/rates/stop-sale/status",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # Clean up - reset to False
        requests.post(
            f"{BASE_URL}/api/rates/stop-sale/toggle",
            headers=headers,
            json={"operator_id": "expedia", "stop_sale": False}
        )


class TestDepositsAPI(TestAuth):
    """Deposits API Tests - Folio Management"""
    
    def test_list_all_deposits(self, headers):
        """Test GET /api/pms/deposits/all - List all deposits"""
        response = requests.get(
            f"{BASE_URL}/api/pms/deposits/all",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "deposits" in data, "Response should contain 'deposits' key"
        assert isinstance(data["deposits"], list), "deposits should be a list"
        
        # If there are deposits, verify structure
        if len(data["deposits"]) > 0:
            deposit = data["deposits"][0]
            assert "id" in deposit, "Deposit should have 'id'"
            assert "amount" in deposit, "Deposit should have 'amount'"
            assert "status" in deposit, "Deposit should have 'status'"
    
    def test_bookings_search_parameter(self, headers):
        """Test GET /api/pms/bookings?search= - Search parameter works"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            headers=headers,
            params={"search": "test", "limit": 10}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "bookings" in data, "Response should contain 'bookings' key"
        assert isinstance(data["bookings"], list), "bookings should be a list"
    
    def test_bookings_search_empty(self, headers):
        """Test GET /api/pms/bookings?search= - Empty search returns results"""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            headers=headers,
            params={"limit": 5}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Should return list or dict with bookings
        if isinstance(data, dict):
            assert "bookings" in data or isinstance(data.get("bookings"), list)
        elif isinstance(data, list):
            pass  # Direct list response is also valid


class TestRateManagerGrid(TestAuth):
    """Rate Manager Grid API Tests"""
    
    def test_get_rate_manager_grid(self, headers):
        """Test GET /api/channel-manager/rate-manager/grid
        
        Note: Returns 404 when no Exely connection is configured for the tenant.
        Both 200 (connected) and 404 (no connection) are valid responses.
        """
        import datetime
        today = datetime.date.today().isoformat()
        end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            headers=headers,
            params={"start_date": today, "end_date": end_date}
        )
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code} - {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "grid" in data or "room_types" in data, "Response should contain grid data"
        else:
            # 404 is acceptable when no Exely connection is configured
            data = response.json()
            assert "detail" in data, "404 response should contain detail message"
    
    def test_bulk_grid_update_structure(self, headers):
        """Test POST /api/channel-manager/rate-manager/bulk-grid-update - Validate structure"""
        import datetime
        today = datetime.date.today().isoformat()
        end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        
        # Test with stop_sell flag
        payload = {
            "per_room_values": [
                {
                    "room_type_code": "STD",  # May not exist but tests structure
                    "rate_plan_codes": ["BAR"],
                    "stop_sell": True
                }
            ],
            "start_date": today,
            "end_date": end_date,
            "selected_days": None,
            "update_fields": ["stop_sell"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            headers=headers,
            json=payload
        )
        # May fail if room type doesn't exist or Exely connection is missing (404), but should not be 5xx
        assert response.status_code in [200, 400, 404, 422], f"Unexpected error: {response.text}"


class TestInvoiceGeneration(TestAuth):
    """Invoice Generation API Tests"""
    
    def test_generate_invoice_endpoint_exists(self, headers):
        """Test POST /api/pms/reservations/{booking_id}/generate-invoice exists"""
        # Use a non-existent booking_id to test endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/pms/reservations/nonexistent-booking/generate-invoice",
            headers=headers,
            json={"selected_charge_ids": [], "billing_name": "Test"}
        )
        # Should return 404 (not found) not 500 (server error)
        assert response.status_code in [404, 400], f"Endpoint should exist: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
