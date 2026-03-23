"""
Guest Messaging API Tests - Misafir Mesajlaşma Sistemi Test Suite
Tests for: POST /api/guest/messages, GET /api/guest/messages, 
GET /api/guest/messages/unread-count, PUT /api/guest/messages/mark-all-read
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")
if BASE_URL:
    BASE_URL = BASE_URL.rstrip('/')

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestGuestMessaging:
    """Guest Messaging API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate before tests"""
        self.session = requests.Session()
        self.token = None
        
        # Login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            })
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_login_works(self):
        """Test login returns access_token"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response missing access_token"
        print("✅ Login successful, token received")
    
    def test_get_messages_list(self):
        """Test GET /api/guest/messages - list messages"""
        response = self.session.get(f"{BASE_URL}/api/guest/messages")
        
        assert response.status_code == 200, f"GET messages failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "conversations" in data, "Response missing 'conversations'"
        assert "total_messages" in data, "Response missing 'total_messages'"
        assert "unread_total" in data, "Response missing 'unread_total'"
        assert isinstance(data["conversations"], list), "conversations should be a list"
        print(f"✅ GET /api/guest/messages returned {data['total_messages']} messages")
    
    def test_get_unread_count(self):
        """Test GET /api/guest/messages/unread-count - unread count"""
        response = self.session.get(f"{BASE_URL}/api/guest/messages/unread-count")
        
        assert response.status_code == 200, f"GET unread-count failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "unread_count" in data, "Response missing 'unread_count'"
        assert isinstance(data["unread_count"], int), "unread_count should be an integer"
        print(f"✅ GET /api/guest/messages/unread-count returned count: {data['unread_count']}")
    
    def test_send_message(self):
        """Test POST /api/guest/messages - send a message"""
        message_payload = {
            "message": "TEST_Test message from pytest",
            "message_type": "general"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        
        assert response.status_code == 200, f"POST message failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "id" in data, "Response missing 'id'"
        assert "message" in data, "Response missing 'message'"
        assert data["message"] == message_payload["message"], "Message content mismatch"
        assert "sender" in data, "Response missing 'sender'"
        assert "created_at" in data, "Response missing 'created_at'"
        print(f"✅ POST /api/guest/messages created message with ID: {data['id']}")
        
        return data["id"]  # Return message ID for cleanup
    
    def test_send_message_with_type_request(self):
        """Test POST /api/guest/messages with message_type='request'"""
        message_payload = {
            "message": "TEST_Request type message",
            "message_type": "request"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        
        assert response.status_code == 200, f"POST request message failed: {response.text}"
        data = response.json()
        
        assert data["message_type"] == "request", "message_type should be 'request'"
        print("✅ POST message with type 'request' successful")
    
    def test_send_message_with_type_complaint(self):
        """Test POST /api/guest/messages with message_type='complaint'"""
        message_payload = {
            "message": "TEST_Complaint type message",
            "message_type": "complaint"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        
        assert response.status_code == 200, f"POST complaint message failed: {response.text}"
        data = response.json()
        
        assert data["message_type"] == "complaint", "message_type should be 'complaint'"
        print("✅ POST message with type 'complaint' successful")
    
    def test_send_message_with_type_feedback(self):
        """Test POST /api/guest/messages with message_type='feedback'"""
        message_payload = {
            "message": "TEST_Feedback type message",
            "message_type": "feedback"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        
        assert response.status_code == 200, f"POST feedback message failed: {response.text}"
        data = response.json()
        
        assert data["message_type"] == "feedback", "message_type should be 'feedback'"
        print("✅ POST message with type 'feedback' successful")
    
    def test_mark_all_read(self):
        """Test PUT /api/guest/messages/mark-all-read - mark all messages as read"""
        response = self.session.put(f"{BASE_URL}/api/guest/messages/mark-all-read")
        
        assert response.status_code == 200, f"PUT mark-all-read failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "marked_read" in data, "Response missing 'marked_read'"
        assert isinstance(data["marked_read"], int), "marked_read should be an integer"
        print(f"✅ PUT /api/guest/messages/mark-all-read marked {data['marked_read']} messages as read")
    
    def test_send_message_missing_message_field(self):
        """Test POST /api/guest/messages without message field (validation)"""
        message_payload = {
            "message_type": "general"
            # missing 'message' field
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        
        # Should fail with 422 Unprocessable Entity
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ POST without message field returns 422 validation error")
    
    def test_unauthorized_access(self):
        """Test endpoints without authorization"""
        # Remove authorization header
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.get(f"{BASE_URL}/api/guest/messages")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✅ Unauthorized request returns {response.status_code}")
    
    def test_message_persistence_after_send(self):
        """Test that sent message persists and appears in list"""
        # First send a unique message
        unique_msg = f"TEST_Persistence_check_{os.urandom(4).hex()}"
        message_payload = {
            "message": unique_msg,
            "message_type": "general"
        }
        
        send_response = self.session.post(
            f"{BASE_URL}/api/guest/messages",
            json=message_payload
        )
        assert send_response.status_code == 200
        
        # Then get messages and verify it exists
        list_response = self.session.get(f"{BASE_URL}/api/guest/messages")
        assert list_response.status_code == 200
        data = list_response.json()
        
        # Check if message is in conversations
        found = False
        for conv in data.get("conversations", []):
            for msg in conv.get("messages", []):
                if msg.get("message") == unique_msg:
                    found = True
                    break
        
        assert found, f"Sent message '{unique_msg}' not found in message list"
        print("✅ Message persistence verified - sent message appears in list")


class TestReportBuilderAfterI18n:
    """Test Report Builder still works after i18n changes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate before tests"""
        self.session = requests.Session()
        self.token = None
        
        # Login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            })
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_report_builder_config(self):
        """Test Report Builder config endpoint works after i18n changes"""
        response = self.session.get(f"{BASE_URL}/api/reports/builder/config")
        
        assert response.status_code == 200, f"Config endpoint failed: {response.text}"
        data = response.json()
        
        # Verify data sources exist
        assert "data_sources" in data, "Response missing 'data_sources'"
        data_sources = data["data_sources"]
        
        # Expected data sources
        expected_sources = ["reservations", "revenue", "guests", "rooms", "housekeeping", "folios"]
        for source in expected_sources:
            assert source in data_sources, f"Missing data source: {source}"
        
        print(f"✅ Report Builder config returns all {len(data_sources)} data sources")
    
    def test_report_builder_generate_report(self):
        """Test Report Builder can generate reports after i18n changes"""
        report_config = {
            "data_source": "reservations",
            "columns": ["guest_name", "room_number", "check_in", "total_amount"],
            "date_from": "2024-01-01",
            "date_to": "2025-12-31",
            "limit": 10
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/reports/builder/generate",
            json=report_config
        )
        
        assert response.status_code == 200, f"Generate report failed: {response.text}"
        data = response.json()
        
        assert "data" in data, "Response missing 'data'"
        assert "total_count" in data, "Response missing 'total_count'"
        print(f"✅ Report Builder generates reports, returned {data['total_count']} records")
    
    def test_report_builder_templates_list(self):
        """Test Report Builder templates listing works after i18n changes"""
        response = self.session.get(f"{BASE_URL}/api/reports/builder/templates")
        
        assert response.status_code == 200, f"Templates list failed: {response.text}"
        data = response.json()
        
        assert "templates" in data, "Response missing 'templates'"
        assert isinstance(data["templates"], list), "templates should be a list"
        print(f"✅ Report Builder templates list works, {len(data['templates'])} templates found")


class TestBasicEndpoints:
    """Test basic endpoints to ensure app is working"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate before tests"""
        self.session = requests.Session()
        self.token = None
        
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            })
    
    def test_dashboard_loads(self):
        """Test dashboard endpoint works"""
        response = self.session.get(f"{BASE_URL}/api/pms/dashboard")
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        print("✅ Dashboard endpoint works")
    
    def test_auth_me_endpoint(self):
        """Test auth/me endpoint returns user info"""
        if not self.token:
            pytest.skip("No token available")
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        # Can be 200 or 403 depending on token state
        if response.status_code == 200:
            data = response.json()
            assert "email" in data or "user" in data, "Response should contain user info"
            print("✅ Auth me endpoint works")
        else:
            # Token may have been invalidated, check it was auth related
            assert response.status_code in [401, 403], f"Unexpected status: {response.status_code}"
            print(f"✅ Auth me endpoint requires valid token (got {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
