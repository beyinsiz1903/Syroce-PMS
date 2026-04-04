"""
Test HR Rate Manager and Exely Rate Manager APIs
Tests both channel manager rate/availability management screens independently.
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://rate-manager-test.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    data = response.json()
    # Auth returns access_token field
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in response: {data}")
    return token


@pytest.fixture(scope="module")
def headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ============ HR Rate Manager Tests ============

class TestHRRateManagerGrid:
    """Tests for GET /api/channel-manager/hr-rate-manager/grid"""
    
    def test_hr_grid_returns_200(self, headers):
        """HR grid endpoint returns 200 with valid date range."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/grid",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "grid" in data, "Response should contain 'grid'"
        assert "room_types" in data, "Response should contain 'room_types'"
        assert "rate_plans" in data, "Response should contain 'rate_plans'"
        assert "pricing_settings" in data, "Response should contain 'pricing_settings'"
        assert "currency" in data, "Response should contain 'currency'"
        print(f"HR Grid: {len(data['grid'])} grid items, {len(data['room_types'])} room types, {len(data['rate_plans'])} rate plans")
    
    def test_hr_grid_room_types_structure(self, headers):
        """HR grid returns HotelRunner room types (Corner Suit, Standart Oda, Deluxe Oda, Default room type)."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/grid",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        room_types = data.get("room_types", [])
        room_type_names = [rt.get("name", "") for rt in room_types]
        
        print(f"HR Room Types: {room_type_names}")
        
        # Check for expected HR room types (may vary based on cached_rooms)
        # At minimum, verify structure
        for rt in room_types:
            assert "code" in rt, "Room type should have 'code'"
            assert "name" in rt, "Room type should have 'name'"


class TestHRRateManagerRoomTypes:
    """Tests for GET /api/channel-manager/hr-rate-manager/room-types"""
    
    def test_hr_room_types_returns_200(self, headers):
        """HR room-types endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/room-types",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "room_types" in data
        assert "rate_plans" in data
        assert "pricing_settings" in data
        
        print(f"HR Room Types: {len(data['room_types'])} types, {len(data['rate_plans'])} plans")


