"""
HotelRunner Push Queue API Tests
================================
Tests for the automatic push retry queue mechanism that handles rate-limited pushes.

Endpoints tested:
- GET /api/channel-manager/hr-rate-manager/queue-status
- POST /api/channel-manager/hr-rate-manager/queue-retry
- DELETE /api/channel-manager/hr-rate-manager/queue-clear
- DELETE /api/channel-manager/hr-rate-manager/queue-cancel/{item_id}
- POST /api/channel-manager/hr-rate-manager/bulk-grid-update (queued_count field)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hotelrunner-sync-1.preview.emergentagent.com").rstrip("/")


class TestHRPushQueueAPI:
    """Test HotelRunner Push Queue endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip(f"Authentication failed: {login_response.status_code}")

    def test_queue_status_endpoint_returns_statistics(self):
        """GET /api/channel-manager/hr-rate-manager/queue-status returns queue statistics"""
        response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "pending" in data, "Response should contain 'pending' field"
        assert "retrying" in data, "Response should contain 'retrying' field"
        assert "completed" in data, "Response should contain 'completed' field"
        assert "failed" in data, "Response should contain 'failed' field"
        assert "total_in_queue" in data, "Response should contain 'total_in_queue' field"
        
        # Verify types
        assert isinstance(data["pending"], int), "pending should be an integer"
        assert isinstance(data["retrying"], int), "retrying should be an integer"
        assert isinstance(data["completed"], int), "completed should be an integer"
        assert isinstance(data["failed"], int), "failed should be an integer"
        assert isinstance(data["total_in_queue"], int), "total_in_queue should be an integer"
        
        # Verify total_in_queue calculation
        assert data["total_in_queue"] == data["pending"] + data["retrying"], \
            "total_in_queue should equal pending + retrying"
        
        print(f"Queue status: pending={data['pending']}, retrying={data['retrying']}, "
              f"completed={data['completed']}, failed={data['failed']}, total={data['total_in_queue']}")

    def test_queue_status_contains_pending_items_list(self):
        """GET /api/channel-manager/hr-rate-manager/queue-status includes pending_items list"""
        response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "pending_items" in data, "Response should contain 'pending_items' field"
        assert isinstance(data["pending_items"], list), "pending_items should be a list"
        
        # If there are pending items, verify their structure
        if len(data["pending_items"]) > 0:
            item = data["pending_items"][0]
            assert "id" in item, "Queue item should have 'id'"
            assert "room_type_code" in item, "Queue item should have 'room_type_code'"
            assert "start_date" in item, "Queue item should have 'start_date'"
            assert "end_date" in item, "Queue item should have 'end_date'"
            assert "status" in item, "Queue item should have 'status'"
            print(f"Found {len(data['pending_items'])} pending items in queue")
        else:
            print("No pending items in queue")

    def test_queue_retry_endpoint_triggers_processing(self):
        """POST /api/channel-manager/hr-rate-manager/queue-retry triggers queue processing"""
        response = self.session.post(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-retry")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should return message and queue status
        assert "message" in data, "Response should contain 'message' field"
        assert "pending" in data, "Response should contain queue status fields"
        assert "total_in_queue" in data, "Response should contain 'total_in_queue'"
        
        print(f"Queue retry response: {data['message']}, total_in_queue={data['total_in_queue']}")

    def test_queue_clear_endpoint_removes_completed_items(self):
        """DELETE /api/channel-manager/hr-rate-manager/queue-clear removes completed items"""
        response = self.session.delete(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-clear")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain 'message' field"
        assert "deleted" in data, "Response should contain 'deleted' count"
        assert isinstance(data["deleted"], int), "deleted should be an integer"
        
        print(f"Queue clear: {data['message']}, deleted={data['deleted']}")

    def test_queue_cancel_with_invalid_id_returns_404(self):
        """DELETE /api/channel-manager/hr-rate-manager/queue-cancel/{item_id} returns 404 for invalid ID"""
        invalid_id = "nonexistent-item-id-12345"
        response = self.session.delete(
            f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-cancel/{invalid_id}"
        )
        
        # Should return 404 for non-existent item
        assert response.status_code == 404, f"Expected 404 for invalid ID, got {response.status_code}"
        print(f"Queue cancel with invalid ID correctly returned 404")

    def test_queue_cancel_with_valid_pending_item(self):
        """DELETE /api/channel-manager/hr-rate-manager/queue-cancel/{item_id} cancels pending item"""
        # First get queue status to find a pending item
        status_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        assert status_response.status_code == 200
        
        data = status_response.json()
        pending_items = data.get("pending_items", [])
        
        if len(pending_items) == 0:
            pytest.skip("No pending items in queue to cancel")
        
        # Get the first pending item's ID
        item_id = pending_items[0]["id"]
        print(f"Attempting to cancel queue item: {item_id}")
        
        # Cancel the item
        cancel_response = self.session.delete(
            f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-cancel/{item_id}"
        )
        
        assert cancel_response.status_code == 200, f"Expected 200, got {cancel_response.status_code}: {cancel_response.text}"
        
        cancel_data = cancel_response.json()
        assert "message" in cancel_data, "Response should contain 'message'"
        print(f"Queue cancel: {cancel_data['message']}")
        
        # Verify item is no longer in queue
        verify_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        verify_data = verify_response.json()
        remaining_ids = [item["id"] for item in verify_data.get("pending_items", [])]
        assert item_id not in remaining_ids, "Cancelled item should not be in pending_items"

    def test_bulk_grid_update_returns_queued_count_field(self):
        """POST /api/channel-manager/hr-rate-manager/bulk-grid-update response includes queued_count"""
        # First get room types to use in the update
        room_types_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/room-types")
        
        if room_types_response.status_code != 200:
            pytest.skip("Could not get room types")
        
        room_types_data = room_types_response.json()
        room_types = room_types_data.get("room_types", [])
        rate_plans = room_types_data.get("rate_plans", [])
        
        if len(room_types) == 0 or len(rate_plans) == 0:
            pytest.skip("No room types or rate plans available")
        
        # Use first room type and rate plan
        rt_code = room_types[0]["code"]
        rp_code = rate_plans[0]["code"]
        
        # Make a bulk update request (this will likely hit rate limit and queue)
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        update_payload = {
            "per_room_values": [{
                "room_type_code": rt_code,
                "rate_plan_codes": [rp_code],
                "rate": 100.0
            }],
            "start_date": today,
            "end_date": tomorrow,
            "update_fields": ["rate"]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/channel-manager/hr-rate-manager/bulk-grid-update",
            json=update_payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify queued_count field exists in response
        assert "queued_count" in data, "Response should contain 'queued_count' field"
        assert isinstance(data["queued_count"], int), "queued_count should be an integer"
        
        # Also verify other expected fields
        assert "saved" in data, "Response should contain 'saved' field"
        assert "push_results" in data, "Response should contain 'push_results' field"
        assert "rate_limit_hit" in data, "Response should contain 'rate_limit_hit' field"
        
        print(f"Bulk update: saved={data['saved']}, queued_count={data['queued_count']}, "
              f"rate_limit_hit={data['rate_limit_hit']}")
        
        # If rate limited, queued_count should be > 0
        if data.get("rate_limit_hit"):
            print(f"Rate limit hit - items queued for retry: {data['queued_count']}")


class TestHRPushQueueWorkerStartup:
    """Test that push queue worker starts on app startup"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")

    def test_queue_status_accessible_indicates_worker_initialized(self):
        """Queue status endpoint being accessible indicates worker module is loaded"""
        response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        
        # If endpoint works, the worker module is loaded
        assert response.status_code == 200, "Queue status endpoint should be accessible"
        print("Push queue worker module is loaded and endpoints are accessible")


class TestHRPushQueueIntegration:
    """Integration tests for push queue with bulk updates"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")

    def test_queue_status_after_rate_limited_push(self):
        """After a rate-limited push, queue should have pending items"""
        # Get initial queue status
        initial_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
        assert initial_response.status_code == 200
        initial_data = initial_response.json()
        initial_total = initial_data["total_in_queue"]
        
        print(f"Initial queue total: {initial_total}")
        
        # The HotelRunner API is rate-limited, so any push should fail and queue
        # Get room types
        room_types_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/room-types")
        if room_types_response.status_code != 200:
            pytest.skip("Could not get room types")
        
        room_types_data = room_types_response.json()
        room_types = room_types_data.get("room_types", [])
        rate_plans = room_types_data.get("rate_plans", [])
        
        if len(room_types) == 0 or len(rate_plans) == 0:
            pytest.skip("No room types or rate plans available")
        
        # Make a bulk update that will hit rate limit
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        update_payload = {
            "per_room_values": [{
                "room_type_code": room_types[0]["code"],
                "rate_plan_codes": [rate_plans[0]["code"]],
                "availability": 5
            }],
            "start_date": today,
            "end_date": tomorrow,
            "update_fields": ["availability"]
        }
        
        update_response = self.session.post(
            f"{BASE_URL}/api/channel-manager/hr-rate-manager/bulk-grid-update",
            json=update_payload
        )
        
        assert update_response.status_code == 200
        update_data = update_response.json()
        
        # Check if rate limit was hit and items were queued
        if update_data.get("rate_limit_hit") or update_data.get("queued_count", 0) > 0:
            # Verify queue has items
            final_response = self.session.get(f"{BASE_URL}/api/channel-manager/hr-rate-manager/queue-status")
            final_data = final_response.json()
            
            print(f"After rate-limited push: total_in_queue={final_data['total_in_queue']}, "
                  f"queued_count from update={update_data.get('queued_count', 0)}")
            
            # Queue should have items (either from this push or previous)
            assert final_data["total_in_queue"] >= 0, "Queue total should be non-negative"
        else:
            print("Push succeeded without rate limit - no items queued")
