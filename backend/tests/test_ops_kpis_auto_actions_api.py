"""
Test Suite: Ops KPIs, Auto-Actions, and Notification Routing
=============================================================
Tests for iteration_146:
- GET /api/ops/dashboard/ops-kpis - Unified KPI panel data
- GET /api/ops/dashboard/auto-actions - Auto-action history
- Notification routing matrix verification
- Auto-action guardrails verification
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestOpsKpisEndpoint:
    """Tests for GET /api/ops/dashboard/ops-kpis endpoint"""

    def test_ops_kpis_returns_200(self):
        """Verify ops-kpis endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: ops-kpis returns 200")

    def test_ops_kpis_structure(self):
        """Verify ops-kpis returns correct structure with all required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level fields
        assert "period_hours" in data, "Missing period_hours"
        assert "calculated_at" in data, "Missing calculated_at"
        assert "drift_alerts" in data, "Missing drift_alerts"
        assert "auto_actions" in data, "Missing auto_actions"
        assert "drift_trend" in data, "Missing drift_trend"
        assert "field_kpis" in data, "Missing field_kpis"
        
        print(f"PASS: ops-kpis structure verified - period_hours={data['period_hours']}")

    def test_ops_kpis_drift_alerts_structure(self):
        """Verify drift_alerts sub-structure in ops-kpis"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200
        data = response.json()
        
        drift_alerts = data.get("drift_alerts", {})
        assert "active_count" in drift_alerts, "Missing active_count in drift_alerts"
        assert "by_severity" in drift_alerts, "Missing by_severity in drift_alerts"
        assert "highest_severity" in drift_alerts, "Missing highest_severity in drift_alerts"
        
        print(f"PASS: drift_alerts structure - active_count={drift_alerts.get('active_count')}, highest={drift_alerts.get('highest_severity')}")

    def test_ops_kpis_auto_actions_structure(self):
        """Verify auto_actions sub-structure in ops-kpis"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200
        data = response.json()
        
        auto_actions = data.get("auto_actions", {})
        assert "total" in auto_actions, "Missing total in auto_actions"
        assert "success" in auto_actions, "Missing success in auto_actions"
        assert "failed" in auto_actions, "Missing failed in auto_actions"
        assert "success_rate" in auto_actions, "Missing success_rate in auto_actions"
        
        print(f"PASS: auto_actions structure - total={auto_actions.get('total')}, success_rate={auto_actions.get('success_rate')}%")

    def test_ops_kpis_field_kpis_structure(self):
        """Verify field_kpis sub-structure in ops-kpis"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200
        data = response.json()
        
        field_kpis = data.get("field_kpis", {})
        assert "sync_success" in field_kpis, "Missing sync_success in field_kpis"
        assert "mttr_hours" in field_kpis, "Missing mttr_hours in field_kpis"
        assert "drift_reduction" in field_kpis, "Missing drift_reduction in field_kpis"
        assert "push_sla_compliance" in field_kpis, "Missing push_sla_compliance in field_kpis"
        
        print(f"PASS: field_kpis structure verified with sync_success, mttr_hours, drift_reduction, push_sla_compliance")

    def test_ops_kpis_drift_trend_is_list(self):
        """Verify drift_trend is a list"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        assert response.status_code == 200
        data = response.json()
        
        drift_trend = data.get("drift_trend", [])
        assert isinstance(drift_trend, list), f"drift_trend should be list, got {type(drift_trend)}"
        
        print(f"PASS: drift_trend is list with {len(drift_trend)} entries")

    def test_ops_kpis_with_hours_param(self):
        """Verify ops-kpis accepts hours parameter"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis?hours=48")
        assert response.status_code == 200
        data = response.json()
        assert data.get("period_hours") == 48, f"Expected period_hours=48, got {data.get('period_hours')}"
        
        print("PASS: ops-kpis accepts hours parameter")