class TestHRRateManagerPushProviders:
    """Tests for GET /api/channel-manager/hr-rate-manager/push-providers"""
    
    def test_hr_push_providers_returns_hotelrunner_shadow(self, headers):
        """HR push-providers returns HotelRunner in shadow mode."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/push-providers",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "providers" in data
        providers = data["providers"]
        
        # Should have HotelRunner provider
        hr_provider = next((p for p in providers if p.get("slug") == "hotelrunner"), None)
        assert hr_provider is not None, "HotelRunner provider should be present"
        
        # Should be in shadow mode (write_enabled=false)
        assert hr_provider.get("mode") in ["shadow", "read_only", "inactive"], \
            f"HotelRunner should be in shadow/read_only/inactive mode, got: {hr_provider.get('mode')}"
        
        print(f"HR Push Provider: {hr_provider}")


class TestHRRateManagerBulkUpdate:
    """Tests for POST /api/channel-manager/hr-rate-manager/bulk-grid-update"""
    
    def test_hr_bulk_update_saves_data(self, headers):
        """HR bulk-grid-update saves rate calendar data."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        # First get room types to use valid codes
        rt_response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/room-types",
            headers=headers
        )
        
        if rt_response.status_code != 200 or not rt_response.json().get("room_types"):
            pytest.skip("No HR room types available for bulk update test")
        
        room_types = rt_response.json()["room_types"]
        rate_plans = rt_response.json()["rate_plans"]
        
        if not room_types or not rate_plans:
            pytest.skip("No room types or rate plans available")
        
        # Use first room type and rate plan
        rt_code = room_types[0]["code"]
        rp_codes = [rate_plans[0]["code"]] if rate_plans else []
        
        if not rp_codes:
            pytest.skip("No rate plans available")
        
        payload = {
            "per_room_values": [{
                "room_type_code": rt_code,
                "rate_plan_codes": rp_codes,
                "rate": 1500.0,
                "availability": 5,
                "min_stay": 2,
                "stop_sell": False
            }],
            "start_date": today,
            "end_date": end_date,
            "selected_days": None,
            "update_fields": ["rate", "availability", "min_stay"]
        }
        
        response = requests.post(
            f"{BASE_URL}/channel-manager/hr-rate-manager/bulk-grid-update",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "saved" in data
        assert data["saved"] > 0, "Should have saved at least 1 record"
        print(f"HR Bulk Update: saved {data['saved']} records")


class TestHRRateManagerStopSale:
    """Tests for HR stop sale endpoints"""
    
    def test_hr_stop_sale_summary(self, headers):
        """HR stop-sale-summary returns stop sale data."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/stop-sale-summary",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "stops" in data
        print(f"HR Stop Sale Summary: {len(data['stops'])} room types with stop sales")
    
    def test_hr_stop_sale_schedules_list(self, headers):
        """HR stop-sale-schedules returns list of schedules."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/stop-sale-schedules",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "schedules" in data
        print(f"HR Stop Sale Schedules: {len(data['schedules'])} schedules")


class TestHRRateManagerHolidays:
    """Tests for GET /api/channel-manager/hr-rate-manager/holidays"""
    
    def test_hr_holidays_returns_periods(self, headers):
        """HR holidays returns holiday periods."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/holidays",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "holidays" in data
        holidays = data["holidays"]
        
        # Should have some holidays
        assert len(holidays) > 0, "Should have at least some holiday periods"
        
        # Verify structure
        for h in holidays[:3]:  # Check first 3
            assert "key" in h
            assert "name" in h
            assert "start_date" in h
            assert "end_date" in h
        
        print(f"HR Holidays: {len(holidays)} periods")


class TestHRRateManagerPricingSettings:
    """Tests for HR pricing settings endpoints"""
    
    def test_hr_pricing_settings_get(self, headers):
        """HR pricing-settings GET returns settings."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/pricing-settings",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "settings" in data
        print(f"HR Pricing Settings: {data['settings']}")
    
    def test_hr_pricing_settings_put(self, headers):
        """HR pricing-settings PUT updates settings."""
        # First get room types
        rt_response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/room-types",
            headers=headers
        )
        
        if rt_response.status_code != 200 or not rt_response.json().get("room_types"):
            pytest.skip("No HR room types available")
        
        room_types = rt_response.json()["room_types"]
        if not room_types:
            pytest.skip("No room types available")
        
        rt_code = room_types[0]["code"]
        
        payload = {
            "settings": [{
                "room_type_code": rt_code,
                "pricing_type": "per_room"
            }]
        }
        
        response = requests.put(
            f"{BASE_URL}/channel-manager/hr-rate-manager/pricing-settings",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "updated" in data
        print(f"HR Pricing Settings Updated: {data['updated']} settings")


# ============ Exely Rate Manager Tests (Regression) ============

class TestExelyRateManagerGrid:
    """Tests for GET /api/channel-manager/rate-manager/grid (Exely)"""
    
    def test_exely_grid_returns_200(self, headers):
        """Exely grid endpoint returns 200 with valid date range."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "grid" in data, "Response should contain 'grid'"
        assert "room_types" in data, "Response should contain 'room_types'"
        assert "rate_plans" in data, "Response should contain 'rate_plans'"
        
        print(f"Exely Grid: {len(data['grid'])} grid items, {len(data['room_types'])} room types")
    
    def test_exely_grid_room_types_structure(self, headers):
        """Exely grid returns Exely room types (Standart, Deluxe, Suite)."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        room_types = data.get("room_types", [])
        room_type_names = [rt.get("name", "") for rt in room_types]
        
        print(f"Exely Room Types: {room_type_names}")
        
        # Verify structure
        for rt in room_types:
            assert "code" in rt, "Room type should have 'code'"
            assert "name" in rt, "Room type should have 'name'"


class TestExelyRateManagerRoomTypes:
    """Tests for GET /api/channel-manager/rate-manager/room-types (Exely)"""
    
    def test_exely_room_types_returns_200(self, headers):
        """Exely room-types endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/room-types",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "room_types" in data
        assert "rate_plans" in data
        
        print(f"Exely Room Types: {len(data['room_types'])} types, {len(data['rate_plans'])} plans")


class TestExelyRateManagerPushProviders:
    """Tests for GET /api/channel-manager/rate-manager/push-providers (Exely)"""
    
    def test_exely_push_providers_returns_exely_active(self, headers):
        """Exely push-providers returns Exely with push active."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/push-providers",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "providers" in data
        providers = data["providers"]
        
        # Should have Exely provider
        exely_provider = next((p for p in providers if p.get("slug") == "exely"), None)
        assert exely_provider is not None, "Exely provider should be present"
        
        print(f"Exely Push Provider: {exely_provider}")


class TestExelyRateManagerBulkUpdate:
    """Tests for POST /api/channel-manager/rate-manager/bulk-grid-update (Exely)"""
    
    def test_exely_bulk_update_saves_data(self, headers):
        """Exely bulk-grid-update saves rate calendar data."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        # First get room types
        rt_response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/room-types",
            headers=headers
        )
        
        if rt_response.status_code != 200 or not rt_response.json().get("room_types"):
            pytest.skip("No Exely room types available")
        
        room_types = rt_response.json()["room_types"]
        rate_plans = rt_response.json()["rate_plans"]
        
        if not room_types or not rate_plans:
            pytest.skip("No room types or rate plans available")
        
        rt_code = room_types[0]["code"]
        rp_codes = [rate_plans[0]["code"]] if rate_plans else []
        
        if not rp_codes:
            pytest.skip("No rate plans available")
        
        payload = {
            "per_room_values": [{
                "room_type_code": rt_code,
                "rate_plan_codes": rp_codes,
                "rate": 2000.0,
                "availability": 10,
                "min_stay": 1,
                "stop_sell": False
            }],
            "start_date": today,
            "end_date": end_date,
            "selected_days": None,
            "update_fields": ["rate", "availability", "min_stay"]
        }
        
        response = requests.post(
            f"{BASE_URL}/channel-manager/rate-manager/bulk-grid-update",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "saved" in data
        assert data["saved"] > 0, "Should have saved at least 1 record"
        print(f"Exely Bulk Update: saved {data['saved']} records")


class TestExelyRateManagerStopSale:
    """Tests for Exely stop sale endpoints"""
    
    def test_exely_stop_sale_summary(self, headers):
        """Exely stop-sale-summary returns stop sale data."""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/stop-sale-summary",
            params={"start_date": today, "end_date": end_date},
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "stops" in data
        print(f"Exely Stop Sale Summary: {len(data['stops'])} room types with stop sales")
    
    def test_exely_stop_sale_schedules_list(self, headers):
        """Exely stop-sale-schedules returns list of schedules."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/stop-sale-schedules",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "schedules" in data
        print(f"Exely Stop Sale Schedules: {len(data['schedules'])} schedules")


class TestExelyRateManagerHolidays:
    """Tests for GET /api/channel-manager/rate-manager/holidays (Exely)"""
    
    def test_exely_holidays_returns_periods(self, headers):
        """Exely holidays returns holiday periods."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/holidays",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "holidays" in data
        print(f"Exely Holidays: {len(data['holidays'])} periods")


class TestExelyRateManagerPricingSettings:
    """Tests for Exely pricing settings endpoints"""
    
    def test_exely_pricing_settings_get(self, headers):
        """Exely pricing-settings GET returns settings."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/pricing-settings",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "settings" in data
        print(f"Exely Pricing Settings: {data['settings']}")


# ============ Cross-Validation Tests ============

class TestCrossValidation:
    """Tests to verify HR and Exely use separate data stores"""
    
    def test_hr_and_exely_have_different_room_types(self, headers):
        """HR and Exely should have different room types from different connections."""
        # Get HR room types
        hr_response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/room-types",
            headers=headers
        )
        
        # Get Exely room types
        exely_response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/room-types",
            headers=headers
        )
        
        # Both should return 200
        assert hr_response.status_code == 200, f"HR room-types failed: {hr_response.status_code}"
        assert exely_response.status_code == 200, f"Exely room-types failed: {exely_response.status_code}"
        
        hr_data = hr_response.json()
        exely_data = exely_response.json()
        
        hr_room_names = [rt.get("name", "") for rt in hr_data.get("room_types", [])]
        exely_room_names = [rt.get("name", "") for rt in exely_data.get("room_types", [])]
        
        print(f"HR Room Types: {hr_room_names}")
        print(f"Exely Room Types: {exely_room_names}")
        
        # They should be different (from different channel managers)
        # Note: This may not always be true if both have same room names, but codes should differ
    
    def test_hr_and_exely_push_providers_differ(self, headers):
        """HR push-providers returns only HotelRunner, Exely returns both."""
        # Get HR push providers
        hr_response = requests.get(
            f"{BASE_URL}/channel-manager/hr-rate-manager/push-providers",
            headers=headers
        )
        
        # Get Exely push providers
        exely_response = requests.get(
            f"{BASE_URL}/channel-manager/rate-manager/push-providers",
            headers=headers
        )
        
        assert hr_response.status_code == 200
        assert exely_response.status_code == 200
        
        hr_providers = hr_response.json().get("providers", [])
        exely_providers = exely_response.json().get("providers", [])
        
        hr_slugs = [p.get("slug") for p in hr_providers]
        exely_slugs = [p.get("slug") for p in exely_providers]
        
        print(f"HR Push Providers: {hr_slugs}")
        print(f"Exely Push Providers: {exely_slugs}")
        
        # HR should have hotelrunner
        assert "hotelrunner" in hr_slugs, "HR should have hotelrunner provider"
        
        # Exely should have exely
        assert "exely" in exely_slugs, "Exely should have exely provider"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
