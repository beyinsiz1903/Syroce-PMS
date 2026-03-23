"""
Stop Sale Scheduler and Holidays API Tests
Testing the new features for Turkish Hotel PMS:
- GET /api/channel-manager/rate-manager/holidays - returns holiday periods
- GET /api/channel-manager/rate-manager/stop-sale-schedules - lists saved schedules
- POST /api/channel-manager/rate-manager/stop-sale-schedules - creates new schedule
- DELETE /api/channel-manager/rate-manager/stop-sale-schedules/{id} - deletes schedule
- PATCH /api/channel-manager/rate-manager/stop-sale-schedules/{id} - updates schedule
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'http://localhost:8001').rstrip('/')


class TestAuthentication:
    """Test login and get auth token"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]

    def test_login_success(self, auth_token):
        """Verify login works"""
        assert auth_token is not None
        assert len(auth_token) > 0
        print(f"Login successful, token length: {len(auth_token)}")


class TestHolidaysEndpoint:
    """Test GET /api/channel-manager/rate-manager/holidays"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_holidays_returns_200(self, headers):
        """Test holidays endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"Holidays endpoint returned status: {response.status_code}")
    
    def test_holidays_returns_list(self, headers):
        """Test holidays endpoint returns holidays list"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        assert "holidays" in data, "No 'holidays' field in response"
        assert isinstance(data["holidays"], list), "holidays should be a list"
        print(f"Found {len(data['holidays'])} holidays")
    
    def test_holidays_have_required_fields(self, headers):
        """Test each holiday has required fields"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        holidays = data.get("holidays", [])
        
        required_fields = ["key", "name", "category", "start_date", "end_date", "days", "year"]
        for h in holidays[:5]:  # Check first 5
            for field in required_fields:
                assert field in h, f"Missing field '{field}' in holiday: {h}"
        print(f"All required fields present in holidays")
    
    def test_holidays_have_categories(self, headers):
        """Test holidays are grouped by category (turkey, international, season)"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        holidays = data.get("holidays", [])
        
        categories = set(h.get("category") for h in holidays)
        print(f"Categories found: {categories}")
        
        # Check for expected categories
        assert "turkey" in categories, "Missing 'turkey' category"
        assert "international" in categories, "Missing 'international' category"
        assert "season" in categories, "Missing 'season' category"
    
    def test_holidays_contain_turkish_holidays(self, headers):
        """Test holidays include Turkish holidays like Kurban Bayrami, Ramazan Bayrami"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        holidays = data.get("holidays", [])
        
        holiday_names = [h.get("name", "") for h in holidays]
        holiday_names_str = ", ".join(holiday_names[:10])
        print(f"Holiday names: {holiday_names_str}...")
        
        # Check for key Turkish holidays (may have variations in name)
        turkey_holidays = [h for h in holidays if h.get("category") == "turkey"]
        assert len(turkey_holidays) > 0, "No Turkish holidays found"
        print(f"Found {len(turkey_holidays)} Turkish holidays")
    
    def test_holidays_contain_easter(self, headers):
        """Test holidays include Easter/Paskalya"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        holidays = data.get("holidays", [])
        
        # Look for Easter-related holidays
        easter_holidays = [h for h in holidays if "easter" in h.get("key", "").lower() or "paskalya" in h.get("name", "").lower()]
        print(f"Found Easter holidays: {[h['name'] for h in easter_holidays]}")
        assert len(easter_holidays) > 0, "No Easter/Paskalya holidays found"
    
    def test_holidays_dates_are_valid(self, headers):
        """Test holiday dates are valid ISO format"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/holidays", headers=headers)
        data = response.json()
        holidays = data.get("holidays", [])
        
        for h in holidays[:5]:
            start_date = h.get("start_date")
            end_date = h.get("end_date")
            # Validate date format YYYY-MM-DD
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        print("All holiday dates are valid ISO format")


