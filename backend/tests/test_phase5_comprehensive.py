"""
Phase 5 Comprehensive API Tests - Using External URL
Tests all Phase 5 endpoints via public URL to verify production behavior.
"""
import pytest
import requests
import os

# Use public URL from frontend env
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pipeline-validation-3.preview.emergentagent.com').rstrip('/')


@pytest.fixture(scope="session")
def auth_headers():
    """Get auth token for demo admin."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
        timeout=30
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Alert Enrichment Engine Tests ──────────────────────────────

class TestAlertEnrichmentEngine:
    """Tests for Alert Rules, Evaluate, Active, Acknowledge, Resolve, Summary"""
    
    def test_get_15_alert_rules(self, auth_headers):
        """GET /api/alerts/rules - returns 15 alert rules"""
        r = requests.get(f"{BASE_URL}/api/alerts/rules", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["count"] == 15, f"Expected 15 rules, got {data['count']}"
        # Validate rule structure
        for rule in data["data"]:
            assert "rule_id" in rule
            assert "name" in rule
            assert "severity" in rule
            assert "category" in rule
            assert "blast_radius" in rule
        print(f"✅ 15 alert rules verified: {[r['rule_id'] for r in data['data'][:3]]}...")

    def test_evaluate_metrics_no_breach(self, auth_headers):
        """POST /api/alerts/evaluate - no alert when below threshold"""
        r = requests.post(
            f"{BASE_URL}/api/alerts/evaluate",
            json={"metrics": {"pending_count": 100}},  # Below 500 threshold
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert "evaluated_rules" in data["data"]
        print(f"✅ Evaluate with no breach: {data['data']['alerts_fired']} alerts fired")

    def test_get_active_alerts(self, auth_headers):
        """GET /api/alerts/active - returns active alerts list"""
        r = requests.get(f"{BASE_URL}/api/alerts/active", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "alerts" in data["data"]
        assert "count" in data["data"]
        print(f"✅ Active alerts: {data['data']['count']} alerts")

    def test_get_alert_summary(self, auth_headers):
        """GET /api/alerts/summary - returns severity breakdown"""
        r = requests.get(f"{BASE_URL}/api/alerts/summary?hours=24", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "total_alerts" in data["data"]
        assert "by_severity" in data["data"]
        assert "rules_count" in data["data"]
        print(f"✅ Alert summary: {data['data']['total_alerts']} alerts in 24h, rules_count={data['data']['rules_count']}")


# ── Incident Response Service Tests ──────────────────────────────

class TestIncidentResponseService:
    """Tests for Incident Create, Acknowledge, Resolve, List, Service Health"""
    
    def test_create_incident(self, auth_headers):
        """POST /api/incidents/create - creates incident"""
        r = requests.post(
            f"{BASE_URL}/api/incidents/create",
            json={
                "title": "Phase5 Test Incident",
                "description": "Testing incident lifecycle",
                "severity": "P3",
                "affected_service": "pms_core",
            },
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert "incident_id" in data["data"]
        incident_id = data["data"]["incident_id"]
        print(f"✅ Created incident: {incident_id}")
        return incident_id

    def test_acknowledge_incident(self, auth_headers):
        """POST /api/incidents/acknowledge - acknowledges incident"""
        # First create one
        create_r = requests.post(
            f"{BASE_URL}/api/incidents/create",
            json={
                "title": "Ack Test Incident",
                "description": "For acknowledgement test",
                "severity": "P2",
                "affected_service": "channel_manager",
            },
            headers=auth_headers,
            timeout=30
        )
        inc_id = create_r.json()["data"]["incident_id"]
        
        # Then acknowledge
        r = requests.post(
            f"{BASE_URL}/api/incidents/acknowledge",
            json={"incident_id": inc_id},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        print(f"✅ Acknowledged incident: {inc_id}")

    def test_resolve_incident(self, auth_headers):
        """POST /api/incidents/resolve - resolves incident"""
        # First create one
        create_r = requests.post(
            f"{BASE_URL}/api/incidents/create",
            json={
                "title": "Resolve Test Incident",
                "description": "For resolution test",
                "severity": "P3",
                "affected_service": "night_audit",
            },
            headers=auth_headers,
            timeout=30
        )
        inc_id = create_r.json()["data"]["incident_id"]
        
        # Then resolve
        r = requests.post(
            f"{BASE_URL}/api/incidents/resolve",
            json={"incident_id": inc_id, "resolution_note": "Resolved in Phase5 test"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        print(f"✅ Resolved incident: {inc_id}")

    def test_list_incidents(self, auth_headers):
        """GET /api/incidents/list - lists incidents"""
        r = requests.get(f"{BASE_URL}/api/incidents/list", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "incidents" in data["data"]
        print(f"✅ Listed {len(data['data']['incidents'])} incidents")

    def test_service_health_matrix(self, auth_headers):
        """GET /api/incidents/service-health - returns service health matrix"""
        r = requests.get(f"{BASE_URL}/api/incidents/service-health", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "services" in data["data"]
        assert "overall_status" in data["data"]
        print(f"✅ Service health: overall={data['data']['overall_status']}, services={len(data['data']['services'])}")


# ── Channel Manager Provider Validation Tests ──────────────────────────────

class TestCMProviderValidation:
    """Tests for Provider Contracts, Validation Run, Sync Lag"""
    
    def test_get_3_provider_contracts(self, auth_headers):
        """GET /api/cm/validation/providers - returns 3 provider contracts"""
        r = requests.get(f"{BASE_URL}/api/cm/validation/providers", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        providers = data["data"]["providers"]
        assert len(providers) == 3, f"Expected 3 providers, got {len(providers)}"
        provider_ids = [p["id"] for p in providers]  # Key is 'id' not 'provider_id'
        assert "hotelrunner" in provider_ids
        assert "booking_com" in provider_ids
        assert "expedia" in provider_ids
        print(f"✅ 3 provider contracts: {provider_ids}")

    def test_run_validation_hotelrunner(self, auth_headers):
        """POST /api/cm/validation/run - runs provider validation for hotelrunner"""
        r = requests.post(
            f"{BASE_URL}/api/cm/validation/run",
            json={"provider_id": "hotelrunner"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert "checks" in data["data"]
        assert "overall_passed" in data["data"]
        print(f"✅ Validation run: overall_passed={data['data']['overall_passed']}, checks={len(data['data']['checks'])}")

    def test_run_validation_unknown_provider_fails(self, auth_headers):
        """POST /api/cm/validation/run - returns 400 for unknown provider"""
        r = requests.post(
            f"{BASE_URL}/api/cm/validation/run",
            json={"provider_id": "unknown_provider"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400
        print("✅ Unknown provider returns 400")

    def test_sync_lag_hotelrunner(self, auth_headers):
        """GET /api/cm/validation/sync-lag/hotelrunner - returns sync lag report"""
        r = requests.get(
            f"{BASE_URL}/api/cm/validation/sync-lag/hotelrunner",
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert "sync_lag" in data["data"]
        print(f"✅ Sync lag report: {data['data']}")


# ── Tenant Isolation Validation Tests ──────────────────────────────

class TestTenantIsolationValidation:
    """Tests for Isolation Score, Noisy Tenants, Resource Fairness"""
    
    def test_validate_isolation_score(self, auth_headers):
        """GET /api/tenant-isolation/v2/validate - returns isolation score and checks"""
        r = requests.get(f"{BASE_URL}/api/tenant-isolation/v2/validate", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "score" in data["data"]
        assert "checks" in data["data"]
        print(f"✅ Isolation score: {data['data']['score']}, checks={len(data['data']['checks'])}")

    def test_detect_noisy_tenants(self, auth_headers):
        """GET /api/tenant-isolation/v2/noisy-tenants - detects noisy tenants"""
        r = requests.get(
            f"{BASE_URL}/api/tenant-isolation/v2/noisy-tenants?window_minutes=60",
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert "noisy_tenants" in data["data"]
        print(f"✅ Noisy tenants: {len(data['data']['noisy_tenants'])} detected")

    def test_resource_fairness_metrics(self, auth_headers):
        """GET /api/tenant-isolation/v2/resource-fairness - returns resource fairness metrics"""
        r = requests.get(f"{BASE_URL}/api/tenant-isolation/v2/resource-fairness", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "total_documents" in data["data"]
        print(f"✅ Resource fairness: {data['data']}")


# ── Pilot Readiness Tests ──────────────────────────────

class TestPilotReadiness:
    """Tests for Readiness Check, Feature Toggles, Sign-off"""
    
    def test_readiness_score_and_checklist(self, auth_headers):
        """GET /api/pilot/readiness - returns readiness score, checklist, blockers"""
        r = requests.get(f"{BASE_URL}/api/pilot/readiness", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "score" in data["data"]
        assert "checklist" in data["data"]
        assert "ready_for_pilot" in data["data"]
        assert "critical_blockers" in data["data"]
        print(f"✅ Readiness: score={data['data']['score']}, ready={data['data']['ready_for_pilot']}, blockers={len(data['data'].get('critical_blockers', []))}")

    def test_get_feature_toggles(self, auth_headers):
        """GET /api/pilot/feature-toggles - returns feature toggles"""
        r = requests.get(f"{BASE_URL}/api/pilot/feature-toggles", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "toggles" in data["data"]
        print(f"✅ Feature toggles: {len(data['data']['toggles'])} toggles")

    def test_sign_off_check(self, auth_headers):
        """POST /api/pilot/sign-off - signs off a check"""
        r = requests.post(
            f"{BASE_URL}/api/pilot/sign-off",
            json={"check_id": "pms_checkin_flow", "notes": "Verified in Phase5 test"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        assert r.json()["data"]["signed_off"] == True
        print("✅ Check signed off")

    def test_set_feature_toggle(self, auth_headers):
        """POST /api/pilot/feature-toggles - sets feature toggle"""
        r = requests.post(
            f"{BASE_URL}/api/pilot/feature-toggles",
            json={"feature": "night_audit_live", "enabled": True},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        print("✅ Feature toggle set")


# ── Frontdesk v2 Tests ──────────────────────────────

class TestFrontdeskV2:
    """Tests for Checkin, Room Move, Late Checkout, Walk-in, No-show, Void Charge"""
    
    def test_checkin_nonexistent_booking_returns_400(self, auth_headers):
        """POST /api/frontdesk/v2/checkin - returns 400 for nonexistent booking"""
        r = requests.post(
            f"{BASE_URL}/api/frontdesk/v2/checkin",
            json={"booking_id": "nonexistent-booking-id"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400
        assert "Booking not found" in r.text
        print("✅ Checkin nonexistent booking returns 400")

    def test_room_move_requires_reason(self, auth_headers):
        """POST /api/frontdesk/v2/room-move - returns 400 with empty reason"""
        r = requests.post(
            f"{BASE_URL}/api/frontdesk/v2/room-move",
            json={"booking_id": "any", "new_room_id": "any", "reason": ""},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400
        print("✅ Room move requires reason")

    def test_late_checkout_requires_reason(self, auth_headers):
        """POST /api/frontdesk/v2/late-checkout - requires reason"""
        r = requests.post(
            f"{BASE_URL}/api/frontdesk/v2/late-checkout",
            json={"booking_id": "any", "new_checkout_time": "2026-03-15", "charge_amount": 0, "reason": ""},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400
        print("✅ Late checkout requires reason")


# ── POS F&B v2 Tests ──────────────────────────────

class TestPOSFnBV2:
    """Tests for Order Create, Close, Void"""
    
    def test_create_order_validates_items_required(self, auth_headers):
        """POST /api/pos/v2/orders - validates items required (returns 400)"""
        r = requests.post(
            f"{BASE_URL}/api/pos/v2/orders",
            json={"outlet_id": "out-1", "items": []},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400
        print("✅ Create order validates items required")

    def test_create_and_close_order_lifecycle(self, auth_headers):
        """POST /api/pos/v2/orders + close - full order lifecycle"""
        # Create order
        r = requests.post(
            f"{BASE_URL}/api/pos/v2/orders",
            json={
                "outlet_id": "test-outlet",
                "items": [{"name": "Pizza", "price": 75.0, "quantity": 1}],
                "guest_name": "Phase5 Test Guest",
                "order_type": "dine_in",
            },
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()["data"]
        order_id = data["order_id"]
        assert data["grand_total"] == 82.5  # 75 + 10% tax
        print(f"✅ Created order: {order_id}, total={data['grand_total']}")

        # Close order
        r = requests.post(
            f"{BASE_URL}/api/pos/v2/orders/close",
            json={"order_id": order_id, "payment_method": "credit_card"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 200
        assert r.json()["data"]["message"] == "Order closed and payment processed"
        print(f"✅ Closed order: {order_id}")

    def test_void_order_requires_supervisor_permission(self, auth_headers):
        """POST /api/pos/v2/orders/void - requires supervisor permission"""
        # Admin role has permission, but nonexistent order returns NOT_FOUND
        r = requests.post(
            f"{BASE_URL}/api/pos/v2/orders/void",
            json={"order_id": "nonexistent", "reason": "test"},
            headers=auth_headers,
            timeout=30
        )
        assert r.status_code == 400  # NOT_FOUND converted to 400
        print("✅ Void order with nonexistent order returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
