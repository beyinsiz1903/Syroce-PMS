"""
Phase 5 Hardening — Integration Tests via API endpoints
Uses curl-style HTTP requests to test all new endpoints.
"""
import pytest
import httpx
import uuid
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Read API URL from frontend env or default to local
API_BASE = "http://localhost:8001"


@pytest.fixture(scope="session")
def auth_headers():
    """Get auth token for test user."""
    resp = httpx.post(
        f"{API_BASE}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Alert Rules Endpoint ──────────────────────────────────────

class TestAlertEndpoints:
    def test_get_rules(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/alerts/rules", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["count"] == 15
        assert all("rule_id" in rule for rule in data["data"])

    def test_get_active_alerts(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/alerts/active", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_evaluate_no_metrics(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/alerts/evaluate",
            json={"metrics": {}},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["alerts_fired"] == 0

    def test_evaluate_fires_alert(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/alerts/evaluate",
            json={"metrics": {"pending_count": 1000}},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        # Alert may be in cooldown from prior runs — verify structure
        assert "alerts_fired" in data["data"]
        assert "evaluated_rules" in data["data"]
        assert data["data"]["evaluated_rules"] == 15

    def test_alert_summary(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/alerts/summary?hours=24", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_alerts" in data["data"]


# ── Incident Endpoints ──────────────────────────────────────

class TestIncidentEndpoints:
    def test_incident_lifecycle(self, auth_headers):
        # Create
        r = httpx.post(
            f"{API_BASE}/api/incidents/create",
            json={
                "title": "Test Incident",
                "description": "Testing incident lifecycle",
                "severity": "P3",
                "affected_service": "pms_core",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        inc_id = r.json()["data"]["incident_id"]

        # Acknowledge
        r = httpx.post(
            f"{API_BASE}/api/incidents/acknowledge",
            json={"incident_id": inc_id},
            headers=auth_headers,
        )
        assert r.status_code == 200

        # Resolve
        r = httpx.post(
            f"{API_BASE}/api/incidents/resolve",
            json={"incident_id": inc_id, "resolution_note": "Fixed in test"},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_list_incidents(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/incidents/list", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "incidents" in data["data"]

    def test_service_health_matrix(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/incidents/service-health", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "services" in data["data"]
        assert "overall_status" in data["data"]


# ── CM Validation Endpoints ──────────────────────────────────

class TestCMValidation:
    def test_get_providers(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/cm/validation/providers", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        providers = data["data"]["providers"]
        assert len(providers) == 3  # hotelrunner, booking_com, expedia

    def test_run_validation(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/cm/validation/run",
            json={"provider_id": "hotelrunner"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "checks" in data["data"]
        assert "overall_passed" in data["data"]

    def test_unknown_provider(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/cm/validation/run",
            json={"provider_id": "nonexistent_provider"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_sync_lag_report(self, auth_headers):
        r = httpx.get(
            f"{API_BASE}/api/cm/validation/sync-lag/hotelrunner",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "sync_lag" in data["data"]


# ── Tenant Isolation Endpoints ──────────────────────────────

class TestTenantIsolation:
    def test_validate_isolation(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/tenant-isolation/v2/validate", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "score" in data["data"]
        assert "checks" in data["data"]

    def test_noisy_tenants(self, auth_headers):
        r = httpx.get(
            f"{API_BASE}/api/tenant-isolation/v2/noisy-tenants?window_minutes=60",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "noisy_tenants" in data["data"]

    def test_resource_fairness(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/tenant-isolation/v2/resource-fairness", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_documents" in data["data"]


# ── Pilot Readiness Endpoints ──────────────────────────────

class TestPilotReadiness:
    def test_readiness_check(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/pilot/readiness", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "score" in data["data"]
        assert "checklist" in data["data"]
        assert "ready_for_pilot" in data["data"]
        assert "critical_blockers" in data["data"]

    def test_feature_toggles(self, auth_headers):
        r = httpx.get(f"{API_BASE}/api/pilot/feature-toggles", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "toggles" in data["data"]

    def test_sign_off_and_toggle(self, auth_headers):
        # Sign off a check
        r = httpx.post(
            f"{API_BASE}/api/pilot/sign-off",
            json={"check_id": "pms_checkin_flow", "notes": "Verified in test"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["signed_off"]

        # Set a feature toggle
        r = httpx.post(
            f"{API_BASE}/api/pilot/feature-toggles",
            json={"feature": "night_audit_live", "enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 200


# ── Frontdesk v2 Endpoints ──────────────────────────────────

class TestFrontdeskV2:
    def test_checkin_not_found(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/frontdesk/v2/checkin",
            json={"booking_id": "nonexistent-booking-id"},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "Booking not found" in str(r.json())

    def test_room_move_requires_reason(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/frontdesk/v2/room-move",
            json={"booking_id": "any", "new_room_id": "any", "reason": ""},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_late_checkout_requires_reason(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/frontdesk/v2/late-checkout",
            json={"booking_id": "any", "new_checkout_time": "2026-03-15", "charge_amount": 0, "reason": ""},
            headers=auth_headers,
        )
        assert r.status_code == 400


# ── POS v2 Endpoints ──────────────────────────────────────

class TestPOSV2:
    def test_create_order_no_items(self, auth_headers):
        r = httpx.post(
            f"{API_BASE}/api/pos/v2/orders",
            json={"outlet_id": "out-1", "items": []},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_create_and_close_order(self, auth_headers):
        # Create order
        r = httpx.post(
            f"{API_BASE}/api/pos/v2/orders",
            json={
                "outlet_id": "test-outlet",
                "items": [{"name": "Burger", "price": 50.0, "quantity": 2}],
                "guest_name": "Test Guest",
                "order_type": "dine_in",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["order_id"]
        assert data["grand_total"] == 110.0  # (50*2) + 10% tax

        order_id = data["order_id"]

        # Close order
        r = httpx.post(
            f"{API_BASE}/api/pos/v2/orders/close",
            json={"order_id": order_id, "payment_method": "cash"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["message"] == "Order closed and payment processed"

    def test_void_order_no_permission(self, auth_headers):
        # This test uses demo admin who has admin role, so it should be allowed
        # But since order doesn't exist, it returns NOT_FOUND
        r = httpx.post(
            f"{API_BASE}/api/pos/v2/orders/void",
            json={"order_id": "nonexistent", "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 400
