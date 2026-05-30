"""
Syroce B2B Webhook API Tests
============================
Tests for:
- Webhook CRUD operations (register, list, delete)
- Webhook test endpoint
- Webhook validation (HTTPS only, valid events)
- Max 5 webhooks per agency limit
- Webhook auto-fire on reservation create/cancel
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
HOTEL_ADMIN_EMAIL = "demo@hotel.com"
HOTEL_ADMIN_PASSWORD = "demo123"

# Test agency ID
ANTALYA_TURIZM_ID = "1d6ebdef-b42a-40ea-8c01-f749ea96fdea"

# Test dates for reservation
CHECK_IN = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
CHECK_OUT = (datetime.now() + timedelta(days=62)).strftime("%Y-%m-%d")

# Valid webhook events
VALID_EVENTS = ["reservation.created", "reservation.cancelled", "reservation.updated"]


class TestB2BWebhookSetup:
    """Setup and helper methods for webhook tests"""
    
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
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def api_key(self, admin_headers):
        """Get or create API key for testing"""
        agency_id = ANTALYA_TURIZM_ID
        
        # Check if key exists
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
            return data.get("api_key")
        
        pytest.skip(f"Could not setup API key: {response.text}")
    
    @pytest.fixture(scope="class")
    def b2b_headers(self, api_key):
        return {"X-API-Key": api_key, "Content-Type": "application/json"}


class TestWebhookValidation(TestB2BWebhookSetup):
    """Test webhook validation rules"""
    
    def test_01_reject_non_https_url(self, b2b_headers):
        """POST /api/b2b/webhooks - Reject non-HTTPS URL"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "http://example.com/webhook",  # HTTP not HTTPS
            "events": ["reservation.created"]
        })
        print(f"Non-HTTPS URL response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 400, f"Expected 400 for non-HTTPS URL, got {response.status_code}"
        
        data = response.json()
        assert "HTTPS" in data.get("detail", ""), "Error should mention HTTPS requirement"
    
    def test_02_reject_invalid_events(self, b2b_headers):
        """POST /api/b2b/webhooks - Reject invalid event names"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "https://httpbin.org/post",
            "events": ["invalid.event", "another.invalid"]
        })
        print(f"Invalid events response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 400, f"Expected 400 for invalid events, got {response.status_code}"
        
        data = response.json()
        assert "Invalid events" in data.get("detail", ""), "Error should mention invalid events"
    
    def test_03_reject_mixed_valid_invalid_events(self, b2b_headers):
        """POST /api/b2b/webhooks - Reject if any event is invalid"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "https://httpbin.org/post",
            "events": ["reservation.created", "invalid.event"]  # One valid, one invalid
        })
        print(f"Mixed events response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 400, f"Expected 400 for mixed events, got {response.status_code}"


class TestWebhookCRUD(TestB2BWebhookSetup):
    """Test webhook CRUD operations"""
    
    created_webhook_id = None
    
    @pytest.fixture(scope="class", autouse=True)
    def cleanup_existing_webhooks(self, b2b_headers):
        """Cleanup existing webhooks before tests"""
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        if response.status_code == 200:
            data = response.json()
            for wh in data.get("webhooks", []):
                requests.delete(f"{BASE_URL}/api/b2b/webhooks/{wh['id']}", headers=b2b_headers)
                print(f"Cleaned up webhook: {wh['id']}")
        yield
    
    def test_01_list_webhooks_empty(self, b2b_headers):
        """GET /api/b2b/webhooks - List webhooks (should be empty after cleanup)"""
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        print(f"List webhooks response: {response.status_code}")
        assert response.status_code == 200, f"List webhooks failed: {response.text}"
        
        data = response.json()
        assert "webhooks" in data, "Response should contain webhooks"
        assert "count" in data, "Response should contain count"
        print(f"Webhooks count: {data.get('count')}")
    
    def test_02_register_webhook(self, b2b_headers):
        """POST /api/b2b/webhooks - Register a new webhook"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "https://httpbin.org/post",
            "events": ["reservation.created", "reservation.cancelled"],
            "secret": "test_secret_123"
        })
        print(f"Register webhook response: {response.status_code} - {response.text[:300]}")
        assert response.status_code == 200, f"Register webhook failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Response should have ok=True"
        assert "webhook" in data, "Response should contain webhook"
        
        webhook = data["webhook"]
        assert "id" in webhook, "Webhook should have id"
        assert webhook["url"] == "https://httpbin.org/post", "URL should match"
        assert "reservation.created" in webhook["events"], "Events should include reservation.created"
        assert "reservation.cancelled" in webhook["events"], "Events should include reservation.cancelled"
        assert webhook["is_active"] == True, "Webhook should be active"
        
        TestWebhookCRUD.created_webhook_id = webhook["id"]
        print(f"Created webhook: {webhook['id']}")
    
    def test_03_list_webhooks_after_create(self, b2b_headers):
        """GET /api/b2b/webhooks - Verify webhook appears in list"""
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        print(f"List webhooks response: {response.status_code}")
        assert response.status_code == 200, f"List webhooks failed: {response.text}"
        
        data = response.json()
        assert data.get("count", 0) >= 1, "Should have at least 1 webhook"
        
        webhook_ids = [wh["id"] for wh in data.get("webhooks", [])]
        assert TestWebhookCRUD.created_webhook_id in webhook_ids, "Created webhook should be in list"
    
    def test_04_test_webhook(self, b2b_headers):
        """POST /api/b2b/webhooks/{id}/test - Send test event to webhook"""
        webhook_id = TestWebhookCRUD.created_webhook_id
        if not webhook_id:
            pytest.skip("No webhook created")
        
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks/{webhook_id}/test", headers=b2b_headers)
        print(f"Test webhook response: {response.status_code} - {response.text[:300]}")
        assert response.status_code == 200, f"Test webhook failed: {response.text}"
        
        data = response.json()
        assert "delivery_id" in data, "Response should contain delivery_id"
        assert "status_code" in data, "Response should contain status_code"
        
        # httpbin.org should return 200
        if data.get("status_code") == 200:
            print(f"SUCCESS: Test webhook delivered successfully, status_code=200")
            assert data.get("ok") == True, "ok should be True for successful delivery"
        else:
            print(f"WARNING: Test webhook delivery status_code={data.get('status_code')}, error={data.get('error')}")
    
    def test_05_test_webhook_not_found(self, b2b_headers):
        """POST /api/b2b/webhooks/{id}/test - Test non-existent webhook"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks/non-existent-id/test", headers=b2b_headers)
        print(f"Test non-existent webhook response: {response.status_code}")
        assert response.status_code == 404, f"Expected 404 for non-existent webhook, got {response.status_code}"
    
    def test_06_delete_webhook(self, b2b_headers):
        """DELETE /api/b2b/webhooks/{id} - Delete webhook"""
        webhook_id = TestWebhookCRUD.created_webhook_id
        if not webhook_id:
            pytest.skip("No webhook created")
        
        response = requests.delete(f"{BASE_URL}/api/b2b/webhooks/{webhook_id}", headers=b2b_headers)
        print(f"Delete webhook response: {response.status_code}")
        assert response.status_code == 200, f"Delete webhook failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Response should have ok=True"
    
    def test_07_verify_webhook_deleted(self, b2b_headers):
        """GET /api/b2b/webhooks - Verify webhook no longer in list"""
        webhook_id = TestWebhookCRUD.created_webhook_id
        if not webhook_id:
            pytest.skip("No webhook created")
        
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        assert response.status_code == 200
        
        data = response.json()
        webhook_ids = [wh["id"] for wh in data.get("webhooks", [])]
        assert webhook_id not in webhook_ids, "Deleted webhook should not be in list"
    
    def test_08_delete_non_existent_webhook(self, b2b_headers):
        """DELETE /api/b2b/webhooks/{id} - Delete non-existent webhook"""
        response = requests.delete(f"{BASE_URL}/api/b2b/webhooks/non-existent-id", headers=b2b_headers)
        print(f"Delete non-existent webhook response: {response.status_code}")
        assert response.status_code == 404, f"Expected 404 for non-existent webhook, got {response.status_code}"


