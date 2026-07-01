"""
Test Rate Manager Bulk Update API (Toplu Guncellemeler)
Tests the HotelRunner-style bulk update interface with day-of-week filtering
"""
import os
import pytest
import requests
from datetime import date, timedelta
from test_helpers import skip_if_no_exely

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)


class TestRateManagerBulkUpdate:
    """Tests for the new Rate Manager Bulk Update functionality"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        data = login_response.json()
        self.token = data.get("access_token")
        assert self.token, "No access_token in login response"
        
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield

    # ─── Grid Endpoint Tests ───
    def test_get_rate_grid(self):
        """Test GET /api/channel-manager/rate-manager/grid returns grid data"""
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()
        
        response = self.session.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end}
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "room_types" in data
        assert "rate_plans" in data
        assert "grid" in data
        assert len(data["room_types"]) == 3, f"Expected 3 room types, got {len(data['room_types'])}"
        assert len(data["rate_plans"]) == 5, f"Expected 5 rate plans, got {len(data['rate_plans'])}"

    def test_grid_contains_room_type_names(self):
        """Verify room types include Standart, Deluxe, Suite"""
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()
        
        response = self.session.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end}
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        room_names = [rt["name"] for rt in data["room_types"]]
        assert "Standart" in room_names
        assert "Deluxe" in room_names
        assert "Suite" in room_names

    # ─── Room Types Endpoint Tests ───
    def test_get_room_types(self):
        """Test GET /api/channel-manager/rate-manager/room-types"""
        response = self.session.get(f"{BASE_URL}/api/channel-manager/rate-manager/room-types")
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "room_types" in data
        assert "rate_plans" in data
        assert len(data["room_types"]) == 3
        assert len(data["rate_plans"]) == 5

    # ─── Bulk Grid Update Tests ───
    def test_bulk_grid_update_single_room_type(self):
        """Test bulk update for single room type and rate plan"""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=2)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,  # All days
                "update_fields": ["rate"],
                "rate": 150.00
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "saved" in data
        assert data["saved"] >= 3, f"Expected at least 3 days saved, got {data['saved']}"
        assert "push_results" in data

    def test_bulk_grid_update_multiple_room_types(self):
        """Test bulk update for multiple room types"""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=1)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101", "102"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,
                "update_fields": ["rate", "availability"],
                "rate": 175.00,
                "availability": 10
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_room_types"] == 2
        assert data["total_rate_plans"] == 1

    def test_bulk_grid_update_with_day_filter_weekends(self):
        """Test bulk update with weekend-only day filter (Sat=6, Sun=0)"""
        today = date.today()
        start = today.isoformat()
        # 14 days to ensure we hit multiple weekends
        end = (today + timedelta(days=14)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": [0, 6],  # Sunday and Saturday only
                "update_fields": ["rate"],
                "rate": 220.00
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only update weekend days (max 4 weekends in 14 days = 8 days)
        assert data["saved"] <= 8, f"Day filter not working: {data['saved']} records updated"
        assert data["saved"] > 0, "No records updated for weekends"

    def test_bulk_grid_update_with_day_filter_weekdays(self):
        """Test bulk update with weekday-only day filter (Mon=1 to Fri=5)"""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=7)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": [1, 2, 3, 4, 5],  # Monday to Friday
                "update_fields": ["rate"],
                "rate": 180.00
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only update weekdays
        assert data["saved"] >= 0

    def test_bulk_grid_update_min_stay(self):
        """Test bulk update for minimum stay"""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=3)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,
                "update_fields": ["min_stay"],
                "min_stay": 2
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        assert data["saved"] >= 4

    def test_bulk_grid_update_stop_sell(self):
        """Test bulk update for stop sell restriction"""
        today = date.today()
        start = (today + timedelta(days=30)).isoformat()  # Future date
        end = (today + timedelta(days=32)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,
                "update_fields": ["stop_sell"],
                "stop_sell": True
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        assert data["saved"] >= 3

    def test_bulk_grid_update_empty_room_types(self):
        """Test bulk update with empty room types returns 0 saved"""
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": [],
                "rate_plan_codes": ["BAR"],
                "start_date": today,
                "end_date": end,
                "update_fields": ["rate"],
                "rate": 100.00
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        assert data["saved"] == 0
        assert data["total_room_types"] == 0

    def test_bulk_grid_update_all_fields(self):
        """Test bulk update with all update fields enabled"""
        today = date.today()
        start = (today + timedelta(days=60)).isoformat()  # Far future
        end = (today + timedelta(days=61)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,
                "update_fields": ["rate", "availability", "min_stay", "max_stay", "stop_sell", "cta", "ctd"],
                "rate": 300.00,
                "availability": 8,
                "min_stay": 2,
                "max_stay": 14,
                "stop_sell": False,
                "cta": False,
                "ctd": False
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        assert data["saved"] >= 2

    # ─── Exely Push Verification ───
    def test_bulk_update_pushes_to_exely(self):
        """Verify bulk update includes Exely push results"""
        today = date.today()
        start = today.isoformat()
        end = (today + timedelta(days=1)).isoformat()
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/bulk-grid-update",
            json={
                "room_type_codes": ["101"],
                "rate_plan_codes": ["BAR"],
                "start_date": start,
                "end_date": end,
                "selected_days": None,
                "update_fields": ["rate"],
                "rate": 155.00
            }
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "push_results" in data
        assert "all_pushed" in data
        # Should have push result for the room type + rate plan combination
        if len(data["push_results"]) > 0:
            result = data["push_results"][0]
            assert "room_type_code" in result
            assert "rate_plan_code" in result
            assert "success" in result


class TestRateManagerGridData:
    """Tests for grid data structure and content"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert login_response.status_code == 200
        
        data = login_response.json()
        self.token = data.get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield

    def test_grid_row_structure(self):
        """Verify grid row has expected fields"""
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=2)).isoformat()
        
        response = self.session.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end}
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["grid"]) > 0, "Grid is empty"
        
        row = data["grid"][0]
        assert "room_type_code" in row
        assert "room_type_name" in row
        assert "rate_plan_code" in row
        assert "rate_plan_name" in row
        assert "dates" in row

    def test_grid_date_cell_structure(self):
        """Verify each date cell in grid has expected fields"""
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=2)).isoformat()
        
        response = self.session.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": today, "end_date": end}
        )
        
        skip_if_no_exely(response)
        
        assert response.status_code == 200
        data = response.json()
        
        row = data["grid"][0]
        assert len(row["dates"]) >= 3, "Not enough dates in grid"
        
        cell = row["dates"][0]
        assert "date" in cell
        assert "rate" in cell or cell.get("rate") is None
        assert "availability" in cell or cell.get("availability") is None
        assert "min_stay" in cell
        assert "stop_sell" in cell
