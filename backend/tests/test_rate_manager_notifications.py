"""
Test Rate Manager and Notifications API
Tests for:
- GET /api/channel-manager/rate-manager/grid
- POST /api/channel-manager/rate-manager/update
- GET /api/channel-manager/rate-manager/room-types
- GET /api/notifications/list
- PUT /api/notifications/{id}/mark-read
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="REACT_APP_BACKEND_URL not set - integration tests require a running server"
)

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"}
    )
    if response.status_code != 200:
        pytest.skip("Authentication failed - skipping authenticated tests")
    return response.json().get("access_token")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Requests session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestRateManagerGrid:
    """Tests for GET /api/channel-manager/rate-manager/grid"""
    
    def test_grid_returns_200(self, api_client):
        """Test grid endpoint returns 200 with valid date range"""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-01-21", "end_date": "2026-01-27"}
        )
        assert response.status_code == 200
        
    def test_grid_has_required_fields(self, api_client):
        """Test grid response contains required fields"""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-01-21", "end_date": "2026-01-27"}
        )
        data = response.json()
        
        assert "grid" in data
        assert "room_types" in data
        assert "rate_plans" in data
        assert "start_date" in data
        assert "end_date" in data
        
    def test_grid_row_structure(self, api_client):
        """Test each grid row has proper structure"""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-01-21", "end_date": "2026-01-27"}
        )
        data = response.json()
        
        assert len(data["grid"]) > 0, "Grid should have at least one row"
        
        row = data["grid"][0]
        assert "room_type_code" in row
        assert "room_type_name" in row
        assert "rate_plan_code" in row
        assert "rate_plan_name" in row
        assert "pms_room_type" in row
        assert "dates" in row
        
    def test_grid_date_cell_structure(self, api_client):
        """Test each date cell has proper structure"""
        response = api_client.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-01-21", "end_date": "2026-01-27"}
        )
        data = response.json()
        
        row = data["grid"][0]
        assert len(row["dates"]) == 7, "Should have 7 days of data"
        
        cell = row["dates"][0]
        assert "date" in cell
        assert "availability" in cell
        assert "min_stay" in cell
        assert "stop_sell" in cell


class TestRateManagerRoomTypes:
    """Tests for GET /api/channel-manager/rate-manager/room-types"""
    
    def test_room_types_returns_200(self, api_client):
        """Test room-types endpoint returns 200"""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/rate-manager/room-types")
        assert response.status_code == 200
        
    def test_room_types_has_data(self, api_client):
        """Test room-types returns expected data from Exely connection"""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/rate-manager/room-types")
        data = response.json()
        
        assert "room_types" in data
        assert "rate_plans" in data
        assert len(data["room_types"]) >= 3, "Should have at least 3 room types from Exely"
        assert len(data["rate_plans"]) >= 5, "Should have at least 5 rate plans from Exely"
        
    def test_room_type_structure(self, api_client):
        """Test room type has code and name"""
        response = api_client.get(f"{BASE_URL}/api/channel-manager/rate-manager/room-types")
        data = response.json()
        
        rt = data["room_types"][0]
        assert "code" in rt
        assert "name" in rt


class TestRateManagerUpdate:
    """Tests for POST /api/channel-manager/rate-manager/update"""
    
    def test_update_single_date_returns_200(self, api_client):
        """Test rate update for single date returns 200"""
        test_update = {
            "updates": [{
                "room_type_code": "5001574",
                "rate_plan_code": "10003870",
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "rate": 175.00,
                "availability": 4,
                "min_stay": 1,
                "stop_sell": False
            }]
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/update",
            json=test_update
        )
        assert response.status_code == 200
        
    def test_update_saves_to_db(self, api_client):
        """Test rate update persists to database"""
        test_update = {
            "updates": [{
                "room_type_code": "5001574",
                "rate_plan_code": "10003870",
                "start_date": "2026-02-02",
                "end_date": "2026-02-02",
                "rate": 199.00,
                "availability": 3,
                "min_stay": 2,
                "stop_sell": False
            }]
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/update",
            json=test_update
        )
        data = response.json()
        
        assert data["saved"] == 1, "Should have saved 1 date record"
        
        # Verify with GET
        verify_response = api_client.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-02-02", "end_date": "2026-02-02"}
        )
        verify_data = verify_response.json()
        
        # Find our updated row
        for row in verify_data["grid"]:
            if row["room_type_code"] == "5001574" and row["rate_plan_code"] == "10003870":
                cell = row["dates"][0]
                assert cell["rate"] == 199.0
                assert cell["availability"] == 3
                assert cell["min_stay"] == 2
                break
                
    def test_update_pushes_to_exely(self, api_client):
        """Test rate update pushes to Exely and returns success"""
        test_update = {
            "updates": [{
                "room_type_code": "5001574",
                "rate_plan_code": "10003870",
                "start_date": "2026-02-03",
                "end_date": "2026-02-03",
                "rate": 185.00,
                "availability": 6,
                "min_stay": 1,
                "stop_sell": False
            }]
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/update",
            json=test_update
        )
        data = response.json()
        
        assert "push_results" in data
        assert len(data["push_results"]) == 1
        assert data["push_results"][0]["success"] is True, "Exely push should succeed"
        assert data["all_pushed"] is True
        
    def test_update_date_range(self, api_client):
        """Test rate update for date range saves multiple records"""
        test_update = {
            "updates": [{
                "room_type_code": "5001574",
                "rate_plan_code": "10003870",
                "start_date": "2026-02-05",
                "end_date": "2026-02-07",
                "rate": 165.00,
                "availability": 5,
                "min_stay": 1,
                "stop_sell": False
            }]
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/channel-manager/rate-manager/update",
            json=test_update
        )
        data = response.json()
        
        assert data["saved"] == 3, "Should have saved 3 date records"


class TestNotificationsList:
    """Tests for GET /api/notifications/list"""
    
    def test_notifications_list_returns_200(self, api_client):
        """Test notifications list returns 200"""
        response = api_client.get(f"{BASE_URL}/api/notifications/list")
        assert response.status_code == 200
        
    def test_notifications_list_structure(self, api_client):
        """Test notifications list has required fields"""
        response = api_client.get(f"{BASE_URL}/api/notifications/list")
        data = response.json()
        
        assert "notifications" in data
        assert "count" in data
        assert "unread_count" in data
        assert isinstance(data["notifications"], list)
        
    def test_notifications_list_with_limit(self, api_client):
        """Test notifications list respects limit parameter"""
        response = api_client.get(
            f"{BASE_URL}/api/notifications/list",
            params={"limit": 5}
        )
        assert response.status_code == 200


class TestNotificationsMarkRead:
    """Tests for PUT /api/notifications/{id}/mark-read"""
    
    def test_mark_read_nonexistent_returns_404(self, api_client):
        """Test marking non-existent notification returns 404"""
        fake_id = str(uuid.uuid4())
        response = api_client.put(f"{BASE_URL}/api/notifications/{fake_id}/mark-read")
        assert response.status_code == 404
        
    def test_mark_read_returns_proper_error(self, api_client):
        """Test marking non-existent notification returns proper error message"""
        fake_id = str(uuid.uuid4())
        response = api_client.put(f"{BASE_URL}/api/notifications/{fake_id}/mark-read")
        data = response.json()
        
        assert "detail" in data
        assert data["detail"] == "Notification not found"


class TestAuthRequired:
    """Test that endpoints require authentication"""
    
    def test_grid_requires_auth(self):
        """Test grid endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/rate-manager/grid",
            params={"start_date": "2026-01-21", "end_date": "2026-01-27"}
        )
        assert response.status_code in [401, 403]
        
    def test_room_types_requires_auth(self):
        """Test room-types endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/rate-manager/room-types")
        assert response.status_code in [401, 403]
        
    def test_notifications_requires_auth(self):
        """Test notifications endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/notifications/list")
        assert response.status_code in [401, 403]
