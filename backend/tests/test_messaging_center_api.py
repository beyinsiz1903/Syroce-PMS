"""
Messaging Center API Tests
Tests for Email (SMTP) and WhatsApp Business API messaging integration.
Endpoints: settings, templates CRUD, send message, delivery logs, metrics, retry.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://guest-list-hub.preview.emergentagent.com"


class TestMessagingCenterAPI:
    """Messaging Center API endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Seed demo data first
        seed_resp = self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")
        # Seed may return success or "already seeded" - both are fine
        assert seed_resp.status_code == 200

    # ═══════════════════════════════════════════════
    # Settings Endpoints
    # ═══════════════════════════════════════════════

    def test_get_messaging_settings(self):
        """GET /api/messaging-center/settings - returns email and whatsapp config"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/settings")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should have email and whatsapp keys
        assert "email" in data, "Missing 'email' key in settings"
        assert "whatsapp" in data, "Missing 'whatsapp' key in settings"
        
        # Email config should have masked credentials
        if data["email"]:
            assert "credentials" in data["email"]
            assert "is_sandbox" in data["email"]
            assert "enabled" in data["email"]
            print(f"Email config: sandbox={data['email']['is_sandbox']}, enabled={data['email']['enabled']}")
        
        # WhatsApp config should have masked credentials
        if data["whatsapp"]:
            assert "credentials" in data["whatsapp"]
            assert "is_sandbox" in data["whatsapp"]
            assert "enabled" in data["whatsapp"]
            print(f"WhatsApp config: sandbox={data['whatsapp']['is_sandbox']}, enabled={data['whatsapp']['enabled']}")

    def test_save_email_settings(self):
        """POST /api/messaging-center/settings/email - save SMTP settings"""
        payload = {
            "smtp_host": "smtp.test.com",
            "smtp_port": 587,
            "smtp_username": "test@test.com",
            "smtp_password": "testpass123",
            "from_email": "noreply@test.com",
            "from_name": "Test Hotel",
            "use_tls": True,
            "is_sandbox": True,
            "enabled": True
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/settings/email", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        assert data.get("action") in ["created", "updated"]
        assert "id" in data
        print(f"Email settings {data['action']}, id={data['id']}")

    def test_save_whatsapp_settings(self):
        """POST /api/messaging-center/settings/whatsapp - save WhatsApp settings"""
        payload = {
            "access_token": "test_access_token_12345",
            "phone_number_id": "123456789012345",
            "business_name": "Test Hotel WhatsApp",
            "is_sandbox": True,
            "enabled": True
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/settings/whatsapp", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        assert data.get("action") in ["created", "updated"]
        assert "id" in data
        print(f"WhatsApp settings {data['action']}, id={data['id']}")

    # ═══════════════════════════════════════════════
    # Templates CRUD
    # ═══════════════════════════════════════════════

    def test_list_templates(self):
        """GET /api/messaging-center/templates - list all templates"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/templates")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "templates" in data
        templates = data["templates"]
        assert isinstance(templates, list)
        print(f"Found {len(templates)} templates")
        
        # Should have seeded templates (9 total: 5 WhatsApp + 4 Email)
        if len(templates) >= 9:
            print("Seeded templates present")
            # Check template structure
            for t in templates[:3]:
                assert "id" in t
                assert "name" in t
                assert "channel" in t
                assert "category" in t
                assert "body_template" in t

    def test_list_templates_filter_by_channel(self):
        """GET /api/messaging-center/templates?channel=whatsapp - filter by channel"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/templates?channel=whatsapp")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        templates = data.get("templates", [])
        for t in templates:
            assert t["channel"] == "whatsapp", f"Expected whatsapp, got {t['channel']}"
        print(f"Found {len(templates)} WhatsApp templates")

    def test_create_template(self):
        """POST /api/messaging-center/templates - create new template"""
        payload = {
            "name": "TEST_Ozel Teklif",
            "category": "kampanya",
            "channel": "email",
            "subject": "Ozel Firsat - {{otel_adi}}",
            "body_template": "Sayin {{misafir_adi}}, size ozel %{{indirim}} indirim sunuyoruz!",
            "variables": ["misafir_adi", "otel_adi", "indirim"]
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/templates", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["channel"] == "email"
        assert data["category"] == "kampanya"
        print(f"Created template: {data['id']}")
        
        # Store for update/delete tests
        self.__class__.created_template_id = data["id"]

    def test_update_template(self):
        """PUT /api/messaging-center/templates/{id} - update template"""
        template_id = getattr(self.__class__, "created_template_id", None)
        if not template_id:
            # Create one first
            create_resp = self.session.post(f"{BASE_URL}/api/messaging-center/templates", json={
                "name": "TEST_Update Template",
                "category": "genel",
                "channel": "whatsapp",
                "body_template": "Original message"
            })
            template_id = create_resp.json().get("id")
        
        update_payload = {
            "name": "TEST_Updated Template Name",
            "body_template": "Updated message content {{var1}}"
        }
        resp = self.session.put(f"{BASE_URL}/api/messaging-center/templates/{template_id}", json=update_payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        print(f"Updated template: {template_id}")

    def test_delete_template(self):
        """DELETE /api/messaging-center/templates/{id} - delete template"""
        # Create a template to delete
        create_resp = self.session.post(f"{BASE_URL}/api/messaging-center/templates", json={
            "name": "TEST_To Delete",
            "category": "genel",
            "channel": "email",
            "body_template": "This will be deleted"
        })
        template_id = create_resp.json().get("id")
        assert template_id, "Failed to create template for deletion"
        
        # Delete it
        resp = self.session.delete(f"{BASE_URL}/api/messaging-center/templates/{template_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        print(f"Deleted template: {template_id}")
        
        # Verify it's gone
        get_resp = self.session.get(f"{BASE_URL}/api/messaging-center/templates")
        templates = get_resp.json().get("templates", [])
        ids = [t["id"] for t in templates]
        assert template_id not in ids, "Template still exists after deletion"

    # ═══════════════════════════════════════════════
    # Send Message (Sandbox Mode)
    # ═══════════════════════════════════════════════

    def test_send_message_email(self):
        """POST /api/messaging-center/send - send email (sandbox mode)"""
        payload = {
            "channel": "email",
            "recipient": "test@example.com",
            "subject": "Test Email Subject",
            "body": "This is a test email body from sandbox mode.",
            "use_case": "test"
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/send", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, f"Send failed: {data.get('error')}"
        assert "delivery_id" in data
        print(f"Email sent (sandbox), delivery_id={data['delivery_id']}")

    def test_send_message_whatsapp(self):
        """POST /api/messaging-center/send - send WhatsApp (sandbox mode)"""
        payload = {
            "channel": "whatsapp",
            "recipient": "+905551234567",
            "body": "Merhaba, bu bir test mesajidir.",
            "use_case": "hosgeldiniz"
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/send", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, f"Send failed: {data.get('error')}"
        assert "delivery_id" in data
        print(f"WhatsApp sent (sandbox), delivery_id={data['delivery_id']}")

    def test_send_message_with_template(self):
        """POST /api/messaging-center/send - send with template and variables"""
        # Get a template first
        templates_resp = self.session.get(f"{BASE_URL}/api/messaging-center/templates?channel=whatsapp")
        templates = templates_resp.json().get("templates", [])
        
        if not templates:
            pytest.skip("No WhatsApp templates available")
        
        template = templates[0]
        payload = {
            "channel": "whatsapp",
            "recipient": "+905559876543",
            "template_id": template["id"],
            "variables": {
                "misafir_adi": "Ahmet Bey",
                "otel_adi": "Test Otel"
            }
        }
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/send", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, f"Send failed: {data.get('error')}"
        print(f"Template message sent, delivery_id={data['delivery_id']}")

    # ═══════════════════════════════════════════════
    # Delivery Logs
    # ═══════════════════════════════════════════════

    def test_get_delivery_logs(self):
        """GET /api/messaging-center/delivery-logs - list delivery logs"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "logs" in data
        logs = data["logs"]
        assert isinstance(logs, list)
        print(f"Found {len(logs)} delivery logs")
        
        # Check log structure
        if logs:
            log = logs[0]
            assert "id" in log
            assert "channel" in log
            assert "recipient" in log
            assert "status" in log
            assert "created_at" in log

    def test_get_delivery_logs_filter_by_status(self):
        """GET /api/messaging-center/delivery-logs?status=sent - filter by status"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs?status=sent")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        logs = data.get("logs", [])
        for log in logs:
            assert log["status"] == "sent", f"Expected sent, got {log['status']}"
        print(f"Found {len(logs)} sent logs")

    def test_get_delivery_logs_filter_by_channel(self):
        """GET /api/messaging-center/delivery-logs?channel=email - filter by channel"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs?channel=email")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        logs = data.get("logs", [])
        for log in logs:
            assert log["channel"] == "email", f"Expected email, got {log['channel']}"
        print(f"Found {len(logs)} email logs")

    # ═══════════════════════════════════════════════
    # Retry Failed Delivery
    # ═══════════════════════════════════════════════

    def test_retry_delivery(self):
        """POST /api/messaging-center/retry/{id} - retry failed delivery"""
        # Get a failed delivery log
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs?status=failed")
        logs = resp.json().get("logs", [])
        
        if not logs:
            # Create a failed delivery by sending to invalid recipient (won't fail in sandbox)
            # Just test with any delivery
            all_logs = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs").json().get("logs", [])
            if not all_logs:
                pytest.skip("No delivery logs available for retry test")
            delivery_id = all_logs[0]["id"]
        else:
            delivery_id = logs[0]["id"]
        
        retry_resp = self.session.post(f"{BASE_URL}/api/messaging-center/retry/{delivery_id}")
        assert retry_resp.status_code == 200, f"Failed: {retry_resp.text}"
        data = retry_resp.json()
        
        # May succeed or fail based on retry count
        print(f"Retry result: success={data.get('success')}, error={data.get('error')}")

    # ═══════════════════════════════════════════════
    # Metrics
    # ═══════════════════════════════════════════════

    def test_get_metrics(self):
        """GET /api/messaging-center/metrics - delivery metrics by channel"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/metrics")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "metrics_by_channel" in data
        assert "total_messages" in data
        assert "period_days" in data
        
        print(f"Total messages: {data['total_messages']}, period: {data['period_days']} days")
        print(f"Metrics by channel: {data['metrics_by_channel']}")

    def test_get_metrics_custom_period(self):
        """GET /api/messaging-center/metrics?days=30 - metrics with custom period"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/metrics?days=30")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data["period_days"] == 30
        print(f"30-day metrics: {data['total_messages']} total messages")

    # ═══════════════════════════════════════════════
    # Seed Demo Data
    # ═══════════════════════════════════════════════

    def test_seed_demo_data(self):
        """POST /api/messaging-center/seed-demo - seed demo templates and logs"""
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        # May return "already seeded" message or template/log counts
        print(f"Seed result: {data}")


# Cleanup test data
class TestCleanup:
    """Cleanup TEST_ prefixed data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        if login_resp.status_code == 200:
            data = login_resp.json()
            token = data.get("access_token") or data.get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def test_cleanup_test_templates(self):
        """Cleanup TEST_ prefixed templates"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/templates")
        if resp.status_code != 200:
            return
        
        templates = resp.json().get("templates", [])
        deleted = 0
        for t in templates:
            if t.get("name", "").startswith("TEST_"):
                del_resp = self.session.delete(f"{BASE_URL}/api/messaging-center/templates/{t['id']}")
                if del_resp.status_code == 200:
                    deleted += 1
        
        print(f"Cleaned up {deleted} test templates")
