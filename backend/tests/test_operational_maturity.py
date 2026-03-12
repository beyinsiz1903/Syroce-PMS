"""
Comprehensive test suite for Phase 1-5 operational maturity modules:
  1. Historical Metrics Storage
  2. Alerting System
  3. Enhanced Sandbox Validation
  4. Connector Reliability Monitoring
  5. Multi-Property Integration Dashboard
"""
import pytest
import httpx
import os
import json
from datetime import datetime

BASE = os.environ.get("TEST_BASE_URL", "https://hotel-hardening.preview.emergentagent.com")
API = f"{BASE}/api/channel-manager/v2"
AUTH = f"{BASE}/api/auth/login"
CREDS = {"email": "demo@hotel.com", "password": "demo123"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(AUTH, json=CREDS, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: Historical Metrics Storage
# ═══════════════════════════════════════════════════════════════════════

class TestHistoricalMetrics:
    def test_create_snapshot(self, headers):
        r = httpx.post(f"{API}/metrics/snapshot", headers=headers, json={}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "snapshots_created" in data
        assert data["snapshots_created"] >= 1

    def test_get_history(self, headers):
        r = httpx.get(f"{API}/metrics/history?period=7d", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "snapshots" in data
        assert "count" in data
        assert data["period"] == "7d"

    def test_get_trends(self, headers):
        r = httpx.get(f"{API}/metrics/trends?period=7d", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "trends" in data
        assert "metric_keys" in data
        assert "data_points" in data

    def test_get_connector_history(self, headers):
        # Get a connector ID first
        conns = httpx.get(f"{API}/connectors", headers=headers, timeout=15).json()
        if conns.get("connectors"):
            cid = conns["connectors"][0]["id"]
            r = httpx.get(f"{API}/metrics/history/{cid}?period=7d", headers=headers, timeout=15)
            assert r.status_code == 200
            assert "snapshots" in r.json()

    def test_retention_cleanup(self, headers):
        r = httpx.post(f"{API}/metrics/retention-cleanup", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "deleted" in data

    def test_daily_aggregation(self, headers):
        r = httpx.post(f"{API}/metrics/daily-aggregation", headers=headers, json={"date": "2026-03-10"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "aggregated" in data


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: Alerting System
# ═══════════════════════════════════════════════════════════════════════

class TestAlertingSystem:
    def test_get_alerts(self, headers):
        r = httpx.get(f"{API}/alerts", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
        assert "summary" in data
        assert "count" in data

    def test_get_alert_summary(self, headers):
        r = httpx.get(f"{API}/alerts/summary", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "active" in data
        assert "resolved" in data

    def test_evaluate_alerts(self, headers):
        r = httpx.post(f"{API}/alerts/evaluate", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "evaluated_rules" in data
        assert "connectors_checked" in data

    def test_get_alert_rules(self, headers):
        r = httpx.get(f"{API}/alerts/rules", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
        assert data["count"] >= 1

    def test_create_alert_rule(self, headers):
        rule = {
            "trigger": "health_score_drop",
            "threshold": 30,
            "severity": "critical",
            "description": "Test rule - health below 30",
            "enabled": True,
        }
        r = httpx.post(f"{API}/alerts/rules", headers=headers, json=rule, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "rule" in data
        assert data["rule"]["trigger"] == "health_score_drop"

    def test_update_alert_rule(self, headers):
        rules = httpx.get(f"{API}/alerts/rules", headers=headers, timeout=15).json()
        if rules.get("rules"):
            rule_id = rules["rules"][-1]["id"]
            update = {"trigger": "health_score_drop", "threshold": 25, "severity": "warning", "description": "Updated", "enabled": False}
            r = httpx.put(f"{API}/alerts/rules/{rule_id}", headers=headers, json=update, timeout=15)
            assert r.status_code == 200

    def test_alert_actions(self, headers):
        alerts = httpx.get(f"{API}/alerts?status=active", headers=headers, timeout=15).json()
        if alerts.get("alerts"):
            alert_id = alerts["alerts"][0]["id"]

            # Acknowledge
            r = httpx.post(f"{API}/alerts/{alert_id}/acknowledge", headers=headers, timeout=15)
            assert r.status_code == 200
            assert r.json()["action"] == "acknowledged"

            # Resolve
            r = httpx.post(f"{API}/alerts/{alert_id}/resolve", headers=headers, json={"reason": "Test resolve"}, timeout=15)
            assert r.status_code == 200
            assert r.json()["action"] == "resolved"

    def test_alert_mute(self, headers):
        # Re-evaluate to create new alerts
        httpx.post(f"{API}/alerts/evaluate", headers=headers, timeout=30)
        alerts = httpx.get(f"{API}/alerts?status=active", headers=headers, timeout=15).json()
        if alerts.get("alerts"):
            alert_id = alerts["alerts"][0]["id"]
            r = httpx.post(f"{API}/alerts/{alert_id}/mute", headers=headers, json={"hours": 4}, timeout=15)
            assert r.status_code == 200
            assert r.json()["action"] == "muted"

    def test_alert_dismiss(self, headers):
        alerts = httpx.get(f"{API}/alerts?status=active", headers=headers, timeout=15).json()
        if alerts.get("alerts"):
            alert_id = alerts["alerts"][0]["id"]
            r = httpx.post(f"{API}/alerts/{alert_id}/dismiss", headers=headers, json={"reason": "Test dismiss"}, timeout=15)
            assert r.status_code == 200

    def test_filter_alerts_by_severity(self, headers):
        r = httpx.get(f"{API}/alerts?severity=critical", headers=headers, timeout=15)
        assert r.status_code == 200
        for alert in r.json().get("alerts", []):
            assert alert["severity"] == "critical"


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: Enhanced Sandbox Validation
# ═══════════════════════════════════════════════════════════════════════

class TestEnhancedSandboxValidation:
    def test_full_validation(self, headers):
        conns = httpx.get(f"{API}/connectors", headers=headers, timeout=15).json()
        if conns.get("connectors"):
            cid = conns["connectors"][0]["id"]
            r = httpx.post(f"{API}/sandbox/validate/{cid}/full", headers=headers, timeout=30)
            assert r.status_code == 200
            data = r.json()
            assert "checks" in data
            assert "passed_checks" in data
            assert "failed_checks" in data
            assert "total_checks" in data
            assert "production_recommendation" in data
            assert "mapping_readiness" in data
            assert "connector_health_impact" in data
            assert "required_next_actions" in data

    def test_full_validation_nonexistent(self, headers):
        r = httpx.post(f"{API}/sandbox/validate/nonexistent/full", headers=headers, timeout=15)
        assert r.status_code in [404, 200]  # May return error or empty report


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: Connector Reliability Monitoring
# ═══════════════════════════════════════════════════════════════════════

class TestReliabilityMonitoring:
    def test_get_all_reliability(self, headers):
        r = httpx.get(f"{API}/reliability", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "connectors" in data
        assert "count" in data
        assert "average_uptime" in data
        assert "classifications" in data

    def test_get_connector_reliability(self, headers):
        conns = httpx.get(f"{API}/connectors", headers=headers, timeout=15).json()
        if conns.get("connectors"):
            cid = conns["connectors"][0]["id"]
            r = httpx.get(f"{API}/reliability/{cid}", headers=headers, timeout=15)
            assert r.status_code == 200
            data = r.json()
            assert "uptime_percentage" in data
            assert "mtbf_hours" in data
            assert "mttr_hours" in data
            assert "sync_success_rate" in data
            assert "ack_success_rate" in data
            assert "retry_rate" in data
            assert "classification" in data
            assert data["classification"] in ["stable", "healthy", "degraded", "unstable"]

    def test_reliability_nonexistent(self, headers):
        r = httpx.get(f"{API}/reliability/nonexistent-id", headers=headers, timeout=15)
        assert r.status_code == 404

    def test_reliability_has_failure_patterns(self, headers):
        r = httpx.get(f"{API}/reliability", headers=headers, timeout=30)
        data = r.json()
        for c in data.get("connectors", []):
            assert "failure_patterns" in c
            assert isinstance(c["failure_patterns"], list)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: Multi-Property Integration Dashboard
# ═══════════════════════════════════════════════════════════════════════

class TestMultiPropertyDashboard:
    def test_get_dashboard(self, headers):
        r = httpx.get(f"{API}/multi-property/dashboard", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "total_properties" in data
        assert "total_connectors" in data
        assert "average_health_score" in data
        assert "healthy_properties" in data
        assert "degraded_properties" in data
        assert "critical_properties" in data
        assert "properties" in data
        assert "top_failing" in data
        assert "provider_distribution" in data
        assert "tenant_health_status" in data

    def test_get_comparison(self, headers):
        r = httpx.get(f"{API}/multi-property/comparison", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "comparisons" in data
        assert "count" in data

    def test_get_issues(self, headers):
        r = httpx.get(f"{API}/multi-property/issues", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "issues" in data
        assert "total" in data
        assert "by_severity" in data

    def test_get_health(self, headers):
        r = httpx.get(f"{API}/multi-property/health", headers=headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "properties" in data
        assert "count" in data

    def test_dashboard_properties_have_required_fields(self, headers):
        r = httpx.get(f"{API}/multi-property/dashboard", headers=headers, timeout=30)
        data = r.json()
        for p in data.get("properties", []):
            assert "property_id" in p
            assert "health_score" in p
            assert "health_status" in p
            assert "sync_success_rate" in p
            assert "connector_count" in p