class TestAutoActionsEndpoint:
    """Tests for GET /api/ops/dashboard/auto-actions endpoint"""

    def test_auto_actions_returns_200(self):
        """Verify auto-actions endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/auto-actions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: auto-actions returns 200")

    def test_auto_actions_structure(self):
        """Verify auto-actions returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/auto-actions")
        assert response.status_code == 200
        data = response.json()
        
        assert "actions" in data, "Missing actions field"
        assert "count" in data, "Missing count field"
        assert isinstance(data["actions"], list), "actions should be a list"
        assert isinstance(data["count"], int), "count should be an integer"
        
        print(f"PASS: auto-actions structure - count={data['count']}")

    def test_auto_actions_with_limit(self):
        """Verify auto-actions accepts limit parameter"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/auto-actions?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("actions", [])) <= 5, "Limit not respected"
        
        print("PASS: auto-actions accepts limit parameter")


class TestDriftAlertsSummaryEnhanced:
    """Enhanced tests for drift-alerts/summary with notification routing info"""

    def test_drift_alerts_summary_returns_200(self):
        """Verify drift-alerts/summary returns 200"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        assert response.status_code == 200
        print("PASS: drift-alerts/summary returns 200")

    def test_drift_alerts_summary_structure(self):
        """Verify drift-alerts/summary structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "active_count" in data, "Missing active_count"
        assert "by_severity" in data, "Missing by_severity"
        assert "highest_severity" in data, "Missing highest_severity"
        assert "recent_alerts" in data, "Missing recent_alerts"
        
        by_severity = data.get("by_severity", {})
        assert "warning" in by_severity, "Missing warning in by_severity"
        assert "critical" in by_severity, "Missing critical in by_severity"
        assert "severe" in by_severity, "Missing severe in by_severity"
        
        print(f"PASS: drift-alerts/summary structure - active={data['active_count']}, highest={data['highest_severity']}")


class TestDriftAlertsListEnhanced:
    """Enhanced tests for drift-alerts list with notification routing"""

    def test_drift_alerts_list_returns_200(self):
        """Verify drift-alerts list returns 200"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts")
        assert response.status_code == 200
        print("PASS: drift-alerts list returns 200")

    def test_drift_alerts_list_structure(self):
        """Verify drift-alerts list structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts")
        assert response.status_code == 200
        data = response.json()
        
        assert "alerts" in data, "Missing alerts field"
        assert "count" in data, "Missing count field"
        
        print(f"PASS: drift-alerts list - count={data['count']}")


class TestDriftAlertEvaluateEnhanced:
    """Enhanced tests for drift-alerts/evaluate with auto-action support"""

    def test_drift_evaluate_returns_200(self):
        """Verify drift-alerts/evaluate returns 200"""
        response = requests.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/evaluate")
        assert response.status_code == 200
        print("PASS: drift-alerts/evaluate returns 200")

    def test_drift_evaluate_structure(self):
        """Verify drift-alerts/evaluate response structure"""
        response = requests.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/evaluate")
        assert response.status_code == 200
        data = response.json()
        
        assert "evaluated" in data, "Missing evaluated field"
        assert "alerts_fired" in data, "Missing alerts_fired field"
        
        if data.get("evaluated"):
            assert "tenant_id" in data, "Missing tenant_id when evaluated"
            assert "evaluated_at" in data, "Missing evaluated_at when evaluated"
            assert "evidence" in data, "Missing evidence when evaluated"
            
            evidence = data.get("evidence", {})
            assert "drift_records" in evidence, "Missing drift_records in evidence"
            assert "drift_nights" in evidence, "Missing drift_nights in evidence"
            assert "post_recon_drift" in evidence, "Missing post_recon_drift in evidence"
        
        print(f"PASS: drift-alerts/evaluate structure - evaluated={data.get('evaluated')}, alerts_fired={len(data.get('alerts_fired', []))}")


class TestRunbookEndpoint:
    """Tests for runbook endpoint"""

    def test_inventory_drift_runbook_returns_200(self):
        """Verify inventory_drift_detected runbook returns 200"""
        response = requests.get(f"{BASE_URL}/api/ops/runbooks/inventory_drift_detected")
        assert response.status_code == 200
        print("PASS: inventory_drift_detected runbook returns 200")

    def test_inventory_drift_runbook_structure(self):
        """Verify runbook structure"""
        response = requests.get(f"{BASE_URL}/api/ops/runbooks/inventory_drift_detected")
        assert response.status_code == 200
        data = response.json()
        
        assert "id" in data, "Missing id"
        assert "title" in data, "Missing title"
        assert "category" in data, "Missing category"
        assert "severity" in data, "Missing severity"
        
        print(f"PASS: runbook structure - id={data.get('id')}, category={data.get('category')}")


class TestNotificationRoutingMatrix:
    """Tests to verify notification routing matrix is correctly configured"""

    def test_notification_routing_in_code(self):
        """Verify NOTIFICATION_ROUTING constant exists and is correct"""
        # This is a code review test - we verify the routing matrix is correct
        # by checking the drift_alerting module
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from controlplane.drift_alerting import NOTIFICATION_ROUTING
            
            # Verify warning routing
            assert NOTIFICATION_ROUTING["warning"]["dashboard"] == True
            assert NOTIFICATION_ROUTING["warning"]["webhook"] == False
            assert NOTIFICATION_ROUTING["warning"]["escalation"] == False
            
            # Verify critical routing
            assert NOTIFICATION_ROUTING["critical"]["dashboard"] == True
            assert NOTIFICATION_ROUTING["critical"]["webhook"] == True
            assert NOTIFICATION_ROUTING["critical"]["escalation"] == False
            
            # Verify severe routing
            assert NOTIFICATION_ROUTING["severe"]["dashboard"] == True
            assert NOTIFICATION_ROUTING["severe"]["webhook"] == True
            assert NOTIFICATION_ROUTING["severe"]["escalation"] == True
            
            print("PASS: NOTIFICATION_ROUTING matrix verified")
            print(f"  warning: dashboard=True, webhook=False, escalation=False")
            print(f"  critical: dashboard=True, webhook=True, escalation=False")
            print(f"  severe: dashboard=True, webhook=True, escalation=True")
        except ImportError as e:
            pytest.skip(f"Could not import drift_alerting module: {e}")


class TestAutoActionGuardrails:
    """Tests to verify auto-action guardrails are in place"""

    def test_auto_action_cooldown_constant(self):
        """Verify AUTO_ACTION_COOLDOWN_MINUTES is set"""
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from controlplane.auto_actions import AUTO_ACTION_COOLDOWN_MINUTES
            
            assert AUTO_ACTION_COOLDOWN_MINUTES == 15, f"Expected 15 min cooldown, got {AUTO_ACTION_COOLDOWN_MINUTES}"
            print(f"PASS: AUTO_ACTION_COOLDOWN_MINUTES = {AUTO_ACTION_COOLDOWN_MINUTES}")
        except ImportError as e:
            pytest.skip(f"Could not import auto_actions module: {e}")


class TestIntegrationOpsKpisWithDriftAlerts:
    """Integration tests between ops-kpis and drift-alerts"""

    def test_ops_kpis_drift_alerts_matches_summary(self):
        """Verify ops-kpis drift_alerts matches drift-alerts/summary"""
        kpi_response = requests.get(f"{BASE_URL}/api/ops/dashboard/ops-kpis")
        summary_response = requests.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        
        assert kpi_response.status_code == 200
        assert summary_response.status_code == 200
        
        kpi_data = kpi_response.json()
        summary_data = summary_response.json()
        
        kpi_drift = kpi_data.get("drift_alerts", {})
        
        # Both should have same active_count
        assert kpi_drift.get("active_count") == summary_data.get("active_count"), \
            f"Mismatch: kpi={kpi_drift.get('active_count')}, summary={summary_data.get('active_count')}"
        
        # Both should have same highest_severity
        assert kpi_drift.get("highest_severity") == summary_data.get("highest_severity"), \
            f"Mismatch: kpi={kpi_drift.get('highest_severity')}, summary={summary_data.get('highest_severity')}"
        
        print(f"PASS: ops-kpis drift_alerts matches drift-alerts/summary")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
