"""
Test Suite: SEC-001/SEC-002 Rollout APIs, Sandbox Dashboard, Admin Guard, KPI Correlation
==========================================================================================
Tests for the new sprint features:
- SEC-001: Secrets Management rollout APIs (rotation plan, rollback, tenant/provider scoping, access audit)
- SEC-002: Crypto Migration rollout APIs (cutover metrics, key versioning, dual-read/write status, migration dry-run)
- Sandbox Dashboard visualization APIs (provider cards, trend chart, regression alerts, correlation)
- /api/ops/* admin guard (role-based access control)
- Alert → Business KPI Correlation (alerts with severity, runbook link, tenant/property/provider context)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://stop-sale-fix.preview.emergentagent.com").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in response"
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ═══════════════════════════════════════════════════════════════════
# Admin Guard Tests - /api/ops/* endpoints require authentication
# ═══════════════════════════════════════════════════════════════════

class TestAdminGuard:
    """Test that /api/ops/* endpoints require authentication."""

    def test_ops_secrets_status_requires_auth(self):
        """SEC-001: GET /api/ops/secrets/status returns 401 without token."""
        response = requests.get(f"{BASE_URL}/api/ops/secrets/status", timeout=30)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_ops_crypto_status_requires_auth(self):
        """SEC-002: GET /api/ops/crypto/status returns 401 without token."""
        response = requests.get(f"{BASE_URL}/api/ops/crypto/status", timeout=30)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_ops_sandbox_dashboard_requires_auth(self):
        """Sandbox: GET /api/ops/sandbox/dashboard returns 401 without token."""
        response = requests.get(f"{BASE_URL}/api/ops/sandbox/dashboard", timeout=30)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_ops_alerts_kpi_correlation_requires_auth(self):
        """KPI: GET /api/ops/alerts/kpi-correlation returns 401 without token."""
        response = requests.get(f"{BASE_URL}/api/ops/alerts/kpi-correlation", timeout=30)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_ops_overview_requires_auth(self):
        """Overview: GET /api/ops/overview returns 401 without token."""
        response = requests.get(f"{BASE_URL}/api/ops/overview", timeout=30)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


# ═══════════════════════════════════════════════════════════════════
# SEC-001: Secrets Management Rollout APIs
# ═══════════════════════════════════════════════════════════════════

class TestSEC001SecretsManagement:
    """SEC-001: Secrets Management rollout APIs."""

    def test_secrets_status_returns_health_config_audit(self, auth_headers):
        """GET /api/ops/secrets/status returns health, config, audit stats."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/status",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify health info
        assert "health" in data, "Missing 'health' field"
        
        # Verify config info
        assert "config" in data, "Missing 'config' field"
        config = data["config"]
        assert "provider" in config, "Missing 'provider' in config"
        assert "environment" in config, "Missing 'environment' in config"
        assert "legacy_fallback" in config, "Missing 'legacy_fallback' in config"
        assert "audit_enabled" in config, "Missing 'audit_enabled' in config"
        
        # Verify audit stats
        assert "audit_24h" in data, "Missing 'audit_24h' field"
        assert "anomalies_24h" in data, "Missing 'anomalies_24h' field"
        assert "timestamp" in data, "Missing 'timestamp' field"

    def test_secrets_rotation_plan_returns_items_with_severity(self, auth_headers):
        """GET /api/ops/secrets/rotation-plan returns rotation items with severity and recommendations."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/rotation-plan",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' field"
        assert "summary" in data, "Missing 'summary' field"
        assert "rotation_policy" in data, "Missing 'rotation_policy' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify summary fields
        summary = data["summary"]
        assert "total_secrets" in summary, "Missing 'total_secrets' in summary"
        assert "urgent_rotations" in summary, "Missing 'urgent_rotations' in summary"
        assert "recommended_rotations" in summary, "Missing 'recommended_rotations' in summary"
        assert "ok" in summary, "Missing 'ok' in summary"
        
        # Verify rotation policy
        policy = data["rotation_policy"]
        assert "max_age_days" in policy, "Missing 'max_age_days' in policy"
        assert "warning_age_days" in policy, "Missing 'warning_age_days' in policy"
        
        # If there are items, verify their structure
        if data["items"]:
            item = data["items"][0]
            assert "provider" in item, "Missing 'provider' in item"
            assert "recommendation" in item, "Missing 'recommendation' in item"
            assert "severity" in item, "Missing 'severity' in item"
            assert item["severity"] in ["info", "warning", "critical"], f"Invalid severity: {item['severity']}"

    def test_secrets_scoping_returns_tenant_provider_isolation(self, auth_headers):
        """GET /api/ops/secrets/scoping returns tenant/provider isolation view."""
        response = requests.get(
            f"{BASE_URL}/api/ops/secrets/scoping",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "scoping" in data, "Missing 'scoping' field"
        assert "isolation_model" in data, "Missing 'isolation_model' field"
        assert "cross_tenant_access" in data, "Missing 'cross_tenant_access' field"
        assert "policy_enforcement" in data, "Missing 'policy_enforcement' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify isolation model
        assert data["isolation_model"] == "tenant/provider/property", f"Unexpected isolation model: {data['isolation_model']}"
        assert data["cross_tenant_access"] == "DENIED", f"Cross-tenant access should be DENIED"
        assert data["policy_enforcement"] == "active", f"Policy enforcement should be active"


# ═══════════════════════════════════════════════════════════════════
# SEC-002: Crypto Migration Rollout APIs
# ═══════════════════════════════════════════════════════════════════

class TestSEC002CryptoMigration:
    """SEC-002: Crypto Migration rollout APIs."""

    def test_crypto_status_returns_health_dual_read_write(self, auth_headers):
        """GET /api/ops/crypto/status returns crypto health with dual-read/write info and key info."""
        response = requests.get(
            f"{BASE_URL}/api/ops/crypto/status",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify health info
        assert "health" in data, "Missing 'health' field"
        
        # Verify config info
        assert "config" in data, "Missing 'config' field"
        config = data["config"]
        assert "v2_enabled" in config, "Missing 'v2_enabled' in config"
        assert "bypass_allowed" in config, "Missing 'bypass_allowed' in config"
        assert "key_version" in config, "Missing 'key_version' in config"
        assert "has_master_key" in config, "Missing 'has_master_key' in config"
        
        # Verify dual read/write info
        assert "dual_read_write" in data, "Missing 'dual_read_write' field"
        drw = data["dual_read_write"]
        assert "status" in drw, "Missing 'status' in dual_read_write"
        assert "write_format" in drw, "Missing 'write_format' in dual_read_write"
        assert "read_formats" in drw, "Missing 'read_formats' in dual_read_write"
        assert isinstance(drw["read_formats"], list), "read_formats should be a list"
        
        # Verify fallback strategy
        assert "fallback_strategy" in data, "Missing 'fallback_strategy' field"
        assert "timestamp" in data, "Missing 'timestamp' field"

    def test_crypto_cutover_metrics_returns_format_distribution(self, auth_headers):
        """GET /api/ops/crypto/cutover-metrics returns format distribution and migration percentage."""
        response = requests.get(
            f"{BASE_URL}/api/ops/crypto/cutover-metrics",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "collections" in data, "Missing 'collections' field"
        assert "totals" in data, "Missing 'totals' field"
        assert "cutover" in data, "Missing 'cutover' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify totals structure
        totals = data["totals"]
        assert "syr1" in totals, "Missing 'syr1' in totals"
        assert "aes_gcm_legacy" in totals, "Missing 'aes_gcm_legacy' in totals"
        assert "other_legacy" in totals, "Missing 'other_legacy' in totals"
        
        # Verify cutover info
        cutover = data["cutover"]
        assert "total_credential_fields" in cutover, "Missing 'total_credential_fields' in cutover"
        assert "migrated_to_syr1" in cutover, "Missing 'migrated_to_syr1' in cutover"
        assert "migration_percentage" in cutover, "Missing 'migration_percentage' in cutover"
        assert "cutover_ready" in cutover, "Missing 'cutover_ready' in cutover"
        assert "recommended_action" in cutover, "Missing 'recommended_action' in cutover"

    def test_crypto_migrate_check_returns_dry_run_results(self, auth_headers):
        """POST /api/ops/crypto/migrate-check returns dry-run check results."""
        response = requests.post(
            f"{BASE_URL}/api/ops/crypto/migrate-check",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "dry_run" in data, "Missing 'dry_run' field"
        assert data["dry_run"] is True, "dry_run should be True"
        assert "would_migrate" in data, "Missing 'would_migrate' field"
        assert "already_current" in data, "Missing 'already_current' field"
        assert "total_scanned" in data, "Missing 'total_scanned' field"
        assert "action" in data, "Missing 'action' field"
        assert "timestamp" in data, "Missing 'timestamp' field"

    def test_crypto_key_info_returns_versioning_and_plans(self, auth_headers):
        """GET /api/ops/crypto/key-info returns key versioning and rotation/rollback plans."""
        response = requests.get(
            f"{BASE_URL}/api/ops/crypto/key-info",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "current_version" in data, "Missing 'current_version' field"
        assert "has_current_key" in data, "Missing 'has_current_key' field"
        assert "has_previous_key" in data, "Missing 'has_previous_key' field"
        assert "rotation_ready" in data, "Missing 'rotation_ready' field"
        assert "rotation_steps" in data, "Missing 'rotation_steps' field"
        assert "rollback_plan" in data, "Missing 'rollback_plan' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify rotation steps is a list
        assert isinstance(data["rotation_steps"], list), "rotation_steps should be a list"
        assert len(data["rotation_steps"]) > 0, "rotation_steps should not be empty"
        
        # Verify rollback plan structure
        rollback = data["rollback_plan"]
        assert "immediate" in rollback, "Missing 'immediate' in rollback_plan"
        assert "break_glass" in rollback, "Missing 'break_glass' in rollback_plan"


# ═══════════════════════════════════════════════════════════════════
# Sandbox Dashboard Visualization APIs
# ═══════════════════════════════════════════════════════════════════

class TestSandboxDashboard:
    """Sandbox Dashboard visualization APIs."""

    def test_sandbox_dashboard_returns_provider_cards(self, auth_headers):
        """GET /api/ops/sandbox/dashboard returns provider cards with pass/fail data."""
        response = requests.get(
            f"{BASE_URL}/api/ops/sandbox/dashboard",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "has_data" in data, "Missing 'has_data' field"
        assert "provider_cards" in data, "Missing 'provider_cards' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # If there's data, verify provider cards structure
        if data["has_data"]:
            assert "last_run" in data, "Missing 'last_run' field when has_data=True"
            assert len(data["provider_cards"]) > 0, "provider_cards should not be empty when has_data=True"
            
            card = data["provider_cards"][0]
            assert "provider" in card, "Missing 'provider' in card"
            assert "display_name" in card, "Missing 'display_name' in card"
            assert "passed" in card, "Missing 'passed' in card"
            assert "failed" in card, "Missing 'failed' in card"
            assert "total" in card, "Missing 'total' in card"
            assert "pass_rate" in card, "Missing 'pass_rate' in card"
            assert "scenarios" in card, "Missing 'scenarios' in card"

    def test_sandbox_trends_returns_trend_data(self, auth_headers):
        """GET /api/ops/sandbox/trends returns trend data for charting."""
        response = requests.get(
            f"{BASE_URL}/api/ops/sandbox/trends?limit=30",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "overall_trend" in data, "Missing 'overall_trend' field"
        assert "provider_trends" in data, "Missing 'provider_trends' field"
        assert "scenario_trends" in data, "Missing 'scenario_trends' field"
        assert "most_failing_scenarios" in data, "Missing 'most_failing_scenarios' field"
        assert "total_runs" in data, "Missing 'total_runs' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # If there are trends, verify structure
        if data["overall_trend"]:
            trend = data["overall_trend"][0]
            assert "run_id" in trend, "Missing 'run_id' in trend"
            assert "date" in trend, "Missing 'date' in trend"
            assert "pass_rate" in trend, "Missing 'pass_rate' in trend"

    def test_sandbox_regressions_returns_regression_data(self, auth_headers):
        """GET /api/ops/sandbox/regressions returns regression detection data."""
        response = requests.get(
            f"{BASE_URL}/api/ops/sandbox/regressions",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "has_regression" in data, "Missing 'has_regression' field"
        assert "regressions" in data, "Missing 'regressions' field"
        assert "label" in data, "Missing 'label' field"
        assert data["label"] == "sandbox_regression", f"Expected label 'sandbox_regression', got {data['label']}"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # If there are regressions, verify structure
        if data["regressions"]:
            reg = data["regressions"][0]
            assert "provider" in reg, "Missing 'provider' in regression"
            assert "scenario" in reg, "Missing 'scenario' in regression"
            assert "severity" in reg, "Missing 'severity' in regression"
            assert "runbook_link" in reg, "Missing 'runbook_link' in regression"
            assert "alert_type" in reg, "Missing 'alert_type' in regression"

    def test_sandbox_correlation_returns_deploy_drift_correlation(self, auth_headers):
        """GET /api/ops/sandbox/correlation returns deploy/drift correlation."""
        response = requests.get(
            f"{BASE_URL}/api/ops/sandbox/correlation?limit=10",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "correlations" in data, "Missing 'correlations' field"
        assert "drift_alerts_active" in data, "Missing 'drift_alerts_active' field"
        assert "insight" in data, "Missing 'insight' field"
        assert "label" in data, "Missing 'label' field"
        assert data["label"] == "prod_health", f"Expected label 'prod_health', got {data['label']}"
        assert "timestamp" in data, "Missing 'timestamp' field"


# ═══════════════════════════════════════════════════════════════════
# KPI Correlation API
# ═══════════════════════════════════════════════════════════════════

class TestKPICorrelation:
    """Alert → Business KPI Correlation API."""

    def test_alerts_kpi_correlation_returns_business_impact(self, auth_headers):
        """GET /api/ops/alerts/kpi-correlation returns business impact mapping."""
        response = requests.get(
            f"{BASE_URL}/api/ops/alerts/kpi-correlation?hours=24",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "kpi_impact" in data, "Missing 'kpi_impact' field"
        assert "alert_summary" in data, "Missing 'alert_summary' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify KPI impact categories
        kpi_impact = data["kpi_impact"]
        expected_kpis = ["revenue_risk", "rate_parity_risk", "security_risk", "data_protection_risk"]
        for kpi in expected_kpis:
            assert kpi in kpi_impact, f"Missing '{kpi}' in kpi_impact"
            assert "level" in kpi_impact[kpi], f"Missing 'level' in {kpi}"
            assert "alert_count" in kpi_impact[kpi], f"Missing 'alert_count' in {kpi}"
            assert "drivers" in kpi_impact[kpi], f"Missing 'drivers' in {kpi}"
            assert kpi_impact[kpi]["level"] in ["low", "medium", "high", "critical"], f"Invalid level for {kpi}"
        
        # Verify alert summary
        summary = data["alert_summary"]
        assert "total_alerts" in summary, "Missing 'total_alerts' in alert_summary"
        assert "by_severity" in summary, "Missing 'by_severity' in alert_summary"
        assert "by_provider" in summary, "Missing 'by_provider' in alert_summary"
        assert "time_window_hours" in summary, "Missing 'time_window_hours' in alert_summary"


# ═══════════════════════════════════════════════════════════════════
# Authenticated Access Tests
# ═══════════════════════════════════════════════════════════════════

class TestAuthenticatedAccess:
    """Test that authenticated users can access /api/ops/* endpoints."""

    def test_ops_overview_with_auth(self, auth_headers):
        """GET /api/ops/overview works with valid auth token."""
        response = requests.get(
            f"{BASE_URL}/api/ops/overview",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "open_failures" in data, "Missing 'open_failures' field"
        assert "timestamp" in data, "Missing 'timestamp' field"

    def test_ops_failures_with_auth(self, auth_headers):
        """GET /api/ops/failures works with valid auth token."""
        response = requests.get(
            f"{BASE_URL}/api/ops/failures?limit=10",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_ops_alerts_with_auth(self, auth_headers):
        """GET /api/ops/alerts works with valid auth token."""
        response = requests.get(
            f"{BASE_URL}/api/ops/alerts?limit=10",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "alerts" in data, "Missing 'alerts' field"

    def test_ops_runbooks_with_auth(self, auth_headers):
        """GET /api/ops/runbooks works with valid auth token."""
        response = requests.get(
            f"{BASE_URL}/api/ops/runbooks",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "runbooks" in data, "Missing 'runbooks' field"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
