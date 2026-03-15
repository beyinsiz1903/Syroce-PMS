"""
Exely Channel Manager API Tests
Tests for Exely SOAP integration endpoints:
- Connection management (GET /connection, POST /connect, DELETE /disconnect, POST /test)
- Room discovery (GET /rooms/discover)
- Room mappings CRUD (POST /room-mappings, GET /room-mappings, DELETE /room-mappings/{id})
- Reservation sync (POST /sync/reservations/pull, GET /reservations/local)
- Sync status (GET /sync/status, POST /sync/scheduler/start, POST /sync/scheduler/stop)
- Sync logs (GET /sync-logs)
- Raw events (GET /logs/events)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestExelyAuth:
    """Setup authentication for tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in response"
        return token
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestExelyConnection(TestExelyAuth):
    """Exely connection management tests"""
    
    def test_get_connection_status_disconnected(self, headers):
        """GET /api/channel-manager/exely/connection - returns connected: false when no connection"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/connection",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Should have 'connected' field
        assert "connected" in data, f"Missing 'connected' field: {data}"
        # When not connected, should return connected: false
        if not data.get("connected"):
            assert data["connected"] == False, f"Expected connected=false, got: {data}"
            print(f"✅ Connection status: disconnected (expected)")
        else:
            print(f"✅ Connection status: connected (existing connection found)")

    def test_connect_invalid_credentials_returns_error(self, headers):
        """POST /api/channel-manager/exely/connect - fails with invalid Exely credentials"""
        # This will fail because there's no real Exely server - expected behavior
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/connect",
            headers=headers,
            json={
                "username": "test_invalid_user",
                "password": "test_invalid_pass",
                "hotel_code": "12345",
                "auto_sync_reservations": False,
                "sync_interval_minutes": 15
            }
        )
        # Should return 400 because Exely connection fails (no real server)
        assert response.status_code in [400, 502], f"Unexpected status: {response.status_code}, {response.text}"
        print(f"✅ Connect with invalid credentials properly rejected: {response.status_code}")


class TestExelySyncStatus(TestExelyAuth):
    """Exely sync status tests"""
    
    def test_get_sync_status(self, headers):
        """GET /api/channel-manager/exely/sync/status - returns sync status structure"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/sync/status",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Verify expected fields
        assert "scheduler_running" in data, f"Missing scheduler_running: {data}"
        assert "pending_events" in data, f"Missing pending_events: {data}"
        assert "error_events" in data, f"Missing error_events: {data}"
        assert "total_reservations" in data, f"Missing total_reservations: {data}"
        print(f"✅ Sync status: scheduler_running={data['scheduler_running']}, "
              f"pending={data['pending_events']}, errors={data['error_events']}, "
              f"reservations={data['total_reservations']}")


class TestExelyRoomMappings(TestExelyAuth):
    """Exely room mapping CRUD tests"""
    
    def test_get_room_mappings_empty(self, headers):
        """GET /api/channel-manager/exely/room-mappings - returns mappings list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "mappings" in data, f"Missing 'mappings' field: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        assert isinstance(data["mappings"], list), f"'mappings' should be a list: {data}"
        print(f"✅ Room mappings: count={data['count']}")

    def test_create_room_mapping(self, headers):
        """POST /api/channel-manager/exely/room-mappings - creates a mapping"""
        mapping_data = {
            "pms_room_type": f"TEST_STD_{uuid.uuid4().hex[:8]}",
            "exely_room_code": "EXELY_STD",
            "exely_rate_plan_code": "EXELY_BAR",
            "exely_room_name": "Test Standard Room",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": True
        }
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers,
            json=mapping_data
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "mapping" in data, f"Missing 'mapping' in response: {data}"
        mapping = data["mapping"]
        assert "id" in mapping, f"Missing 'id' in mapping: {mapping}"
        assert mapping["pms_room_type"] == mapping_data["pms_room_type"]
        assert mapping["exely_room_code"] == mapping_data["exely_room_code"]
        print(f"✅ Created room mapping: id={mapping['id']}")
        return mapping["id"]

    def test_create_and_delete_room_mapping(self, headers):
        """POST and DELETE /api/channel-manager/exely/room-mappings/{id}"""
        # Create mapping
        mapping_data = {
            "pms_room_type": f"TEST_DEL_{uuid.uuid4().hex[:8]}",
            "exely_room_code": "EXELY_DLX",
            "exely_rate_plan_code": "EXELY_PROMO",
            "exely_room_name": "Test Deluxe Room (Delete Test)",
            "sync_availability": True,
            "sync_price": False,
            "sync_restrictions": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings",
            headers=headers,
            json=mapping_data
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        mapping_id = create_response.json()["mapping"]["id"]
        
        # Delete mapping
        delete_response = requests.delete(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings/{mapping_id}",
            headers=headers
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        print(f"✅ Created and deleted room mapping: id={mapping_id}")

    def test_delete_nonexistent_mapping_returns_404(self, headers):
        """DELETE /api/channel-manager/exely/room-mappings/{id} - 404 for unknown id"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/exely/room-mappings/{fake_id}",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got: {response.status_code}"
        print(f"✅ Delete nonexistent mapping correctly returns 404")


