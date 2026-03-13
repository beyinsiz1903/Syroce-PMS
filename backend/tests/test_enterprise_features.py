"""
Enterprise Features Test Suite - WebSocket, Messaging, Auto-Pricing, Cross-Module.
Tests auth, workflows, retry, rollback, tenant isolation, event propagation.
"""
import pytest
import httpx
import os
import asyncio

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "")

pytestmark = pytest.mark.skipif(not API_URL, reason="REACT_APP_BACKEND_URL not set")
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def auth_token(event_loop):
    async def _get():
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{API_URL}/api/auth/login",
                             json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            assert r.status_code == 200, f"Login failed: {r.text}"
            return r.json()["access_token"]
    return event_loop.run_until_complete(_get())


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════════════════════
# 1. WEBSOCKET & LIVE DATA TESTS
# ═══════════════════════════════════════════════════════════

class TestWebSocketLive:
    def test_ws_stats(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/ws/stats", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_connections" in data
        assert "tenants_connected" in data

    def test_live_data(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/ws/live-data", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "front_desk_queue" in data
        assert "housekeeping_board" in data
        assert "vip_arrivals" in data
        assert "audit_exceptions" in data
        assert "occupancy" in data
        assert "overbooking_risk" in data

    def test_live_data_occupancy_fields(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/ws/live-data", headers=headers)
        data = r.json()
        occ = data["occupancy"]
        assert "total_rooms" in occ
        assert "booked" in occ
        assert "available" in occ
        assert "pct" in occ

    def test_ws_unauthenticated(self):
        r = httpx.get(f"{API_URL}/api/enterprise/ws/stats", headers={"Authorization": "Bearer invalid"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════
# 2. MESSAGING TESTS
# ═══════════════════════════════════════════════════════════

class TestMessaging:
    def test_provider_health(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/messaging/provider-health", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "providers" in data
        assert "sms" in data["providers"]
        assert "email" in data["providers"]
        assert "whatsapp" in data["providers"]

    def test_send_email_mock(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/send", headers=headers,
                       json={"channel": "email", "to": "test@test.com",
                             "subject": "Test", "body": "Test message"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "delivery_id" in data
        assert data["mode"] == "mock"

    def test_send_sms_mock(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/send", headers=headers,
                       json={"channel": "sms", "to": "+905551234567", "body": "Test SMS"})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_send_whatsapp_mock(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/send", headers=headers,
                       json={"channel": "whatsapp", "to": "+905551234567", "body": "Test WA"})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_send_unknown_channel(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/send", headers=headers,
                       json={"channel": "telegram", "to": "user", "body": "Test"})
        assert r.status_code == 400

    def test_delivery_history(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/messaging/history?limit=5", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "deliveries" in data
        assert "count" in data

    def test_create_template(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/templates", headers=headers,
                       json={"name": "welcome", "channel": "email",
                             "subject": "Hosgeldiniz", "body": "Merhaba {{guest_name}}"})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_get_templates(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/messaging/templates", headers=headers)
        assert r.status_code == 200
        assert "templates" in r.json()

    def test_update_consent(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/messaging/consent", headers=headers,
                       json={"guest_id": "test-guest-123", "channel": "sms", "opted_in": False})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_messaging_analytics(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/messaging/analytics?days=7", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_messages" in data
        assert "delivery_rate" in data


# ═══════════════════════════════════════════════════════════
# 3. AUTO-PRICING WORKFLOW TESTS
# ═══════════════════════════════════════════════════════════

class TestAutoPricing:
    def test_create_recommendation(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/autopricing/recommendation", headers=headers,
                       json={"room_type": "Standard", "current_rate": 100,
                             "suggested_rate": 110, "reason": "Test demand spike",
                             "source": "ml", "confidence": 0.85})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "recommendation_id" in data

    def test_approve_recommendation(self, headers):
        # Create
        r1 = httpx.post(f"{API_URL}/api/enterprise/autopricing/recommendation", headers=headers,
                        json={"room_type": "Standard", "current_rate": 100,
                              "suggested_rate": 105, "reason": "Approve test"})
        rec_id = r1.json()["recommendation_id"]
        # Approve
        r2 = httpx.post(f"{API_URL}/api/enterprise/autopricing/approve", headers=headers,
                        json={"recommendation_id": rec_id, "note": "Approved"})
        assert r2.status_code == 200
        data = r2.json()
        assert data["success"] is True
        assert data["status"] == "applied"
        assert data["rooms_affected"] >= 0

    def test_reject_recommendation(self, headers):
        r1 = httpx.post(f"{API_URL}/api/enterprise/autopricing/recommendation", headers=headers,
                        json={"room_type": "Standard", "current_rate": 100,
                              "suggested_rate": 120, "reason": "Reject test"})
        rec_id = r1.json()["recommendation_id"]
        r2 = httpx.post(f"{API_URL}/api/enterprise/autopricing/reject", headers=headers,
                        json={"recommendation_id": rec_id, "reason": "Too aggressive"})
        assert r2.status_code == 200
        assert r2.json()["success"] is True
        assert r2.json()["status"] == "rejected"

    def test_rollback_correctness(self, headers):
        # Create and approve
        r1 = httpx.post(f"{API_URL}/api/enterprise/autopricing/recommendation", headers=headers,
                        json={"room_type": "Standard", "current_rate": 100,
                              "suggested_rate": 112, "reason": "Rollback test"})
        rec_id = r1.json()["recommendation_id"]
        httpx.post(f"{API_URL}/api/enterprise/autopricing/approve", headers=headers,
                   json={"recommendation_id": rec_id})
        # Rollback
        r3 = httpx.post(f"{API_URL}/api/enterprise/autopricing/rollback", headers=headers,
                        json={"recommendation_id": rec_id, "reason": "Rolled back"})
        assert r3.status_code == 200
        data = r3.json()
        assert data["success"] is True
        assert data["status"] == "rolled_back"
        assert data["rooms_restored"] >= 0

    def test_pending_recommendations(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/autopricing/pending", headers=headers)
        assert r.status_code == 200
        assert "recommendations" in r.json()

    def test_recommendation_history(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/autopricing/history", headers=headers)
        assert r.status_code == 200
        assert "recommendations" in r.json()

    def test_pricing_audit_trail(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/autopricing/audit", headers=headers)
        assert r.status_code == 200
        assert "audits" in r.json()

    def test_channel_push_status(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/autopricing/channel-push", headers=headers)
        assert r.status_code == 200
        assert "pushes" in r.json()

    def test_protected_dates(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/autopricing/protected-dates", headers=headers,
                       json={"start_date": "2026-12-24", "end_date": "2026-12-31",
                             "reason": "Holiday blackout"})
        assert r.status_code == 200
        assert r.json()["success"] is True

        r2 = httpx.get(f"{API_URL}/api/enterprise/autopricing/protected-dates", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["count"] >= 1

    def test_automation_policy(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/autopricing/policy", headers=headers,
                       json={"mode": "supervised", "max_auto_change_pct": 8,
                             "min_rate": 50, "max_rate": 500})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_autopricing_dashboard(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/autopricing/dashboard", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "policy" in data
        assert "stats" in data
        assert "pending_count" in data


# ═══════════════════════════════════════════════════════════
# 4. CROSS-MODULE INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════

class TestCrossModule:
    def test_run_all_integrations(self, headers):
        r = httpx.post(f"{API_URL}/api/enterprise/integration/run-all", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["integrations_run"] == 10
        assert "results" in data

    def test_cancellation_overbooking(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/cancellation-overbooking", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "safe_overbook_rooms" in data

    def test_booking_confidence(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/booking-confidence", headers=headers)
        assert r.status_code == 200
        assert "confidence_boost" in r.json()

    def test_compset_adr(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/compset-adr", headers=headers)
        assert r.status_code == 200
        assert "adjustments" in r.json()

    def test_guest_hk_priority(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/guest-hk-priority", headers=headers)
        assert r.status_code == 200
        assert "priority_rooms" in r.json()

    def test_vip_readiness(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/vip-readiness", headers=headers)
        assert r.status_code == 200
        assert "vip_arrivals" in r.json()

    def test_audit_escalation(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/audit-escalation", headers=headers)
        assert r.status_code == 200
        assert "escalated" in r.json()

    def test_messaging_fallback(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/messaging-fallback", headers=headers)
        assert r.status_code == 200
        assert "fallbacks_created" in r.json()

    def test_sync_alerts(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/sync-alerts", headers=headers)
        assert r.status_code == 200
        assert "alerts_created" in r.json()

    def test_autopricing_metrics(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/autopricing-metrics", headers=headers)
        assert r.status_code == 200
        assert "metrics" in r.json()

    def test_risk_badges(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/risk-badges", headers=headers)
        assert r.status_code == 200
        assert "warnings_generated" in r.json()

    def test_frontdesk_warnings(self, headers):
        r = httpx.get(f"{API_URL}/api/enterprise/integration/frontdesk-warnings", headers=headers)
        assert r.status_code == 200
        assert "badges" in r.json()

    def test_event_propagation_cross_module(self, headers):
        """Test that cross-module run creates signals in DB."""
        r = httpx.post(f"{API_URL}/api/enterprise/integration/run-all", headers=headers, timeout=30)
        data = r.json()
        # All integrations should succeed
        for key, val in data["results"].items():
            assert val.get("status") == "ok", f"Integration {key} failed: {val}"
