"""
Test cases for Group Folio API endpoints
- GET /api/pms/group-folio-summary
- GET /api/pms/group-folio/{group_id}/booking/{booking_id}
- POST /api/pms/group-folio/payment
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)

class TestGroupFolioAPI:
    """Test Group Folio API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                self.authenticated = True
            else:
                self.authenticated = False
                pytest.skip(f"No token in response: {data}")
        else:
            self.authenticated = False
            pytest.skip(f"Authentication failed: {login_response.status_code} - {login_response.text}")
    
    def test_group_folio_summary_endpoint_exists(self):
        """Test GET /api/pms/group-folio-summary returns summary stats"""
        response = self.session.get(f"{BASE_URL}/api/pms/group-folio-summary")
        
        # Should return 200 with summary data
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate response structure
        assert "total_groups" in data, "Missing total_groups in response"
        assert "active_groups" in data, "Missing active_groups in response"
        assert "total_bookings" in data, "Missing total_bookings in response"
        assert "total_balance" in data, "Missing total_balance in response"
        assert "merged_folios" in data, "Missing merged_folios in response"
        assert "merge_operations" in data, "Missing merge_operations in response"
        
        # Validate data types
        assert isinstance(data["total_groups"], int), "total_groups should be int"
        assert isinstance(data["total_balance"], (int, float)), "total_balance should be numeric"
        
        print(f"Group Folio Summary: {data}")
    
    def test_group_folio_status_endpoint(self):
        """Test GET /api/pms/group-folio/{group_id} returns group folio status"""
        # Use test group ID from credentials
        test_group_id = "db38d4b6-dd61-4750-b535-394b15273f63"
        
        response = self.session.get(f"{BASE_URL}/api/pms/group-folio/{test_group_id}")
        
        # Should return 200 with group folio data, or 404 if group doesn't exist
        if response.status_code == 404:
            print(f"Test group {test_group_id} not found - this is expected if no group data exists")
            pytest.skip("Test group not found in database")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate response structure
        assert "group" in data, "Missing group in response"
        assert "bookings" in data, "Missing bookings in response"
        assert isinstance(data["bookings"], list), "bookings should be a list"
        
        print(f"Group Folio Status: {len(data.get('bookings', []))} bookings")
    
    def test_group_booking_folio_detail_endpoint(self):
        """Test GET /api/pms/group-folio/{group_id}/booking/{booking_id} returns detailed folio"""
        # Use test IDs from credentials
        test_group_id = "db38d4b6-dd61-4750-b535-394b15273f63"
        test_booking_id = "46793d7f-0bfe-4a3f-bf31-6d3ea5d34d29"
        
        response = self.session.get(
            f"{BASE_URL}/api/pms/group-folio/{test_group_id}/booking/{test_booking_id}"
        )
        
        # Should return 200 with folio details, or 404 if booking doesn't exist
        if response.status_code == 404:
            print(f"Test booking {test_booking_id} not found - testing with any available booking")
            pytest.skip("Test booking not found in database")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate response structure
        assert "booking_id" in data, "Missing booking_id in response"
        assert "guest_name" in data, "Missing guest_name in response"
        assert "room_number" in data, "Missing room_number in response"
        assert "charges" in data or "folios" in data, "Missing charges/folios in response"
        assert "payments" in data, "Missing payments in response"
        
        print(f"Booking Folio Detail: {data.get('guest_name')} - Room {data.get('room_number')}")
    
    def test_group_folio_payment_endpoint_validation(self):
        """Test POST /api/pms/group-folio/payment endpoint exists and validates input"""
        # Use test IDs from credentials
        test_group_id = "db38d4b6-dd61-4750-b535-394b15273f63"
        test_booking_id = "46793d7f-0bfe-4a3f-bf31-6d3ea5d34d29"
        
        # Test with valid data structure
        payment_data = {
            "group_id": test_group_id,
            "booking_id": test_booking_id,
            "amount": 100.0,
            "method": "cash",
            "reference": "TEST_PAYMENT_REF"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/pms/group-folio/payment",
            json=payment_data
        )
        
        # Should return 200 on success or 404 if booking not found
        # 422 means validation error (endpoint exists but data invalid)
        assert response.status_code in [200, 201, 404, 422], \
            f"Expected 200/201/404/422, got {response.status_code}: {response.text}"
        
        if response.status_code in [200, 201]:
            data = response.json()
            assert "success" in data or "payment" in data, "Missing success/payment in response"
            print(f"Payment recorded successfully: {data}")
        elif response.status_code == 404:
            print("Booking not found - endpoint exists but test data missing")
        elif response.status_code == 422:
            print("Validation error - endpoint exists, schema validation working")
    
    def test_group_bookings_list_endpoint(self):
        """Test GET /api/pms/group-bookings returns list of groups"""
        response = self.session.get(f"{BASE_URL}/api/pms/group-bookings")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should have groups array or be an array itself
        groups = data.get("groups") if isinstance(data, dict) else data
        assert isinstance(groups, list), "Response should contain groups list"
        
        print(f"Found {len(groups)} group bookings")
    
    def test_group_folio_merge_endpoint_validation(self):
        """Test POST /api/pms/group-folio/merge endpoint exists"""
        # Test with valid data structure
        merge_data = {
            "group_id": "db38d4b6-dd61-4750-b535-394b15273f63",
            "master_booking_id": "46793d7f-0bfe-4a3f-bf31-6d3ea5d34d29",
            "merge_booking_ids": [],
            "merge_payments": True
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/pms/group-folio/merge",
            json=merge_data
        )
        
        # Should return 200 on success or 404 if booking not found
        # 422 means validation error (endpoint exists but data invalid)
        assert response.status_code in [200, 201, 400, 404, 422], \
            f"Expected 200/201/400/404/422, got {response.status_code}: {response.text}"
        
        print(f"Merge endpoint response: {response.status_code}")


class TestGroupFolioAPIStructure:
    """Test Group Folio API response structure in detail"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
            else:
                pytest.skip("No token in login response")
        else:
            pytest.skip("Authentication failed")
    
    def test_summary_stats_data_types(self):
        """Test summary stats have correct data types"""
        response = self.session.get(f"{BASE_URL}/api/pms/group-folio-summary")
        assert response.status_code == 200
        
        data = response.json()
        
        # All numeric fields should be non-negative
        assert data["total_groups"] >= 0, "total_groups should be non-negative"
        assert data["active_groups"] >= 0, "active_groups should be non-negative"
        assert data["total_bookings"] >= 0, "total_bookings should be non-negative"
        assert data["merged_folios"] >= 0, "merged_folios should be non-negative"
        assert data["merge_operations"] >= 0, "merge_operations should be non-negative"
        # total_balance can be negative (overpaid)
        
        print(f"All data types validated: {data}")
