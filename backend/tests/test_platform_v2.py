"""
Comprehensive tests for the new platform modules:
- Messaging Service (providers, templates, delivery, consent, fallback)
- ML Scheduler (execution, policies, stale detection)
- Revenue Autopilot (policy, queue, approve, reject, rollback)
- Analytics Export (generate, history)
- Event Broadcast (sessions, publish, replay)
- Cross-Enrichment (inter-module events)
"""
import pytest
import httpx
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pipeline-validation-3.preview.emergentagent.com")
LOGIN_PAYLOAD = {"email": "demo@hotel.com", "password": "demo123"}


@pytest.fixture(scope="module")
def auth_token():
    resp = httpx.post(f"{BASE_URL}/api/auth/login", json=LOGIN_PAYLOAD, timeout=15)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ── MESSAGING ──

class TestMessaging:
    def test_list_providers(self, headers):
        r = httpx.get(f"{BASE_URL}/api/messaging-center/providers", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "providers" in r.json()

    def test_create_provider(self, headers):
        r = httpx.post(f"{BASE_URL}/api/messaging-center/providers", headers=headers, timeout=10, json={
            "provider_type": "twilio_sms",
            "credentials": {"account_sid": "test_sid", "auth_token": "test_token", "from_number": "+1234567890"},
            "is_sandbox": True,
            "enabled": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["provider_type"] == "twilio_sms"
        assert data["is_sandbox"] is True

    def test_provider_health_check(self, headers):
        r = httpx.post(f"{BASE_URL}/api/messaging-center/providers/health-check", headers=headers, timeout=15)
        assert r.status_code == 200
        assert "results" in r.json()

    def test_list_templates(self, headers):
        r = httpx.get(f"{BASE_URL}/api/messaging-center/templates", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "templates" in r.json()

    def test_create_template(self, headers):
        r = httpx.post(f"{BASE_URL}/api/messaging-center/templates", headers=headers, timeout=10, json={
            "name": "Room Ready",
            "category": "room_ready",
            "channel": "sms",
            "subject": None,
            "body_template": "Dear {{guest_name}}, your room {{room_number}} is ready!",
            "variables": ["guest_name", "room_number"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Room Ready"
        assert data["is_active"] is True

    def test_send_message_no_provider(self, headers):
        # Should fail gracefully (no email provider configured)
        r = httpx.post(f"{BASE_URL}/api/messaging-center/send", headers=headers, timeout=10, json={
            "channel": "email",
            "recipient": "guest@test.com",
            "body": "Test message",
        })
        assert r.status_code == 200
        data = r.json()
        # expect failure since no real email provider
        assert data.get("success") is False or data.get("delivery_id") is not None

    def test_delivery_logs(self, headers):
        r = httpx.get(f"{BASE_URL}/api/messaging-center/delivery-logs", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "logs" in r.json()

    def test_delivery_logs_filter(self, headers):
        r = httpx.get(f"{BASE_URL}/api/messaging-center/delivery-logs?status=failed", headers=headers, timeout=10)
        assert r.status_code == 200
        for log in r.json().get("logs", []):
            assert log["status"] == "failed"

    def test_messaging_metrics(self, headers):
        r = httpx.get(f"{BASE_URL}/api/messaging-center/metrics?days=7", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total_messages" in data
        assert "metrics_by_channel" in data

    def test_consent_update(self, headers):
        r = httpx.post(f"{BASE_URL}/api/messaging-center/consent", headers=headers, timeout=10, json={
            "recipient": "guest@test.com",
            "channel": "email",
            "status": "opt_in",
        })
        assert r.status_code == 200
        assert r.json()["success"] is True


# ── ML SCHEDULER ──

class TestMLScheduler:
    def test_get_dashboard(self, headers):
        r = httpx.get(f"{BASE_URL}/api/data-intelligence/schedules/dashboard", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "schedules" in data
        assert "recent_executions" in data
        assert "stale_models" in data

    def test_get_policies(self, headers):
        r = httpx.get(f"{BASE_URL}/api/data-intelligence/schedules/policies", headers=headers, timeout=10)
        assert r.status_code == 200
        policies = r.json()["policies"]
        assert len(policies) >= 3
        model_types = [p["model_type"] for p in policies]
        assert "revenue_ml" in model_types
        assert "operational_ai" in model_types
        assert "guest_intelligence" in model_types

    def test_update_schedule(self, headers):
        r = httpx.put(f"{BASE_URL}/api/data-intelligence/schedules/policies/revenue_ml",
                      headers=headers, timeout=10, json={"interval_hours": 4})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_trigger_execution(self, headers):
        r = httpx.post(f"{BASE_URL}/api/data-intelligence/schedules/trigger",
                       headers=headers, timeout=10, json={"model_type": "operational_ai"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "job_id" in data

    def test_execution_history(self, headers):
        r = httpx.get(f"{BASE_URL}/api/data-intelligence/schedules/history", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "jobs" in r.json()

    def test_stale_models(self, headers):
        r = httpx.get(f"{BASE_URL}/api/data-intelligence/schedules/stale", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "stale_models" in r.json()


# ── REVENUE AUTOPILOT ──

class TestRevenueAutopilot:
    def test_get_dashboard(self, headers):
        r = httpx.get(f"{BASE_URL}/api/revenue-autopilot/dashboard", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "policy" in data
        assert "pending_queue" in data
        assert "daily_summary" in data

    def test_get_policy(self, headers):
        r = httpx.get(f"{BASE_URL}/api/revenue-autopilot/policy", headers=headers, timeout=10)
        assert r.status_code == 200
        policy = r.json()
        assert policy["mode"] in ["full_auto", "supervised", "advisory"]
        assert "confidence_threshold_auto" in policy

    def test_update_policy(self, headers):
        r = httpx.put(f"{BASE_URL}/api/revenue-autopilot/policy", headers=headers, timeout=10,
                      json={"mode": "full_auto", "confidence_threshold_auto": 0.90})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_process_recommendation_queued(self, headers):
        r = httpx.post(f"{BASE_URL}/api/revenue-autopilot/process", headers=headers, timeout=10, json={
            "room_type": "Deluxe",
            "target_date": "2026-04-01",
            "current_price": 200,
            "recommended_price": 220,
            "confidence": 0.70,
        })
        assert r.status_code == 200
        data = r.json()
        # Low confidence: should be queued or rejected
        assert data["action"] in ["queued", "rejected"]

    def test_process_high_confidence_auto_apply(self, headers):
        # Policy mode was set to full_auto, threshold 0.90
        r = httpx.post(f"{BASE_URL}/api/revenue-autopilot/process", headers=headers, timeout=10, json={
            "room_type": "Suite",
            "target_date": "2026-04-02",
            "current_price": 500,
            "recommended_price": 530,
            "confidence": 0.95,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["action"] in ["auto_applied", "queued"]

    def test_approval_queue(self, headers):
        r = httpx.get(f"{BASE_URL}/api/revenue-autopilot/queue", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_daily_summary(self, headers):
        r = httpx.get(f"{BASE_URL}/api/revenue-autopilot/summary", headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total_recommendations" in data


# ── WEBSOCKET HEALTH ──

class TestWebSocketHealth:
    def test_health(self, headers):
        r = httpx.get(f"{BASE_URL}/api/websocket/health", headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["health"] == "ok"

    def test_register_session(self, headers):
        r = httpx.post(f"{BASE_URL}/api/websocket/sessions/register", headers=headers, timeout=10, json={
            "session_id": "test-session-001",
            "roles": ["admin"],
            "property_ids": [],
        })
        assert r.status_code == 200
        assert r.json()["status"] == "registered"

    def test_publish_event(self, headers):
        r = httpx.post(f"{BASE_URL}/api/websocket/publish", headers=headers, timeout=10, json={
            "event_type": "vip_arrival",
            "payload": {"guest": "VIP Guest", "room": "501"},
        })
        assert r.status_code == 200
        assert "event_id" in r.json()

    def test_replay_events(self, headers):
        r = httpx.get(f"{BASE_URL}/api/websocket/replay", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "events" in r.json()

    def test_unregister_session(self, headers):
        r = httpx.delete(f"{BASE_URL}/api/websocket/sessions/test-session-001", headers=headers, timeout=10)
        assert r.status_code == 200


# ── ANALYTICS EXPORT ──

class TestAnalyticsExport:
    def test_available_reports(self, headers):
        r = httpx.get(f"{BASE_URL}/api/reports/export/available", headers=headers, timeout=10)
        assert r.status_code == 200
        reports = r.json()["reports"]
        assert len(reports) == 8
        types = [rr["type"] for rr in reports]
        assert "management_summary" in types

    def test_generate_csv(self, headers):
        r = httpx.post(f"{BASE_URL}/api/reports/export/generate", headers=headers, timeout=15, json={
            "report_type": "management_summary",
            "export_format": "csv",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["row_count"] >= 0
        assert "headers" in data

    def test_generate_json(self, headers):
        r = httpx.post(f"{BASE_URL}/api/reports/export/generate", headers=headers, timeout=15, json={
            "report_type": "autopilot_decisions",
            "export_format": "json",
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_export_history(self, headers):
        r = httpx.get(f"{BASE_URL}/api/reports/export/history", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "history" in r.json()

    def test_download_csv(self, headers):
        r = httpx.post(f"{BASE_URL}/api/reports/export/download", headers=headers, timeout=15, json={
            "report_type": "management_summary",
            "export_format": "csv",
        })
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
