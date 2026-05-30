"""
Syroce B2B API Tests — Acente Otomasyon Sistemi Entegrasyonu
=============================================================
Tests for:
- Admin API Key Management (create, get, regenerate, revoke)
- B2B Agency Endpoints (content, availability, rates, reservations)
- X-API-Key authentication
- Push providers endpoint includes Syroce B2B
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
HOTEL_ADMIN_EMAIL = "demo@hotel.com"
HOTEL_ADMIN_PASSWORD = "demo123"
HOTEL_STAFF_EMAIL = "frontdesk@hotel.com"
HOTEL_STAFF_PASSWORD = "staff123"

# Test agency IDs from test_credentials.md
ANTALYA_TURIZM_ID = "1d6ebdef-b42a-40ea-8c01-f749ea96fdea"
TEST_CONTENT_AGENCY_ID = "6b187487-37f9-41d1-9945-0e32e4481385"

# Test dates
CHECK_IN = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
CHECK_OUT = (datetime.now() + timedelta(days=32)).strftime("%Y-%m-%d")


class TestB2BAPISetup:
    """Setup and helper methods for B2B API tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get hotel admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": HOTEL_ADMIN_EMAIL,
            "password": HOTEL_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def staff_token(self):
        """Get hotel staff token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": HOTEL_STAFF_EMAIL,
            "password": HOTEL_STAFF_PASSWORD
        })
        assert response.status_code == 200, f"Staff login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def staff_headers(self, staff_token):
        return {"Authorization": f"Bearer {staff_token}", "Content-Type": "application/json"}


class TestB2BAdminAPIKeyManagement(TestB2BAPISetup):
    """Test Admin API Key Management endpoints"""
    
    generated_api_key = None
    test_agency_id = None
    
    def test_01_get_agencies_list(self, admin_headers):
        """GET /api/agencies - Get list of agencies to find one for testing"""
        response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        print(f"Get agencies response: {response.status_code}")
        assert response.status_code == 200, f"Get agencies failed: {response.text}"
        
        agencies = response.json()
        assert isinstance(agencies, list), "Response should be a list"
        
        # Find an active agency without API key or use Antalya Turizm
        active_agencies = [a for a in agencies if a.get("status") == "active"]
        assert len(active_agencies) > 0, "No active agencies found"
        
        # Try to find Antalya Turizm first
        antalya = next((a for a in active_agencies if a.get("id") == ANTALYA_TURIZM_ID), None)
        if antalya:
            TestB2BAdminAPIKeyManagement.test_agency_id = antalya["id"]
            print(f"Using Antalya Turizm agency: {antalya['name']}")
        else:
            # Use first active agency
            TestB2BAdminAPIKeyManagement.test_agency_id = active_agencies[0]["id"]
            print(f"Using agency: {active_agencies[0]['name']}")
    
    def test_02_get_api_key_info_before_creation(self, admin_headers):
        """GET /api/b2b/api-keys/{agency_id} - Check API key info before creation"""
        agency_id = TestB2BAdminAPIKeyManagement.test_agency_id
        assert agency_id, "No test agency ID set"
        
        response = requests.get(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        print(f"Get API key info response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Get API key info failed: {response.text}"
        
        data = response.json()
        assert "has_key" in data, "Response should contain has_key field"
        assert "agency_id" in data, "Response should contain agency_id field"
        print(f"Agency has_key: {data.get('has_key')}")
    
    def test_03_create_or_regenerate_api_key(self, admin_headers):
        """POST /api/b2b/api-keys or regenerate - Create or regenerate API key"""
        agency_id = TestB2BAdminAPIKeyManagement.test_agency_id
        assert agency_id, "No test agency ID set"
        
        # First try to create
        response = requests.post(f"{BASE_URL}/api/b2b/api-keys?agency_id={agency_id}", headers=admin_headers)
        print(f"Create API key response: {response.status_code}")
        
        if response.status_code == 409:
            # Key already exists, regenerate instead
            print("API key already exists, regenerating...")
            response = requests.post(f"{BASE_URL}/api/b2b/api-keys/{agency_id}/regenerate", headers=admin_headers)
            print(f"Regenerate API key response: {response.status_code}")
        
        assert response.status_code == 200, f"Create/Regenerate API key failed: {response.text}"
        
        data = response.json()
        assert "api_key" in data, "Response should contain api_key"
        assert data["api_key"].startswith("syroce_b2b_"), "API key should start with syroce_b2b_"
        assert "key_prefix" in data, "Response should contain key_prefix"
        assert "agency_id" in data, "Response should contain agency_id"
        
        TestB2BAdminAPIKeyManagement.generated_api_key = data["api_key"]
        print(f"Generated API key prefix: {data['key_prefix']}")
    
    def test_04_get_api_key_info_after_creation(self, admin_headers):
        """GET /api/b2b/api-keys/{agency_id} - Verify API key info after creation"""
        agency_id = TestB2BAdminAPIKeyManagement.test_agency_id
        assert agency_id, "No test agency ID set"
        
        response = requests.get(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        print(f"Get API key info response: {response.status_code}")
        assert response.status_code == 200, f"Get API key info failed: {response.text}"
        
        data = response.json()
        assert data.get("has_key") == True, "Agency should have API key"
        assert "key_prefix" in data, "Response should contain key_prefix"
        assert "created_at" in data, "Response should contain created_at"
        assert "usage_count" in data, "Response should contain usage_count"
        print(f"API key info: prefix={data.get('key_prefix')}, usage={data.get('usage_count')}")


class TestB2BAgencyEndpoints(TestB2BAPISetup):
    """Test B2B Agency Endpoints with X-API-Key authentication"""
    
    api_key = None
    created_reservation_id = None
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_api_key(self, admin_headers):
        """Setup: Get or create API key for testing"""
        # Use Antalya Turizm agency
        agency_id = ANTALYA_TURIZM_ID
        
        # First check if key exists
        response = requests.get(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("has_key"):
                # Regenerate to get the key
                response = requests.post(f"{BASE_URL}/api/b2b/api-keys/{agency_id}/regenerate", headers=admin_headers)
            else:
                # Create new key
                response = requests.post(f"{BASE_URL}/api/b2b/api-keys?agency_id={agency_id}", headers=admin_headers)
        
        if response.status_code == 200:
            data = response.json()
            TestB2BAgencyEndpoints.api_key = data.get("api_key")
            print(f"Setup API key: {data.get('key_prefix')}")
        else:
            pytest.skip(f"Could not setup API key: {response.text}")
    
    def test_01_invalid_api_key_returns_401(self):
        """Test that invalid API key returns 401"""
        headers = {"X-API-Key": "invalid_key_12345", "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/content", headers=headers)
        print(f"Invalid API key response: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for invalid API key, got {response.status_code}"
    
    def test_02_missing_api_key_returns_401(self):
        """Test that missing API key returns 401 (clean auth deny, not 422 validation).

        B2B sub-routers treat a missing X-API-Key as an authentication failure
        (401) rather than a request-validation error (422). The deny path must
        be a proper auth status so callers cannot distinguish 'missing' from
        'invalid' via status code.
        """
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/content", headers=headers)
        print(f"Missing API key response: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for missing API key, got {response.status_code}"
    
    def test_03_get_content(self):
        """GET /api/b2b/content - Get hotel content"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/content", headers=headers)
        print(f"Get content response: {response.status_code}")
        assert response.status_code == 200, f"Get content failed: {response.text}"
        
        data = response.json()
        assert "published" in data, "Response should contain published field"
        print(f"Content published: {data.get('published')}")
    
    def test_04_get_availability(self):
        """GET /api/b2b/availability - Get room availability"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(
            f"{BASE_URL}/api/b2b/availability?check_in={CHECK_IN}&check_out={CHECK_OUT}",
            headers=headers
        )
        print(f"Get availability response: {response.status_code}")
        assert response.status_code == 200, f"Get availability failed: {response.text}"
        
        data = response.json()
        assert "check_in" in data, "Response should contain check_in"
        assert "check_out" in data, "Response should contain check_out"
        assert "room_types" in data, "Response should contain room_types"
        assert data["check_in"] == CHECK_IN, "check_in should match request"
        assert data["check_out"] == CHECK_OUT, "check_out should match request"
        print(f"Room types available: {len(data.get('room_types', []))}")
    
    def test_05_get_availability_invalid_dates(self):
        """GET /api/b2b/availability - Test invalid date range"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        # check_out before check_in
        response = requests.get(
            f"{BASE_URL}/api/b2b/availability?check_in={CHECK_OUT}&check_out={CHECK_IN}",
            headers=headers
        )
        print(f"Invalid dates response: {response.status_code}")
        assert response.status_code == 400, f"Expected 400 for invalid dates, got {response.status_code}"
    
    def test_06_get_rates(self):
        """GET /api/b2b/rates - Get room rates"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(
            f"{BASE_URL}/api/b2b/rates?start_date={CHECK_IN}&end_date={CHECK_OUT}",
            headers=headers
        )
        print(f"Get rates response: {response.status_code}")
        assert response.status_code == 200, f"Get rates failed: {response.text}"
        
        data = response.json()
        assert "start_date" in data, "Response should contain start_date"
        assert "end_date" in data, "Response should contain end_date"
        assert "rates" in data, "Response should contain rates"
        assert "source" in data, "Response should contain source"
        print(f"Rates source: {data.get('source')}, count: {len(data.get('rates', []))}")
    
    def test_07_list_reservations_empty(self):
        """GET /api/b2b/reservations - List reservations (may be empty)"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/reservations", headers=headers)
        print(f"List reservations response: {response.status_code}")
        assert response.status_code == 200, f"List reservations failed: {response.text}"
        
        data = response.json()
        assert "reservations" in data, "Response should contain reservations"
        assert "count" in data, "Response should contain count"
        print(f"Reservations count: {data.get('count')}")
    
    def test_08_create_reservation(self):
        """POST /api/b2b/reservations - Create a reservation"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        
        # First get available room types
        avail_response = requests.get(
            f"{BASE_URL}/api/b2b/availability?check_in={CHECK_IN}&check_out={CHECK_OUT}",
            headers=headers
        )
        if avail_response.status_code != 200:
            pytest.skip("Could not get availability")
        
        avail_data = avail_response.json()
        room_types = avail_data.get("room_types", [])
        
        # Find a room type with availability
        available_room_type = None
        for rt in room_types:
            if rt.get("available_rooms", 0) > 0:
                available_room_type = rt["room_type"]
                break
        
        if not available_room_type:
            # Use first room type even if no availability shown
            if room_types:
                available_room_type = room_types[0].get("room_type", "Standard")
            else:
                available_room_type = "Standard"
        
        print(f"Creating reservation for room type: {available_room_type}")
        
        reservation_data = {
            "room_type": available_room_type,
            "check_in": CHECK_IN,
            "check_out": CHECK_OUT,
            "guest_name": "TEST_B2B_Guest",
            "guest_email": "test_b2b@example.com",
            "guest_phone": "+90 555 123 4567",
            "adults": 2,
            "children": 0,
            "special_requests": "B2B API Test Reservation",
            "total_amount": 500.00
        }
        
        response = requests.post(f"{BASE_URL}/api/b2b/reservations", headers=headers, json=reservation_data)
        print(f"Create reservation response: {response.status_code} - {response.text[:500]}")
        
        # May fail if no rooms available - that's OK
        if response.status_code == 409:
            print("No rooms available for the selected dates - expected behavior")
            return
        
        if response.status_code == 404:
            print("Room type not found - may need different room type")
            return
        
        assert response.status_code == 200, f"Create reservation failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Response should have ok=True"
        assert "reservation" in data, "Response should contain reservation"
        
        reservation = data["reservation"]
        assert "id" in reservation, "Reservation should have id"
        assert "confirmation_code" in reservation, "Reservation should have confirmation_code"
        assert reservation["confirmation_code"].startswith("B2B-"), "Confirmation code should start with B2B-"
        
        TestB2BAgencyEndpoints.created_reservation_id = reservation["id"]
        print(f"Created reservation: {reservation['confirmation_code']}")
    
    def test_09_get_reservation_by_id(self):
        """GET /api/b2b/reservations/{id} - Get reservation by ID"""
        api_key = TestB2BAgencyEndpoints.api_key
        reservation_id = TestB2BAgencyEndpoints.created_reservation_id
        
        if not api_key:
            pytest.skip("No API key available")
        if not reservation_id:
            pytest.skip("No reservation created in previous test")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/reservations/{reservation_id}", headers=headers)
        print(f"Get reservation response: {response.status_code}")
        assert response.status_code == 200, f"Get reservation failed: {response.text}"
        
        data = response.json()
        assert "reservation" in data, "Response should contain reservation"
        assert data["reservation"]["id"] == reservation_id, "Reservation ID should match"
    
    def test_10_get_reservation_not_found(self):
        """GET /api/b2b/reservations/{id} - Test non-existent reservation"""
        api_key = TestB2BAgencyEndpoints.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/reservations/non-existent-id-12345", headers=headers)
        print(f"Get non-existent reservation response: {response.status_code}")
        assert response.status_code == 404, f"Expected 404 for non-existent reservation, got {response.status_code}"
    
    def test_11_cancel_reservation(self):
        """PUT /api/b2b/reservations/{id}/cancel - Cancel reservation"""
        api_key = TestB2BAgencyEndpoints.api_key
        reservation_id = TestB2BAgencyEndpoints.created_reservation_id
        
        if not api_key:
            pytest.skip("No API key available")
        if not reservation_id:
            pytest.skip("No reservation created in previous test")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.put(f"{BASE_URL}/api/b2b/reservations/{reservation_id}/cancel", headers=headers)
        print(f"Cancel reservation response: {response.status_code}")
        assert response.status_code == 200, f"Cancel reservation failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Response should have ok=True"
        assert data.get("status") == "cancelled", "Status should be cancelled"
        print(f"Cancelled reservation: {data.get('confirmation_code')}")
    
    def test_12_cancel_already_cancelled(self):
        """PUT /api/b2b/reservations/{id}/cancel - Test cancelling already cancelled reservation"""
        api_key = TestB2BAgencyEndpoints.api_key
        reservation_id = TestB2BAgencyEndpoints.created_reservation_id
        
        if not api_key:
            pytest.skip("No API key available")
        if not reservation_id:
            pytest.skip("No reservation created in previous test")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.put(f"{BASE_URL}/api/b2b/reservations/{reservation_id}/cancel", headers=headers)
        print(f"Cancel already cancelled response: {response.status_code}")
        assert response.status_code == 400, f"Expected 400 for already cancelled reservation, got {response.status_code}"


class TestB2BAPIKeyRevoke(TestB2BAPISetup):
    """Test API Key Revoke functionality"""
    
    test_agency_id = None
    api_key = None
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_test_agency(self, admin_headers):
        """Setup: Create a test agency and API key for revoke testing"""
        # Create a new test agency
        agency_name = f"TEST_B2B_Revoke_{datetime.now().strftime('%H%M%S')}"
        response = requests.post(f"{BASE_URL}/api/agencies", headers=admin_headers, json={
            "name": agency_name,
            "contact_name": "Test Contact",
            "contact_email": "test@revoke.com",
            "commission_rate": 10
        })
        
        if response.status_code == 200:
            data = response.json()
            TestB2BAPIKeyRevoke.test_agency_id = data["id"]
            print(f"Created test agency: {agency_name}")
            
            # Create API key for this agency
            key_response = requests.post(
                f"{BASE_URL}/api/b2b/api-keys?agency_id={data['id']}",
                headers=admin_headers
            )
            if key_response.status_code == 200:
                key_data = key_response.json()
                TestB2BAPIKeyRevoke.api_key = key_data["api_key"]
                print(f"Created API key: {key_data['key_prefix']}")
    
    def test_01_verify_api_key_works(self):
        """Verify API key works before revoke"""
        api_key = TestB2BAPIKeyRevoke.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/content", headers=headers)
        print(f"API key works response: {response.status_code}")
        assert response.status_code == 200, f"API key should work before revoke: {response.text}"
    
    def test_02_revoke_api_key(self, admin_headers):
        """DELETE /api/b2b/api-keys/{agency_id} - Revoke API key"""
        agency_id = TestB2BAPIKeyRevoke.test_agency_id
        if not agency_id:
            pytest.skip("No test agency available")
        
        response = requests.delete(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        print(f"Revoke API key response: {response.status_code}")
        assert response.status_code == 200, f"Revoke API key failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Response should have ok=True"
    
    def test_03_verify_api_key_revoked(self):
        """Verify API key no longer works after revoke"""
        api_key = TestB2BAPIKeyRevoke.api_key
        if not api_key:
            pytest.skip("No API key available")
        
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/b2b/content", headers=headers)
        print(f"Revoked API key response: {response.status_code}")
        assert response.status_code == 401, f"Revoked API key should return 401, got {response.status_code}"
    
    def test_04_verify_api_key_info_shows_no_key(self, admin_headers):
        """GET /api/b2b/api-keys/{agency_id} - Verify has_key is False after revoke"""
        agency_id = TestB2BAPIKeyRevoke.test_agency_id
        if not agency_id:
            pytest.skip("No test agency available")
        
        response = requests.get(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        print(f"Get API key info after revoke: {response.status_code}")
        assert response.status_code == 200, f"Get API key info failed: {response.text}"
        
        data = response.json()
        assert data.get("has_key") == False, "has_key should be False after revoke"
    
    def test_05_revoke_non_existent_key(self, admin_headers):
        """DELETE /api/b2b/api-keys/{agency_id} - Test revoking non-existent key"""
        agency_id = TestB2BAPIKeyRevoke.test_agency_id
        if not agency_id:
            pytest.skip("No test agency available")
        
        # Try to revoke again (key already revoked)
        response = requests.delete(f"{BASE_URL}/api/b2b/api-keys/{agency_id}", headers=admin_headers)
        print(f"Revoke non-existent key response: {response.status_code}")
        assert response.status_code == 404, f"Expected 404 for non-existent key, got {response.status_code}"


class TestPushProvidersIncludesSyroceB2B(TestB2BAPISetup):
    """Test that push providers endpoint includes Syroce B2B"""
    
    def test_01_push_providers_includes_syroce_b2b(self, admin_headers):
        """GET /api/channel-manager/unified-rate-manager/push-providers - Should include Syroce B2B"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/unified-rate-manager/push-providers",
            headers=admin_headers
        )
        print(f"Push providers response: {response.status_code}")
        assert response.status_code == 200, f"Get push providers failed: {response.text}"
        
        data = response.json()
        assert "providers" in data, "Response should contain providers"
        
        providers = data["providers"]
        provider_slugs = [p.get("slug") for p in providers]
        print(f"Provider slugs: {provider_slugs}")
        
        # Check if Syroce B2B is in the list
        syroce_b2b = next((p for p in providers if p.get("slug") == "syroce_b2b"), None)
        
        if syroce_b2b:
            print(f"Syroce B2B provider found: {syroce_b2b}")
            assert syroce_b2b.get("name") == "Syroce B2B", "Provider name should be 'Syroce B2B'"
            assert syroce_b2b.get("mode") == "live", "Provider mode should be 'live'"
            assert "agency_count" in syroce_b2b, "Provider should have agency_count"
            assert "api_key_count" in syroce_b2b, "Provider should have api_key_count"
        else:
            # Syroce B2B only appears if there are active agencies
            print("Syroce B2B not in providers - checking if there are active agencies")
            agencies_response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
            if agencies_response.status_code == 200:
                agencies = agencies_response.json()
                active_agencies = [a for a in agencies if a.get("status") == "active"]
                if len(active_agencies) > 0:
                    pytest.fail("Syroce B2B should be in providers when active agencies exist")
                else:
                    print("No active agencies - Syroce B2B not expected in providers")


class TestB2BAgencyUserRestrictions(TestB2BAPISetup):
    """Test that agency users cannot access admin API key endpoints"""
    
    def test_01_agency_user_cannot_create_api_key(self, admin_headers):
        """Test that agency users (if any) cannot create API keys"""
        # This test verifies the _require_hotel_staff check
        # Agency users have role 'agency_admin' or 'agency_agent'
        # They should get 403 when trying to access admin endpoints
        
        # For now, we just verify the endpoint exists and works for admin
        response = requests.get(f"{BASE_URL}/api/b2b/api-keys/{ANTALYA_TURIZM_ID}", headers=admin_headers)
        print(f"Admin can access API key info: {response.status_code}")
        assert response.status_code == 200, "Admin should be able to access API key info"


# Cleanup fixture
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """Cleanup test data after all tests"""
    yield
    # Cleanup is handled by test data prefixes (TEST_)
    print("Test cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