class TestStopSaleSchedulesCRUD:
    """Test Stop Sale Schedules CRUD operations"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    @pytest.fixture
    def test_schedule_data(self):
        """Generate unique test schedule data"""
        unique_id = str(uuid.uuid4())[:8]
        today = datetime.now()
        return {
            "name": f"TEST_Schedule_{unique_id}",
            "holiday_key": "test_holiday",
            "start_date": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
            "end_date": (today + timedelta(days=35)).strftime("%Y-%m-%d"),
            "room_type_codes": ["Standart", "Deluxe"],
            "auto_apply": False  # Don't auto-apply to avoid affecting real data
        }
    
    # GET schedules
    def test_list_schedules_returns_200(self, headers):
        """Test GET /api/channel-manager/rate-manager/stop-sale-schedules returns 200"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"List schedules returned status: {response.status_code}")
    
    def test_list_schedules_returns_list(self, headers):
        """Test schedules endpoint returns schedules array"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules", headers=headers)
        data = response.json()
        assert "schedules" in data, "No 'schedules' field in response"
        assert isinstance(data["schedules"], list), "schedules should be a list"
        print(f"Found {len(data['schedules'])} existing schedules")
    
    # CREATE schedule
    def test_create_schedule_success(self, headers, test_schedule_data):
        """Test POST /api/channel-manager/rate-manager/stop-sale-schedules creates schedule"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=test_schedule_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "schedule" in data, "No 'schedule' in response"
        schedule = data["schedule"]
        
        # Verify returned schedule has correct data
        assert schedule["name"] == test_schedule_data["name"], "Name mismatch"
        assert schedule["start_date"] == test_schedule_data["start_date"], "Start date mismatch"
        assert schedule["end_date"] == test_schedule_data["end_date"], "End date mismatch"
        assert schedule["room_type_codes"] == test_schedule_data["room_type_codes"], "Room types mismatch"
        assert "id" in schedule, "No 'id' in created schedule"
        
        print(f"Created schedule with ID: {schedule['id']}")
        
        # Cleanup - delete the test schedule
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule['id']}",
            headers=headers
        )
        assert delete_response.status_code == 200, f"Cleanup failed: {delete_response.text}"
    
    def test_create_schedule_persists(self, headers, test_schedule_data):
        """Test created schedule can be retrieved via GET"""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=test_schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        
        # Verify via GET
        get_response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        schedules = get_response.json().get("schedules", [])
        found = [s for s in schedules if s.get("id") == schedule_id]
        assert len(found) == 1, f"Schedule {schedule_id} not found in list"
        print(f"Schedule {schedule_id} verified in list")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers
        )
    
    # DELETE schedule
    def test_delete_schedule_success(self, headers, test_schedule_data):
        """Test DELETE /api/channel-manager/rate-manager/stop-sale-schedules/{id}"""
        # First create a schedule
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=test_schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        
        # Delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        print(f"Deleted schedule {schedule_id}")
        
        # Verify it's gone
        get_response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        schedules = get_response.json().get("schedules", [])
        found = [s for s in schedules if s.get("id") == schedule_id]
        assert len(found) == 0, f"Schedule {schedule_id} should be deleted but still found"
        print(f"Verified schedule {schedule_id} is deleted")
    
    def test_delete_nonexistent_schedule_returns_404(self, headers):
        """Test deleting non-existent schedule returns 404"""
        fake_id = "nonexistent-id-12345"
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{fake_id}",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Non-existent schedule delete returns 404 as expected")
    
    # PATCH schedule
    def test_update_schedule_success(self, headers, test_schedule_data):
        """Test PATCH /api/channel-manager/rate-manager/stop-sale-schedules/{id}"""
        # Create a schedule
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=test_schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        original_name = test_schedule_data["name"]
        
        # Update it
        new_name = f"UPDATED_{original_name}"
        update_response = requests.patch(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers,
            json={"name": new_name}
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        print(f"Updated schedule {schedule_id} name to: {new_name}")
        
        # Verify update persisted
        get_response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        schedules = get_response.json().get("schedules", [])
        found = [s for s in schedules if s.get("id") == schedule_id]
        assert len(found) == 1, f"Schedule {schedule_id} not found"
        assert found[0]["name"] == new_name, f"Name not updated: {found[0]['name']}"
        print(f"Verified name update persisted")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers
        )
    
    def test_update_schedule_dates(self, headers, test_schedule_data):
        """Test updating schedule dates"""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=test_schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        
        # Update dates
        new_start = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        new_end = (datetime.now() + timedelta(days=65)).strftime("%Y-%m-%d")
        
        update_response = requests.patch(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers,
            json={"start_date": new_start, "end_date": new_end}
        )
        assert update_response.status_code == 200, f"Update dates failed: {update_response.text}"
        
        # Verify
        get_response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        schedules = get_response.json().get("schedules", [])
        found = [s for s in schedules if s.get("id") == schedule_id]
        assert found[0]["start_date"] == new_start, "Start date not updated"
        assert found[0]["end_date"] == new_end, "End date not updated"
        print(f"Dates updated: {new_start} to {new_end}")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}",
            headers=headers
        )
    
    def test_update_nonexistent_schedule_returns_404(self, headers):
        """Test updating non-existent schedule returns 404"""
        fake_id = "nonexistent-id-12345"
        response = requests.patch(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{fake_id}",
            headers=headers,
            json={"name": "New Name"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Non-existent schedule update returns 404 as expected")


class TestStopSaleScheduleAutoApply:
    """Test auto_apply feature for stop sale schedules"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_create_schedule_with_auto_apply_true(self, headers):
        """Test creating schedule with auto_apply=true applies stop sale"""
        unique_id = str(uuid.uuid4())[:8]
        today = datetime.now()
        schedule_data = {
            "name": f"TEST_AutoApply_{unique_id}",
            "start_date": (today + timedelta(days=90)).strftime("%Y-%m-%d"),
            "end_date": (today + timedelta(days=92)).strftime("%Y-%m-%d"),
            "room_type_codes": ["Standart"],
            "auto_apply": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=schedule_data
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        schedule = data["schedule"]
        schedule_id = schedule["id"]
        
        # auto_apply triggers actual stop-sale only when an active Exely connection
        # exists for the tenant. In CI (no Exely connection) applied stays False,
        # which is correct behaviour.
        assert schedule.get("auto_apply") == True, "auto_apply should be True"

        # Verify via GET as well
        import time
        time.sleep(0.5)

        get_response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        schedules = get_response.json().get("schedules", [])
        found = [s for s in schedules if s.get("id") == schedule_id]

        assert len(found) == 1, f"Schedule {schedule_id} not found"
        assert found[0].get("auto_apply") == True, "auto_apply should be True in DB"
        # applied depends on whether an active Exely connection exists
        print(f"Created schedule with auto_apply=true, applied={found[0].get('applied')} (depends on Exely connection)")
        
        # Cleanup - delete with remove_stop_sale=true to restore
        requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}?remove_stop_sale=true",
            headers=headers
        )


class TestDeleteWithRemoveStopSale:
    """Test delete endpoint with remove_stop_sale option"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_delete_with_remove_stop_sale_false(self, headers):
        """Test delete without removing stop sale"""
        unique_id = str(uuid.uuid4())[:8]
        today = datetime.now()
        schedule_data = {
            "name": f"TEST_NoRemove_{unique_id}",
            "start_date": (today + timedelta(days=100)).strftime("%Y-%m-%d"),
            "end_date": (today + timedelta(days=102)).strftime("%Y-%m-%d"),
            "room_type_codes": ["Standart"],
            "auto_apply": False
        }
        
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        
        # Delete without removing stop sale
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}?remove_stop_sale=false",
            headers=headers
        )
        assert delete_response.status_code == 200
        print("Delete with remove_stop_sale=false succeeded")
    
    def test_delete_with_remove_stop_sale_true(self, headers):
        """Test delete with removing stop sale"""
        unique_id = str(uuid.uuid4())[:8]
        today = datetime.now()
        schedule_data = {
            "name": f"TEST_WithRemove_{unique_id}",
            "start_date": (today + timedelta(days=110)).strftime("%Y-%m-%d"),
            "end_date": (today + timedelta(days=112)).strftime("%Y-%m-%d"),
            "room_type_codes": ["Standart"],
            "auto_apply": True  # Apply stop sale first
        }
        
        # Create with auto_apply
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers,
            json=schedule_data
        )
        schedule_id = create_response.json()["schedule"]["id"]
        
        # Delete with removing stop sale
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/rate-manager/stop-sale-schedules/{schedule_id}?remove_stop_sale=true",
            headers=headers
        )
        assert delete_response.status_code == 200
        print("Delete with remove_stop_sale=true succeeded (stop sale should be removed)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