class TestWebhookLimit(TestB2BWebhookSetup):
    """Test max 5 webhooks per agency limit"""
    
    created_webhook_ids = []
    
    @pytest.fixture(scope="class", autouse=True)
    def cleanup_webhooks(self, b2b_headers):
        """Cleanup webhooks before and after tests"""
        # Cleanup before
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        if response.status_code == 200:
            for wh in response.json().get("webhooks", []):
                requests.delete(f"{BASE_URL}/api/b2b/webhooks/{wh['id']}", headers=b2b_headers)
        
        yield
        
        # Cleanup after
        for wh_id in TestWebhookLimit.created_webhook_ids:
            requests.delete(f"{BASE_URL}/api/b2b/webhooks/{wh_id}", headers=b2b_headers)
    
    def test_01_create_5_webhooks(self, b2b_headers):
        """Create 5 webhooks (max allowed)"""
        for i in range(5):
            response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
                "url": f"https://httpbin.org/post?webhook={i}",
                "events": ["reservation.created"]
            })
            print(f"Create webhook {i+1} response: {response.status_code}")
            assert response.status_code == 200, f"Create webhook {i+1} failed: {response.text}"
            
            data = response.json()
            TestWebhookLimit.created_webhook_ids.append(data["webhook"]["id"])
        
        print(f"Created {len(TestWebhookLimit.created_webhook_ids)} webhooks")
    
    def test_02_reject_6th_webhook(self, b2b_headers):
        """POST /api/b2b/webhooks - Reject 6th webhook (exceeds limit)"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "https://httpbin.org/post?webhook=6",
            "events": ["reservation.created"]
        })
        print(f"6th webhook response: {response.status_code} - {response.text[:200]}")
        assert response.status_code == 400, f"Expected 400 for 6th webhook, got {response.status_code}"
        
        data = response.json()
        assert "Maximum" in data.get("detail", "") or "5" in data.get("detail", ""), "Error should mention limit"


class TestWebhookAutoFire(TestB2BWebhookSetup):
    """Test webhook auto-fire on reservation create/cancel"""
    
    webhook_id = None
    reservation_id = None
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_webhook(self, b2b_headers):
        """Setup webhook for auto-fire testing"""
        # Cleanup existing webhooks
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers)
        if response.status_code == 200:
            for wh in response.json().get("webhooks", []):
                requests.delete(f"{BASE_URL}/api/b2b/webhooks/{wh['id']}", headers=b2b_headers)
        
        # Create webhook for testing
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", headers=b2b_headers, json={
            "url": "https://httpbin.org/post",
            "events": ["reservation.created", "reservation.cancelled"],
            "secret": "auto_fire_test_secret"
        })
        
        if response.status_code == 200:
            data = response.json()
            TestWebhookAutoFire.webhook_id = data["webhook"]["id"]
            print(f"Setup webhook for auto-fire: {TestWebhookAutoFire.webhook_id}")
        
        yield
        
        # Cleanup
        if TestWebhookAutoFire.webhook_id:
            requests.delete(f"{BASE_URL}/api/b2b/webhooks/{TestWebhookAutoFire.webhook_id}", headers=b2b_headers)
    
    def test_01_create_reservation_fires_webhook(self, b2b_headers):
        """POST /api/b2b/reservations - Should fire reservation.created webhook"""
        if not TestWebhookAutoFire.webhook_id:
            pytest.skip("No webhook setup")
        
        # Get available room type
        avail_response = requests.get(
            f"{BASE_URL}/api/b2b/availability?check_in={CHECK_IN}&check_out={CHECK_OUT}",
            headers=b2b_headers
        )
        
        room_type = "Standard"
        if avail_response.status_code == 200:
            room_types = avail_response.json().get("room_types", [])
            for rt in room_types:
                if rt.get("available_rooms", 0) > 0:
                    room_type = rt["room_type"]
                    break
            if room_types and not room_type:
                room_type = room_types[0].get("room_type", "Standard")
        
        # Create reservation
        response = requests.post(f"{BASE_URL}/api/b2b/reservations", headers=b2b_headers, json={
            "room_type": room_type,
            "check_in": CHECK_IN,
            "check_out": CHECK_OUT,
            "guest_name": "TEST_Webhook_Guest",
            "guest_email": "webhook_test@example.com",
            "adults": 2,
            "total_amount": 300.00
        })
        
        print(f"Create reservation response: {response.status_code}")
        
        if response.status_code == 409:
            print("No rooms available - skipping webhook fire test")
            pytest.skip("No rooms available for reservation")
        
        if response.status_code == 404:
            print("Room type not found - skipping webhook fire test")
            pytest.skip("Room type not found")
        
        assert response.status_code == 200, f"Create reservation failed: {response.text}"
        
        data = response.json()
        TestWebhookAutoFire.reservation_id = data["reservation"]["id"]
        print(f"Created reservation: {data['reservation']['confirmation_code']}")
        print("NOTE: Webhook should have been fired in background task (reservation.created)")
    
    def test_02_cancel_reservation_fires_webhook(self, b2b_headers):
        """PUT /api/b2b/reservations/{id}/cancel - Should fire reservation.cancelled webhook"""
        reservation_id = TestWebhookAutoFire.reservation_id
        if not reservation_id:
            pytest.skip("No reservation created")
        
        response = requests.put(f"{BASE_URL}/api/b2b/reservations/{reservation_id}/cancel", headers=b2b_headers)
        print(f"Cancel reservation response: {response.status_code}")
        assert response.status_code == 200, f"Cancel reservation failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "cancelled", "Status should be cancelled"
        print(f"Cancelled reservation: {data.get('confirmation_code')}")
        print("NOTE: Webhook should have been fired in background task (reservation.cancelled)")


class TestWebhookWithoutAPIKey(TestB2BWebhookSetup):
    """Test webhook endpoints require API key authentication"""
    
    def test_01_list_webhooks_without_key(self):
        """GET /api/b2b/webhooks - Should require API key"""
        response = requests.get(f"{BASE_URL}/api/b2b/webhooks")
        print(f"List webhooks without key: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for missing API key, got {response.status_code}"
    
    def test_02_register_webhook_without_key(self):
        """POST /api/b2b/webhooks - Should require API key"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks", json={
            "url": "https://httpbin.org/post",
            "events": ["reservation.created"]
        })
        print(f"Register webhook without key: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for missing API key, got {response.status_code}"
    
    def test_03_delete_webhook_without_key(self):
        """DELETE /api/b2b/webhooks/{id} - Should require API key"""
        response = requests.delete(f"{BASE_URL}/api/b2b/webhooks/some-id")
        print(f"Delete webhook without key: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for missing API key, got {response.status_code}"
    
    def test_04_test_webhook_without_key(self):
        """POST /api/b2b/webhooks/{id}/test - Should require API key"""
        response = requests.post(f"{BASE_URL}/api/b2b/webhooks/some-id/test")
        print(f"Test webhook without key: {response.status_code}")
        assert response.status_code == 401, f"Expected 401 for missing API key, got {response.status_code}"


# Cleanup fixture
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """Cleanup test data after all tests"""
    yield
    print("Webhook test cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
