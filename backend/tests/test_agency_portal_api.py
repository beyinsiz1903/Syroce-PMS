"""
Agency Portal API Tests — Acente Yonetim ve Portal Sistemi
============================================================
Tests for:
- Agency CRUD (Hotel Admin)
- Agency User Management
- Agency Portal Auth & Operations
- Hotel Content Management & Distribution
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

# Test agency data
TEST_AGENCY_NAME = f"TEST_Antalya_Turizm_{datetime.now().strftime('%H%M%S')}"
TEST_AGENCY_USER_EMAIL = f"test_agency_{datetime.now().strftime('%H%M%S')}@acente.com"
TEST_AGENCY_USER_PASSWORD = "acente123"


class TestAgencyPortalSetup:
    """Setup and helper methods"""
    
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


class TestAgencyCRUD(TestAgencyPortalSetup):
    """Test Agency CRUD operations (Hotel Admin)"""
    
    created_agency_id = None
    created_user_id = None
    
    def test_01_create_agency(self, admin_headers):
        """POST /api/agencies - Create new agency"""
        response = requests.post(f"{BASE_URL}/api/agencies", headers=admin_headers, json={
            "name": TEST_AGENCY_NAME,
            "contact_name": "Ahmet Yilmaz",
            "contact_email": "info@antalyaturizm.com",
            "contact_phone": "+90 242 555 1234",
            "commission_rate": 12.5,
            "notes": "Test agency for automated testing"
        })
        print(f"Create agency response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Create agency failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Agency ID not returned"
        assert data["name"] == TEST_AGENCY_NAME
        assert data["commission_rate"] == 12.5
        assert data["status"] == "active"
        
        TestAgencyCRUD.created_agency_id = data["id"]
        print(f"Created agency ID: {TestAgencyCRUD.created_agency_id}")
    
    def test_02_list_agencies(self, admin_headers):
        """GET /api/agencies - List all agencies"""
        response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        print(f"List agencies response: {response.status_code}")
        assert response.status_code == 200, f"List agencies failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Find our created agency
        found = any(a["id"] == TestAgencyCRUD.created_agency_id for a in data)
        assert found, "Created agency not found in list"
        print(f"Found {len(data)} agencies")
    
    def test_03_get_agency_detail(self, admin_headers):
        """GET /api/agencies/{agency_id} - Get agency detail"""
        agency_id = TestAgencyCRUD.created_agency_id
        assert agency_id, "No agency ID from previous test"
        
        response = requests.get(f"{BASE_URL}/api/agencies/{agency_id}", headers=admin_headers)
        print(f"Get agency detail response: {response.status_code}")
        assert response.status_code == 200, f"Get agency detail failed: {response.text}"
        
        data = response.json()
        assert data["id"] == agency_id
        assert data["name"] == TEST_AGENCY_NAME
    
    def test_04_update_agency(self, admin_headers):
        """PUT /api/agencies/{agency_id} - Update agency"""
        agency_id = TestAgencyCRUD.created_agency_id
        assert agency_id, "No agency ID from previous test"
        
        response = requests.put(f"{BASE_URL}/api/agencies/{agency_id}", headers=admin_headers, json={
            "commission_rate": 15.0,
            "notes": "Updated notes for testing"
        })
        print(f"Update agency response: {response.status_code}")
        assert response.status_code == 200, f"Update agency failed: {response.text}"
        
        data = response.json()
        assert data["commission_rate"] == 15.0
        assert "Updated notes" in data["notes"]
    
    def test_05_create_agency_user(self, admin_headers):
        """POST /api/agencies/{agency_id}/users - Create agency user"""
        agency_id = TestAgencyCRUD.created_agency_id
        assert agency_id, "No agency ID from previous test"
        
        response = requests.post(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers, json={
            "name": "Test Agency User",
            "email": TEST_AGENCY_USER_EMAIL,
            "password": TEST_AGENCY_USER_PASSWORD,
            "role": "agency_agent"
        })
        print(f"Create agency user response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Create agency user failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "User ID not returned"
        assert data["email"] == TEST_AGENCY_USER_EMAIL.lower()
        assert data["role"] == "agency_agent"
        assert "password" not in data, "Password should not be returned"
        
        TestAgencyCRUD.created_user_id = data["id"]
        print(f"Created agency user ID: {TestAgencyCRUD.created_user_id}")
    
    def test_06_list_agency_users(self, admin_headers):
        """GET /api/agencies/{agency_id}/users - List agency users"""
        agency_id = TestAgencyCRUD.created_agency_id
        assert agency_id, "No agency ID from previous test"
        
        response = requests.get(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers)
        print(f"List agency users response: {response.status_code}")
        assert response.status_code == 200, f"List agency users failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Find our created user
        found = any(u["id"] == TestAgencyCRUD.created_user_id for u in data)
        assert found, "Created user not found in list"
        print(f"Found {len(data)} agency users")


class TestAgencyPortalAuth(TestAgencyPortalSetup):
    """Test Agency Portal Authentication"""
    
    agency_token = None
    
    def test_01_agency_login_invalid_credentials(self):
        """POST /api/agency-portal/auth/login - Invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/agency-portal/auth/login", json={
            "email": "nonexistent@acente.com",
            "password": "wrongpassword"
        })
        print(f"Invalid login response: {response.status_code}")
        assert response.status_code == 401, f"Should return 401 for invalid credentials"
    
    def test_02_agency_login_hotel_user_rejected(self):
        """POST /api/agency-portal/auth/login - Hotel user should be rejected"""
        response = requests.post(f"{BASE_URL}/api/agency-portal/auth/login", json={
            "email": HOTEL_ADMIN_EMAIL,
            "password": HOTEL_ADMIN_PASSWORD
        })
        print(f"Hotel user login response: {response.status_code}")
        # Hotel users should be rejected - either 401 (not found as agency user) or 403 (forbidden)
        assert response.status_code in (401, 403), f"Hotel users should be rejected from agency portal, got {response.status_code}"
    
    def test_03_agency_login_success(self):
        """POST /api/agency-portal/auth/login - Valid agency user login"""
        # First ensure we have an agency user (from previous test class or create one)
        # Login as admin and create agency + user if needed
        admin_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": HOTEL_ADMIN_EMAIL,
            "password": HOTEL_ADMIN_PASSWORD
        })
        if admin_response.status_code != 200:
            pytest.skip("Admin login failed, cannot setup agency user")
        
        admin_data = admin_response.json()
        admin_token = admin_data.get("access_token") or admin_data.get("token")
        admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Check if we have an existing agency user or create one
        agencies_response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        agencies = agencies_response.json() if agencies_response.status_code == 200 else []
        
        agency_id = None
        agency_user_email = None
        agency_user_password = "acente123"
        
        if agencies:
            # Use first active agency
            for agency in agencies:
                if agency.get("status") == "active":
                    agency_id = agency["id"]
                    # Check for existing users
                    users_response = requests.get(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers)
                    if users_response.status_code == 200:
                        users = users_response.json()
                        if users:
                            agency_user_email = users[0].get("email")
                            break
        
        if not agency_id:
            # Create a new agency
            create_agency_response = requests.post(f"{BASE_URL}/api/agencies", headers=admin_headers, json={
                "name": f"TEST_Portal_Agency_{datetime.now().strftime('%H%M%S')}",
                "contact_name": "Portal Test",
                "commission_rate": 10.0
            })
            if create_agency_response.status_code == 200:
                agency_id = create_agency_response.json().get("id")
        
        if agency_id and not agency_user_email:
            # Create a new agency user
            agency_user_email = f"portal_test_{datetime.now().strftime('%H%M%S')}@acente.com"
            create_user_response = requests.post(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers, json={
                "name": "Portal Test User",
                "email": agency_user_email,
                "password": agency_user_password,
                "role": "agency_agent"
            })
            if create_user_response.status_code != 200:
                pytest.skip(f"Could not create agency user: {create_user_response.text}")
        
        if not agency_user_email:
            pytest.skip("No agency user available for testing")
        
        # Now test agency login
        response = requests.post(f"{BASE_URL}/api/agency-portal/auth/login", json={
            "email": agency_user_email,
            "password": agency_user_password
        })
        print(f"Agency login response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Agency login failed: {response.text}"
        
        data = response.json()
        assert "token" in data, "Token not returned"
        assert "user" in data, "User info not returned"
        assert "agency" in data, "Agency info not returned"
        assert data["user"]["role"] in ("agency_admin", "agency_agent")
        
        TestAgencyPortalAuth.agency_token = data["token"]
        print(f"Agency login successful for: {agency_user_email}")


class TestAgencyPortalOperations(TestAgencyPortalSetup):
    """Test Agency Portal Operations (Availability, Reservations)"""
    
    @pytest.fixture(scope="class")
    def agency_token(self, admin_headers):
        """Get or create agency user and return token"""
        # Get agencies
        agencies_response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        agencies = agencies_response.json() if agencies_response.status_code == 200 else []
        
        agency_id = None
        for agency in agencies:
            if agency.get("status") == "active":
                agency_id = agency["id"]
                break
        
        if not agency_id:
            # Create agency
            create_response = requests.post(f"{BASE_URL}/api/agencies", headers=admin_headers, json={
                "name": f"TEST_Ops_Agency_{datetime.now().strftime('%H%M%S')}",
                "commission_rate": 10.0
            })
            if create_response.status_code == 200:
                agency_id = create_response.json().get("id")
        
        if not agency_id:
            pytest.skip("Could not get/create agency")
        
        # Create agency user
        user_email = f"ops_test_{datetime.now().strftime('%H%M%S')}@acente.com"
        user_password = "acente123"
        
        create_user_response = requests.post(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers, json={
            "name": "Ops Test User",
            "email": user_email,
            "password": user_password,
            "role": "agency_agent"
        })
        
        if create_user_response.status_code != 200:
            pytest.skip(f"Could not create agency user: {create_user_response.text}")
        
        # Login as agency user
        login_response = requests.post(f"{BASE_URL}/api/agency-portal/auth/login", json={
            "email": user_email,
            "password": user_password
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Agency login failed: {login_response.text}")
        
        return login_response.json().get("token")
    
    @pytest.fixture(scope="class")
    def agency_headers(self, agency_token):
        return {"Authorization": f"Bearer {agency_token}", "Content-Type": "application/json"}
    
    def test_01_agency_profile(self, agency_headers):
        """GET /api/agency-portal/profile - Get agency profile"""
        response = requests.get(f"{BASE_URL}/api/agency-portal/profile", headers=agency_headers)
        print(f"Agency profile response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Get profile failed: {response.text}"
        
        data = response.json()
        assert "agency" in data, "Agency info not returned"
        assert "hotel" in data, "Hotel info not returned"
    
    def test_02_search_availability(self, agency_headers):
        """GET /api/agency-portal/availability - Search room availability"""
        check_in = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        
        response = requests.get(f"{BASE_URL}/api/agency-portal/availability", headers=agency_headers, params={
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2
        })
        print(f"Availability search response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Availability search failed: {response.text}"
        
        data = response.json()
        assert "check_in" in data
        assert "check_out" in data
        assert "room_types" in data
        assert isinstance(data["room_types"], list)
        print(f"Found {len(data['room_types'])} available room types")
    
    def test_03_search_availability_invalid_dates(self, agency_headers):
        """GET /api/agency-portal/availability - Invalid date range"""
        check_in = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")  # Before check_in
        
        response = requests.get(f"{BASE_URL}/api/agency-portal/availability", headers=agency_headers, params={
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2
        })
        print(f"Invalid dates response: {response.status_code}")
        assert response.status_code == 400, "Should return 400 for invalid date range"
    
    def test_04_create_reservation(self, agency_headers):
        """POST /api/agency-portal/reservations - Create reservation"""
        # First search for availability
        check_in = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=16)).strftime("%Y-%m-%d")
        
        avail_response = requests.get(f"{BASE_URL}/api/agency-portal/availability", headers=agency_headers, params={
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2
        })
        
        if avail_response.status_code != 200:
            pytest.skip("Could not search availability")
        
        room_types = avail_response.json().get("room_types", [])
        if not room_types:
            pytest.skip("No available room types")
        
        # Use first available room type
        room_type = room_types[0]["room_type"]
        
        # Use unique guest email to avoid duplicate key errors
        unique_guest_email = f"test_guest_{datetime.now().strftime('%H%M%S%f')}@example.com"
        
        response = requests.post(f"{BASE_URL}/api/agency-portal/reservations", headers=agency_headers, json={
            "room_type_id": room_type,
            "check_in": check_in,
            "check_out": check_out,
            "guest_name": "TEST_Agency_Guest",
            "guest_email": unique_guest_email,
            "guest_phone": "+90 555 123 4567",
            "adults": 2,
            "children": 0,
            "special_requests": "Early check-in if possible",
            "total_amount": 1000.0
        })
        print(f"Create reservation response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Create reservation failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Reservation creation not successful"
        assert "booking" in data, "Booking data not returned"
        assert "confirmation_code" in data["booking"], "Confirmation code not returned"
        assert data["booking"]["source_channel"] == "agency", "Source channel should be 'agency'"
        print(f"Created reservation: {data['booking']['confirmation_code']}")
    
    def test_05_list_reservations(self, agency_headers):
        """GET /api/agency-portal/reservations - List agency reservations"""
        response = requests.get(f"{BASE_URL}/api/agency-portal/reservations", headers=agency_headers)
        print(f"List reservations response: {response.status_code}")
        assert response.status_code == 200, f"List reservations failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} agency reservations")
        
        # Verify all reservations have agency source
        for res in data:
            assert res.get("source_channel") == "agency", "All reservations should have agency source"


class TestHotelContent(TestAgencyPortalSetup):
    """Test Hotel Content Management & Distribution"""
    
    def test_01_get_hotel_content(self, admin_headers):
        """GET /api/hotel-content - Get hotel content (auto-initializes)"""
        response = requests.get(f"{BASE_URL}/api/hotel-content", headers=admin_headers)
        print(f"Get hotel content response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Get hotel content failed: {response.text}"
        
        data = response.json()
        assert "tenant_id" in data, "Tenant ID not in content"
        assert "hotel_name" in data, "Hotel name not in content"
        assert "room_types" in data, "Room types not in content"
        print(f"Hotel content has {len(data.get('room_types', []))} room types")
    
    def test_02_update_hotel_content(self, admin_headers):
        """PUT /api/hotel-content - Update hotel content"""
        response = requests.put(f"{BASE_URL}/api/hotel-content", headers=admin_headers, json={
            "hotel_name": "Test Hotel Updated",
            "description": "A beautiful test hotel for automated testing",
            "address": "Test Street 123, Antalya",
            "phone": "+90 242 555 0000",
            "email": "info@testhotel.com",
            "images": [],
            "amenities": ["WiFi", "Pool", "Spa", "Restaurant"],
            "room_types": [
                {
                    "room_type": "Standard",
                    "name": "Standard Room",
                    "description": "Comfortable standard room",
                    "capacity": 2,
                    "base_price": 500,
                    "images": [],
                    "amenities": ["WiFi", "TV", "Minibar"],
                    "bed_type": "Double"
                }
            ],
            "services": [
                {"name": "Room Service", "description": "24/7 room service", "icon": "utensils"},
                {"name": "Spa", "description": "Full service spa", "icon": "spa"}
            ]
        })
        print(f"Update hotel content response: {response.status_code}")
        assert response.status_code == 200, f"Update hotel content failed: {response.text}"
        
        data = response.json()
        assert data["hotel_name"] == "Test Hotel Updated"
        assert len(data["amenities"]) == 4
    
    def test_03_distribute_content_no_agencies(self, admin_headers):
        """POST /api/hotel-content/distribute - No agencies selected"""
        response = requests.post(f"{BASE_URL}/api/hotel-content/distribute", headers=admin_headers, json={
            "agency_ids": []
        })
        print(f"Distribute no agencies response: {response.status_code}")
        assert response.status_code == 400, "Should return 400 when no agencies selected"
    
    def test_04_distribute_content_to_agencies(self, admin_headers):
        """POST /api/hotel-content/distribute - Distribute to agencies"""
        # First get agencies
        agencies_response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        agencies = agencies_response.json() if agencies_response.status_code == 200 else []
        
        active_agency_ids = [a["id"] for a in agencies if a.get("status") == "active"]
        
        if not active_agency_ids:
            pytest.skip("No active agencies to distribute to")
        
        response = requests.post(f"{BASE_URL}/api/hotel-content/distribute", headers=admin_headers, json={
            "agency_ids": active_agency_ids[:3]  # Distribute to up to 3 agencies
        })
        print(f"Distribute content response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"Distribute content failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True
        assert "distributed_to" in data
        print(f"Distributed to {data['distributed_to']} agencies")


class TestAgencyPortalContent(TestAgencyPortalSetup):
    """Test Agency Portal Content View"""
    
    @pytest.fixture(scope="class")
    def agency_with_content_token(self, admin_headers):
        """Create agency with published content and return token"""
        # Create agency
        create_agency_response = requests.post(f"{BASE_URL}/api/agencies", headers=admin_headers, json={
            "name": f"TEST_Content_Agency_{datetime.now().strftime('%H%M%S')}",
            "commission_rate": 10.0
        })
        
        if create_agency_response.status_code != 200:
            pytest.skip("Could not create agency")
        
        agency_id = create_agency_response.json().get("id")
        
        # Create agency user
        user_email = f"content_test_{datetime.now().strftime('%H%M%S')}@acente.com"
        user_password = "acente123"
        
        create_user_response = requests.post(f"{BASE_URL}/api/agencies/{agency_id}/users", headers=admin_headers, json={
            "name": "Content Test User",
            "email": user_email,
            "password": user_password,
            "role": "agency_agent"
        })
        
        if create_user_response.status_code != 200:
            pytest.skip("Could not create agency user")
        
        # Distribute content to this agency
        requests.post(f"{BASE_URL}/api/hotel-content/distribute", headers=admin_headers, json={
            "agency_ids": [agency_id]
        })
        
        # Login as agency user
        login_response = requests.post(f"{BASE_URL}/api/agency-portal/auth/login", json={
            "email": user_email,
            "password": user_password
        })
        
        if login_response.status_code != 200:
            pytest.skip("Agency login failed")
        
        return login_response.json().get("token")
    
    @pytest.fixture(scope="class")
    def agency_content_headers(self, agency_with_content_token):
        return {"Authorization": f"Bearer {agency_with_content_token}", "Content-Type": "application/json"}
    
    def test_01_view_published_content(self, agency_content_headers):
        """GET /api/agency-portal/content - View published hotel content"""
        response = requests.get(f"{BASE_URL}/api/agency-portal/content", headers=agency_content_headers)
        print(f"View content response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200, f"View content failed: {response.text}"
        
        data = response.json()
        assert "published" in data
        if data["published"]:
            assert "hotel_content" in data
            print("Agency can view published hotel content")
        else:
            print("No content published to this agency yet")


class TestAgencyReservationsHotelSide(TestAgencyPortalSetup):
    """Test Agency Reservations from Hotel Admin perspective"""
    
    def test_01_list_all_agency_reservations(self, admin_headers):
        """GET /api/agency-reservations - List all agency reservations"""
        response = requests.get(f"{BASE_URL}/api/agency-reservations", headers=admin_headers)
        print(f"List agency reservations response: {response.status_code}")
        assert response.status_code == 200, f"List agency reservations failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} agency reservations from hotel side")
        
        # All should have agency source
        for res in data:
            assert res.get("source_channel") == "agency"


class TestCleanup(TestAgencyPortalSetup):
    """Cleanup test data"""
    
    def test_cleanup_test_agencies(self, admin_headers):
        """Delete test agencies created during testing"""
        response = requests.get(f"{BASE_URL}/api/agencies", headers=admin_headers)
        if response.status_code != 200:
            return
        
        agencies = response.json()
        deleted_count = 0
        
        for agency in agencies:
            if agency["name"].startswith("TEST_"):
                # First delete users
                users_response = requests.get(f"{BASE_URL}/api/agencies/{agency['id']}/users", headers=admin_headers)
                if users_response.status_code == 200:
                    for user in users_response.json():
                        requests.delete(f"{BASE_URL}/api/agencies/users/{user['id']}", headers=admin_headers)
                
                # Then delete agency
                delete_response = requests.delete(f"{BASE_URL}/api/agencies/{agency['id']}", headers=admin_headers)
                if delete_response.status_code == 200:
                    deleted_count += 1
        
        print(f"Cleaned up {deleted_count} test agencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
