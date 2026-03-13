"""
Production Go-Live NEW Features API Tests
Tests new endpoints added to production-golive router:
1. Provider Test Connection Framework (test-all, individual test, test-audit)
2. Config Activation Workflow (validate, boot-check, category)
3. Pre-Launch Validation Suite (run, history, latest)
4. Live Ops Alerts (summary, definitions, history, delivery-log)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

# Test user credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for all tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, f"No access_token in response: {data}"
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# =============================================================================
# MODULE 1: PROVIDER TEST CONNECTION FRAMEWORK
# =============================================================================

class TestProviderTestConnection:
    """Tests for Provider Test Connection Framework with live credential validation."""
    
    def test_providers_status_with_test_results(self, auth_headers):
        """GET /api/production-golive/providers/status - Provider status with test results"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/providers/status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have provider info and test_results
        assert "providers" in data or "active_providers" in data, "Missing provider info"
        # test_results may be added after tests are run
        print(f"Provider status: {data}")
    
    @pytest.mark.parametrize("provider", [
        "twilio_sms",
        "sendgrid_email", 
        "whatsapp",
        "redis",
        "sentry",
        "otel"
    ])
    def test_individual_provider_test(self, auth_headers, provider):
        """POST /api/production-golive/providers/{provider}/test - Test individual provider"""
        response = requests.post(
            f"{BASE_URL}/api/production-golive/providers/{provider}/test",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed for {provider}: {response.text}"
        data = response.json()
        
        # Validate test result structure
        assert "provider" in data, f"Missing 'provider' for {provider}"
        assert data["provider"] == provider, f"Provider mismatch: expected {provider}, got {data['provider']}"
        assert "status" in data, f"Missing 'status' for {provider}"
        # Dev mode expected statuses: not_configured, success, degraded, failed
        assert data["status"] in ["not_configured", "success", "degraded", "failed", "unknown_provider"], \
            f"Unexpected status for {provider}: {data['status']}"
        assert "latency_ms" in data, f"Missing 'latency_ms' for {provider}"
        assert "mode" in data, f"Missing 'mode' for {provider}"
        assert "validated_at" in data, f"Missing 'validated_at' for {provider}"
        assert "network_reachable" in data, f"Missing 'network_reachable' for {provider}"
        assert "credential_valid" in data, f"Missing 'credential_valid' for {provider}"
        
        print(f"Provider {provider}: status={data['status']}, mode={data['mode']}, latency={data['latency_ms']:.2f}ms")
    
    def test_test_all_providers(self, auth_headers):
        """POST /api/production-golive/providers/test-all - Test all providers at once"""
        response = requests.post(
            f"{BASE_URL}/api/production-golive/providers/test-all",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate structure
        assert "tested_at" in data, "Missing 'tested_at'"
        assert "providers" in data, "Missing 'providers'"
        assert "summary" in data, "Missing 'summary'"
        
        # Validate summary
        summary = data["summary"]
        assert "total" in summary, "Missing 'total' in summary"
        assert "success" in summary, "Missing 'success' in summary"
        assert "degraded" in summary, "Missing 'degraded' in summary"
        assert "failed" in summary, "Missing 'failed' in summary"
        assert "overall" in summary, "Missing 'overall' in summary"
        assert summary["overall"] in ["all_healthy", "degraded", "failed"], \
            f"Unexpected overall: {summary['overall']}"
        
        # Validate each provider result
        expected_providers = ["twilio_sms", "sendgrid_email", "whatsapp", "redis", "sentry", "otel"]
        for provider in expected_providers:
            assert provider in data["providers"], f"Missing provider: {provider}"
            p_data = data["providers"][provider]
            assert "status" in p_data, f"Missing status for {provider}"
        
        print(f"Test all: {summary['success']}/{summary['total']} success, {summary['failed']} failed, overall={summary['overall']}")
    
    def test_provider_test_audit(self, auth_headers):
        """GET /api/production-golive/providers/test-audit - Audit log of test connections"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/providers/test-audit?limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "audit_log" in data, "Missing 'audit_log'"
        audit_log = data["audit_log"]
        assert isinstance(audit_log, list), "audit_log should be a list"
        
        # If tests were run, validate audit entries
        if len(audit_log) > 0:
            entry = audit_log[0]
            assert "provider" in entry, "Missing 'provider' in audit entry"
            assert "action" in entry, "Missing 'action' in audit entry"
            assert "result" in entry, "Missing 'result' in audit entry"
            assert "timestamp" in entry, "Missing 'timestamp' in audit entry"
        
        print(f"Audit log: {len(audit_log)} entries")


# =============================================================================
# MODULE 2: CONFIG ACTIVATION WORKFLOW
# =============================================================================

class TestConfigActivationWorkflow:
    """Tests for Production Config Activation Workflow with blocker/warning classification."""
    
    def test_config_activation_validate(self, auth_headers):
        """GET /api/production-golive/config-activation/validate - Full config validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config-activation/validate",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate structure
        assert "validated_at" in data, "Missing 'validated_at'"
        assert "boot_status" in data, "Missing 'boot_status'"
        assert data["boot_status"] in ["CLEAR", "WARNING", "BLOCKED"], f"Invalid boot_status: {data['boot_status']}"
        assert "total_variables" in data, "Missing 'total_variables'"
        assert "configured_count" in data, "Missing 'configured_count'"
        assert "blocker_count" in data, "Missing 'blocker_count'"
        assert "warning_count" in data, "Missing 'warning_count'"
        assert "format_error_count" in data, "Missing 'format_error_count'"
        
        # Lists validation
        assert "blockers" in data, "Missing 'blockers'"
        assert isinstance(data["blockers"], list), "blockers should be a list"
        assert "warnings" in data, "Missing 'warnings'"
        assert isinstance(data["warnings"], list), "warnings should be a list"
        assert "format_errors" in data, "Missing 'format_errors'"
        assert isinstance(data["format_errors"], list), "format_errors should be a list"
        
        # Categories validation
        assert "categories" in data, "Missing 'categories'"
        categories = data["categories"]
        # Expect: database, redis, auth, security, observability, messaging, backup, queue
        expected_cats = ["database", "messaging"]  # At least these should exist
        for cat in expected_cats:
            assert cat in categories, f"Missing category: {cat}"
            cat_data = categories[cat]
            assert "total" in cat_data, f"Missing 'total' in {cat}"
            assert "configured" in cat_data, f"Missing 'configured' in {cat}"
            assert "variables" in cat_data, f"Missing 'variables' in {cat}"
        
        # Source summary
        assert "source_summary" in data, "Missing 'source_summary'"
        
        print(f"Config activation: boot_status={data['boot_status']}, {data['configured_count']}/{data['total_variables']} configured, {data['blocker_count']} blockers")
    
    def test_config_activation_boot_check(self, auth_headers):
        """GET /api/production-golive/config-activation/boot-check - Boot blocker check"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config-activation/boot-check",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        assert data["status"] in ["CLEAR", "BLOCKED"], f"Invalid status: {data['status']}"
        assert "blockers" in data, "Missing 'blockers'"
        assert isinstance(data["blockers"], list), "blockers should be a list"
        assert "checked_at" in data, "Missing 'checked_at'"
        
        # In dev mode, MONGO_URL is expected to be missing (BLOCKED status expected)
        print(f"Boot check: status={data['status']}, blockers={data['blockers']}")
    
    @pytest.mark.parametrize("category", ["database", "messaging", "observability"])
    def test_config_activation_category(self, auth_headers, category):
        """GET /api/production-golive/config-activation/category/{category} - Category-specific config"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config-activation/category/{category}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed for {category}: {response.text}"
        data = response.json()
        
        assert "category" in data, f"Missing 'category' for {category}"
        assert data["category"] == category, "Category mismatch"
        assert "variables" in data, f"Missing 'variables' for {category}"
        assert isinstance(data["variables"], list), "variables should be a list"
        
        if len(data["variables"]) > 0:
            var = data["variables"][0]
            assert "variable" in var, "Missing 'variable' in variable entry"
            assert "configured" in var, "Missing 'configured' in variable entry"
            assert "source" in var, "Missing 'source' in variable entry"
        
        print(f"Category {category}: {len(data['variables'])} variables")


# =============================================================================
# MODULE 3: PRE-LAUNCH VALIDATION SUITE
# =============================================================================

class TestPreLaunchValidationSuite:
    """Tests for Pre-Launch Validation Suite with 12-step check."""
    
    def test_prelaunch_validation_run(self, auth_headers):
        """POST /api/production-golive/validate/run - Run full pre-launch validation"""
        response = requests.post(
            f"{BASE_URL}/api/production-golive/validate/run",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate top-level structure
        assert "run_id" in data, "Missing 'run_id'"
        assert "started_at" in data, "Missing 'started_at'"
        assert "total_duration_ms" in data, "Missing 'total_duration_ms'"
        assert "recommendation" in data, "Missing 'recommendation'"
        assert data["recommendation"] in ["NOT_READY", "CONDITIONALLY_READY", "GO_LIVE_READY"], \
            f"Invalid recommendation: {data['recommendation']}"
        
        # Metrics
        assert "readiness_score" in data, "Missing 'readiness_score'"
        assert 0 <= data["readiness_score"] <= 100, "readiness_score should be 0-100"
        assert "total_checks" in data, "Missing 'total_checks'"
        assert "passed_count" in data, "Missing 'passed_count'"
        assert "failed_count" in data, "Missing 'failed_count'"
        assert "warning_count" in data, "Missing 'warning_count'"
        assert "blocker_count" in data, "Missing 'blocker_count'"
        
        # Lists
        assert "blockers" in data, "Missing 'blockers'"
        assert "warnings" in data, "Missing 'warnings'"
        assert "recommended_actions" in data, "Missing 'recommended_actions'"
        
        # Validate steps (should be 12)
        assert "steps" in data, "Missing 'steps'"
        steps = data["steps"]
        assert isinstance(steps, list), "steps should be a list"
        assert len(steps) >= 10, f"Expected at least 10 steps, got {len(steps)}"
        
        # Validate each step structure
        expected_step_names = [
            "config_validation", "redis_connectivity", "mongo_connectivity",
            "worker_availability", "provider_credentials", "event_bus_health",
            "websocket_broadcast", "messaging_simulation", "tracing_export",
            "alert_engine", "backup_readiness", "security_checklist"
        ]
        step_names_found = [s["name"] for s in steps]
        for expected in expected_step_names:
            assert expected in step_names_found, f"Missing step: {expected}"
        
        for step in steps:
            assert "name" in step, "Missing 'name' in step"
            assert "category" in step, "Missing 'category' in step"
            assert "status" in step, "Missing 'status' in step"
            assert step["status"] in ["pass", "fail", "warning", "skipped"], f"Invalid status in step: {step['status']}"
            assert "latency_ms" in step, "Missing 'latency_ms' in step"
            assert "blocker" in step, "Missing 'blocker' in step"
            assert "message" in step, "Missing 'message' in step"
        
        # In dev mode, expect NOT_READY
        print(f"Pre-launch: {data['recommendation']} ({data['readiness_score']}%), {data['passed_count']}/{data['total_checks']} passed, {data['blocker_count']} blockers")
    
    def test_prelaunch_validation_history(self, auth_headers):
        """GET /api/production-golive/validate/history - Validation history"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/validate/history?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "history" in data, "Missing 'history'"
        history = data["history"]
        assert isinstance(history, list), "history should be a list"
        
        # If validation was run, should have at least one entry
        if len(history) > 0:
            entry = history[0]
            assert "run_id" in entry, "Missing 'run_id' in history entry"
            assert "recommendation" in entry, "Missing 'recommendation' in history entry"
            assert "readiness_score" in entry, "Missing 'readiness_score' in history entry"
        
        print(f"Validation history: {len(history)} entries")
    
    def test_prelaunch_validation_latest(self, auth_headers):
        """GET /api/production-golive/validate/latest - Latest validation result"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/validate/latest",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # If no validation run yet, expects specific message
        if "status" in data and data["status"] == "no_validation_run":
            assert "message" in data, "Missing 'message'"
            print("No validation run yet")
        else:
            # If validation exists, should have full result
            assert "run_id" in data, "Missing 'run_id'"
            assert "recommendation" in data, "Missing 'recommendation'"
            print(f"Latest: {data.get('recommendation', 'N/A')} ({data.get('readiness_score', 'N/A')}%)")


# =============================================================================
# MODULE 4: LIVE OPS ALERT INTEGRATION
# =============================================================================

class TestLiveOpsAlerts:
    """Tests for Live Ops Alert Integration with webhook delivery."""
    
    def test_alerts_summary(self, auth_headers):
        """GET /api/production-golive/alerts/summary - Alert summary"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/alerts/summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "total_alerts" in data, "Missing 'total_alerts'"
        assert "by_severity" in data, "Missing 'by_severity'"
        assert "by_type" in data, "Missing 'by_type'"
        assert "suppressed" in data, "Missing 'suppressed'"
        assert "webhook_targets_configured" in data, "Missing 'webhook_targets_configured'"
        # last_alert may be None if no alerts fired
        
        print(f"Alerts summary: {data['total_alerts']} total, {data['webhook_targets_configured']} webhooks configured")
    
    def test_alerts_definitions(self, auth_headers):
        """GET /api/production-golive/alerts/definitions - Alert definitions with runbooks"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/alerts/definitions",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "definitions" in data, "Missing 'definitions'"
        definitions = data["definitions"]
        assert isinstance(definitions, dict), "definitions should be a dict"
        
        # Expected alert types
        expected_alert_types = [
            "readiness_blocker", "provider_connection_failure", "redis_disconnected",
            "tracing_export_failure", "backup_readiness_failure", "config_blocker",
            "security_score_low", "prelaunch_validation_failed"
        ]
        for alert_type in expected_alert_types:
            assert alert_type in definitions, f"Missing alert type: {alert_type}"
            defn = definitions[alert_type]
            assert "severity" in defn, f"Missing 'severity' in {alert_type}"
            assert "description" in defn, f"Missing 'description' in {alert_type}"
            assert "runbook" in defn, f"Missing 'runbook' in {alert_type}"
            assert "cooldown_sec" in defn, f"Missing 'cooldown_sec' in {alert_type}"
        
        print(f"Alert definitions: {len(definitions)} alert types defined")
    
    def test_alerts_history(self, auth_headers):
        """GET /api/production-golive/alerts/history - Alert history"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/alerts/history?limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "alerts" in data, "Missing 'alerts'"
        alerts = data["alerts"]
        assert isinstance(alerts, list), "alerts should be a list"
        
        if len(alerts) > 0:
            alert = alerts[0]
            assert "alert_id" in alert, "Missing 'alert_id' in alert"
            assert "alert_type" in alert, "Missing 'alert_type' in alert"
            assert "severity" in alert, "Missing 'severity' in alert"
            assert "fired_at" in alert, "Missing 'fired_at' in alert"
        
        print(f"Alert history: {len(alerts)} alerts")
    
    def test_alerts_delivery_log(self, auth_headers):
        """GET /api/production-golive/alerts/delivery-log - Webhook delivery log"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/alerts/delivery-log?limit=50",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "delivery_log" in data, "Missing 'delivery_log'"
        delivery_log = data["delivery_log"]
        assert isinstance(delivery_log, list), "delivery_log should be a list"
        
        if len(delivery_log) > 0:
            entry = delivery_log[0]
            assert "target" in entry, "Missing 'target' in delivery entry"
            assert "status" in entry, "Missing 'status' in delivery entry"
        
        print(f"Delivery log: {len(delivery_log)} entries")


# =============================================================================
# MODULE 5: SUMMARY ENDPOINT
# =============================================================================

class TestGoLiveSummary:
    """Tests for full go-live summary aggregation."""
    
    def test_golive_summary_all_subsystems(self, auth_headers):
        """GET /api/production-golive/summary - Full summary with all new features"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Original subsystems
        assert "readiness" in data, "Missing 'readiness'"
        assert "configuration" in data, "Missing 'configuration'"
        assert "redis" in data, "Missing 'redis'"
        assert "mongodb" in data, "Missing 'mongodb'"
        assert "workers" in data, "Missing 'workers'"
        assert "providers" in data, "Missing 'providers'"
        assert "backup" in data, "Missing 'backup'"
        assert "observability" in data, "Missing 'observability'"
        assert "security" in data, "Missing 'security'"
        
        # NEW subsystems added
        assert "provider_tests" in data, "Missing 'provider_tests' (new feature)"
        assert "config_activation" in data, "Missing 'config_activation' (new feature)"
        assert "prelaunch_latest" in data, "Missing 'prelaunch_latest' (new feature)"
        assert "alerts_summary" in data, "Missing 'alerts_summary' (new feature)"
        
        # Validate config_activation structure
        config_act = data["config_activation"]
        assert "boot_status" in config_act, "Missing 'boot_status' in config_activation"
        
        # Validate alerts_summary structure
        alerts_sum = data["alerts_summary"]
        assert "total_alerts" in alerts_sum, "Missing 'total_alerts' in alerts_summary"
        
        print("Summary includes all 13 subsystems: readiness, configuration, redis, mongodb, workers, providers, backup, observability, security + provider_tests, config_activation, prelaunch_latest, alerts_summary")


# =============================================================================
# AUTH REQUIRED TESTS FOR NEW ENDPOINTS
# =============================================================================

class TestAuthRequiredNewEndpoints:
    """Tests to verify auth is required for all new endpoints."""
    
    @pytest.mark.parametrize("endpoint,method", [
        ("/api/production-golive/providers/twilio_sms/test", "POST"),
        ("/api/production-golive/providers/sendgrid_email/test", "POST"),
        ("/api/production-golive/providers/whatsapp/test", "POST"),
        ("/api/production-golive/providers/redis/test", "POST"),
        ("/api/production-golive/providers/sentry/test", "POST"),
        ("/api/production-golive/providers/otel/test", "POST"),
        ("/api/production-golive/providers/test-all", "POST"),
        ("/api/production-golive/providers/test-audit", "GET"),
        ("/api/production-golive/config-activation/validate", "GET"),
        ("/api/production-golive/config-activation/boot-check", "GET"),
        ("/api/production-golive/config-activation/category/database", "GET"),
        ("/api/production-golive/validate/run", "POST"),
        ("/api/production-golive/validate/history", "GET"),
        ("/api/production-golive/validate/latest", "GET"),
        ("/api/production-golive/alerts/summary", "GET"),
        ("/api/production-golive/alerts/definitions", "GET"),
        ("/api/production-golive/alerts/history", "GET"),
        ("/api/production-golive/alerts/delivery-log", "GET"),
    ])
    def test_endpoints_require_auth(self, endpoint, method):
        """New production-golive endpoints require authentication."""
        if method == "GET":
            response = requests.get(f"{BASE_URL}{endpoint}")
        else:
            response = requests.post(f"{BASE_URL}{endpoint}")
        
        assert response.status_code in [401, 403], \
            f"{method} {endpoint} should require auth, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