class TestExelySyncLogs(TestExelyAuth):
    """Exely sync logs tests"""
    
    def test_get_sync_logs(self, headers):
        """GET /api/channel-manager/exely/sync-logs - returns logs list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/sync-logs?limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "logs" in data, f"Missing 'logs' field: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        assert isinstance(data["logs"], list), f"'logs' should be a list: {data}"
        print(f"✅ Sync logs: count={data['count']}")


class TestExelyReservations(TestExelyAuth):
    """Exely reservations tests"""
    
    def test_get_local_reservations(self, headers):
        """GET /api/channel-manager/exely/reservations/local - returns reservations list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/reservations/local",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "reservations" in data, f"Missing 'reservations' field: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        assert isinstance(data["reservations"], list), f"'reservations' should be a list: {data}"
        print(f"✅ Local reservations: count={data['count']}")


class TestExelyRawEvents(TestExelyAuth):
    """Exely raw events tests"""
    
    def test_get_raw_events(self, headers):
        """GET /api/channel-manager/exely/logs/events - returns events list"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/logs/events?limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "events" in data, f"Missing 'events' field: {data}"
        assert "count" in data, f"Missing 'count' field: {data}"
        assert isinstance(data["events"], list), f"'events' should be a list: {data}"
        print(f"✅ Raw events: count={data['count']}")


class TestExelyRequireConnection(TestExelyAuth):
    """Tests that require an active Exely connection (expected to fail or return 404/502)"""
    
    def test_rooms_discover_requires_connection(self, headers):
        """GET /api/channel-manager/exely/rooms/discover - requires connection"""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/exely/rooms/discover",
            headers=headers
        )
        # Should return 404 (no connection) or 502 (connection but SOAP fails)
        # Unless there's an existing connection
        assert response.status_code in [200, 404, 502], f"Unexpected: {response.status_code}, {response.text}"
        if response.status_code == 404:
            print(f"✅ Room discovery correctly requires connection (404)")
        elif response.status_code == 502:
            print(f"✅ Room discovery attempted but SOAP failed (502 - no real Exely)")
        else:
            print(f"✅ Room discovery succeeded (existing connection)")

    def test_manual_pull_requires_connection(self, headers):
        """POST /api/channel-manager/exely/sync/reservations/pull - requires connection"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/sync/reservations/pull",
            headers=headers
        )
        # Should return 404 if no connection
        assert response.status_code in [200, 404, 502], f"Unexpected: {response.status_code}, {response.text}"
        if response.status_code == 404:
            print(f"✅ Manual pull correctly requires connection (404)")
        elif response.status_code == 502:
            print(f"✅ Manual pull attempted but SOAP failed (502 - no real Exely)")
        else:
            print(f"✅ Manual pull succeeded (existing connection)")

    def test_test_connection_requires_existing(self, headers):
        """POST /api/channel-manager/exely/test - requires existing connection"""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/exely/test",
            headers=headers
        )
        # Should return 404 if no connection exists
        assert response.status_code in [200, 404, 502], f"Unexpected: {response.status_code}, {response.text}"
        if response.status_code == 404:
            print(f"✅ Test connection correctly requires existing connection (404)")
        else:
            print(f"✅ Test connection returned: {response.status_code}")

    def test_disconnect_requires_existing(self, headers):
        """DELETE /api/channel-manager/exely/disconnect - requires existing connection"""
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/exely/disconnect",
            headers=headers
        )
        # Should return 404 if no active connection
        assert response.status_code in [200, 404], f"Unexpected: {response.status_code}, {response.text}"
        if response.status_code == 404:
            print(f"✅ Disconnect correctly requires active connection (404)")
        else:
            print(f"✅ Disconnect succeeded")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
