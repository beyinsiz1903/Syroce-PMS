"""
HotelRunner Room Mappings API Tests
Tests for: GET /pms-room-types, GET /cached-rooms, POST /room-mappings, 
POST /room-mappings/bulk, DELETE /room-mappings/{id}, GET /room-mappings
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('VITE_BACKEND_URL', 'https://orphan-removal.preview.emergentagent.com').rstrip('/')


class TestHotelRunnerRoomMappingsAPI:
    """Test HotelRunner Room Mappings API endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token via login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    # ── Connection Status ────────────────────────────────────────────────
    
    def test_connection_status(self, headers):
        """Test HotelRunner connection status"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/connection", headers=headers)
        assert response.status_code == 200, f"Connection status failed: {response.text}"
        data = response.json()
        print(f"Connection status: {data}")
        assert "connected" in data
        # Connection should be active for mapping tests
        assert data.get("connected") == True, "HotelRunner connection not active"
    
    # ── PMS Room Types ───────────────────────────────────────────────────
    
    def test_get_pms_room_types(self, headers):
        """Test GET /api/channel-manager/hotelrunner/pms-room-types"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/pms-room-types", headers=headers)
        assert response.status_code == 200, f"Get PMS room types failed: {response.text}"
        data = response.json()
        print(f"PMS room types: {data}")
        assert "room_types" in data
        # Should have some room types (Standard, Deluxe, Suite, etc.)
        room_types = data.get("room_types", [])
        print(f"Found {len(room_types)} PMS room types: {room_types}")
    
    # ── Cached HR Rooms ──────────────────────────────────────────────────
    
    def test_get_cached_rooms(self, headers):
        """Test GET /api/channel-manager/hotelrunner/cached-rooms"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/cached-rooms", headers=headers)
        assert response.status_code == 200, f"Get cached rooms failed: {response.text}"
        data = response.json()
        print(f"Cached rooms response: {data}")
        assert "rooms" in data
        rooms = data.get("rooms", [])
        print(f"Found {len(rooms)} cached HR rooms")
        if rooms:
            print(f"Sample room: {rooms[0]}")
    
    # ── Room Mappings CRUD ───────────────────────────────────────────────
    
    def test_get_room_mappings(self, headers):
        """Test GET /api/channel-manager/hotelrunner/room-mappings"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings", headers=headers)
        assert response.status_code == 200, f"Get room mappings failed: {response.text}"
        data = response.json()
        print(f"Room mappings: {data}")
        assert "mappings" in data
        assert "count" in data
        mappings = data.get("mappings", [])
        print(f"Found {len(mappings)} existing mappings")
        if mappings:
            print(f"Sample mapping: {mappings[0]}")
    
    def test_create_single_mapping(self, headers):
        """Test POST /api/channel-manager/hotelrunner/room-mappings"""
        # First get cached rooms to get valid inv_code and rate_code
        rooms_response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/cached-rooms", headers=headers)
        if rooms_response.status_code != 200:
            pytest.skip("No cached rooms available")
        
        rooms = rooms_response.json().get("rooms", [])
        if not rooms:
            pytest.skip("No cached rooms to create mapping for")
        
        # Use first room for test
        test_room = rooms[0]
        payload = {
            "pms_room_type": "TEST_Standard",
            "hr_inv_code": test_room.get("inv_code", "TEST-INV"),
            "hr_rate_code": test_room.get("rate_code", "TEST-RATE"),
            "hr_room_name": test_room.get("name", "Test Room"),
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": False
        }
        
        response = requests.post(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings", 
                                json=payload, headers=headers)
        assert response.status_code == 200, f"Create mapping failed: {response.text}"
        data = response.json()
        print(f"Create mapping response: {data}")
        assert "message" in data
        # Store mapping_id for cleanup
        return data.get("mapping", {}).get("id") or data.get("mapping_id")
    
    def test_bulk_create_mappings(self, headers):
        """Test POST /api/channel-manager/hotelrunner/room-mappings/bulk"""
        # First get cached rooms
        rooms_response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/cached-rooms", headers=headers)
        if rooms_response.status_code != 200:
            pytest.skip("No cached rooms available")
        
        rooms = rooms_response.json().get("rooms", [])
        if len(rooms) < 2:
            pytest.skip("Need at least 2 rooms for bulk test")
        
        # Create bulk mappings for first 2 rooms
        bulk_payload = []
        pms_types = ["TEST_Bulk_Standard", "TEST_Bulk_Deluxe"]
        for i, room in enumerate(rooms[:2]):
            bulk_payload.append({
                "pms_room_type": pms_types[i],
                "hr_inv_code": room.get("inv_code", f"TEST-INV-{i}"),
                "hr_rate_code": room.get("rate_code", f"TEST-RATE-{i}"),
                "hr_room_name": room.get("name", f"Test Room {i}"),
                "sync_availability": True,
                "sync_price": True,
                "sync_restrictions": True
            })
        
        response = requests.post(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings/bulk",
                                json=bulk_payload, headers=headers)
        assert response.status_code == 200, f"Bulk create failed: {response.text}"
        data = response.json()
        print(f"Bulk create response: {data}")
        assert "message" in data
        assert "created" in data or "updated" in data
    
    def test_delete_mapping(self, headers):
        """Test DELETE /api/channel-manager/hotelrunner/room-mappings/{mapping_id}"""
        # First get existing mappings
        mappings_response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings", headers=headers)
        assert mappings_response.status_code == 200
        
        mappings = mappings_response.json().get("mappings", [])
        # Find a TEST_ mapping to delete
        test_mapping = None
        for m in mappings:
            if m.get("pms_room_type", "").startswith("TEST_"):
                test_mapping = m
                break
        
        if not test_mapping:
            pytest.skip("No TEST_ mapping found to delete")
        
        mapping_id = test_mapping.get("id")
        response = requests.delete(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings/{mapping_id}", 
                                  headers=headers)
        assert response.status_code == 200, f"Delete mapping failed: {response.text}"
        data = response.json()
        print(f"Delete mapping response: {data}")
        assert "message" in data
        
        # Verify deletion
        verify_response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings", headers=headers)
        verify_mappings = verify_response.json().get("mappings", [])
        deleted_ids = [m.get("id") for m in verify_mappings]
        assert mapping_id not in deleted_ids, "Mapping was not deleted"
    
    # ── Fetch Rooms from HotelRunner ─────────────────────────────────────
    
    def test_fetch_rooms_from_hr(self, headers):
        """Test GET /api/channel-manager/hotelrunner/rooms (fetch from HR API)"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/rooms", headers=headers)
        # This may fail if HR connection is not properly configured
        if response.status_code == 502:
            print(f"HR API error (expected if mock): {response.text}")
            pytest.skip("HotelRunner API not available")
        
        assert response.status_code == 200, f"Fetch rooms failed: {response.text}"
        data = response.json()
        print(f"Fetched rooms: {data}")
        assert "rooms" in data
        assert "count" in data
        rooms = data.get("rooms", [])
        print(f"Fetched {len(rooms)} rooms from HotelRunner")
        if rooms:
            print(f"Sample room: {rooms[0]}")
    
    # ── Cleanup TEST_ mappings ───────────────────────────────────────────
    
    def test_cleanup_test_mappings(self, headers):
        """Cleanup all TEST_ prefixed mappings"""
        mappings_response = requests.get(f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings", headers=headers)
        if mappings_response.status_code != 200:
            return
        
        mappings = mappings_response.json().get("mappings", [])
        deleted_count = 0
        for m in mappings:
            if m.get("pms_room_type", "").startswith("TEST_"):
                mapping_id = m.get("id")
                del_response = requests.delete(
                    f"{BASE_URL}/api/channel-manager/hotelrunner/room-mappings/{mapping_id}",
                    headers=headers
                )
                if del_response.status_code == 200:
                    deleted_count += 1
        
        print(f"Cleaned up {deleted_count} TEST_ mappings")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
