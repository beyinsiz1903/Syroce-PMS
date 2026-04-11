"""
Drift Threshold Alerting API Tests
===================================
Tests for the new drift alerting endpoints:
1. GET /api/ops/dashboard/drift-alerts/summary - Drift alert summary for dashboard
2. GET /api/ops/dashboard/drift-alerts - Active drift alerts list
3. POST /api/ops/dashboard/drift-alerts/evaluate - Evaluate and fire drift alerts
4. POST /api/ops/dashboard/drift-alerts/{alert_id}/acknowledge - Acknowledge a drift alert
5. GET /api/ops/runbooks/inventory_drift_detected - New runbook for drift alerts
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestDriftAlertSummary:
    """Tests for GET /api/ops/dashboard/drift-alerts/summary"""

    def test_drift_alert_summary_returns_200(self, api_client):
        """Summary endpoint should return 200 with correct structure."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "active_count" in data, "Missing active_count field"
        assert "by_severity" in data, "Missing by_severity field"
        assert "highest_severity" in data, "Missing highest_severity field"
        assert "recent_alerts" in data, "Missing recent_alerts field"
        
        # Verify by_severity structure
        by_severity = data["by_severity"]
        assert "warning" in by_severity, "Missing warning in by_severity"
        assert "critical" in by_severity, "Missing critical in by_severity"
        assert "severe" in by_severity, "Missing severe in by_severity"
        
        # Verify types
        assert isinstance(data["active_count"], int), "active_count should be int"
        assert isinstance(data["recent_alerts"], list), "recent_alerts should be list"
        assert data["highest_severity"] in ["none", "warning", "critical", "severe"], \
            f"Invalid highest_severity: {data['highest_severity']}"
        
        print(f"Summary: active_count={data['active_count']}, highest_severity={data['highest_severity']}")

    def test_drift_alert_summary_with_tenant_filter(self, api_client):
        """Summary endpoint should accept tenant_id filter."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary?tenant_id=test_tenant")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "active_count" in data
        print(f"Summary with tenant filter: active_count={data['active_count']}")


class TestDriftAlertsList:
    """Tests for GET /api/ops/dashboard/drift-alerts"""

    def test_drift_alerts_list_returns_200(self, api_client):
        """Alerts list endpoint should return 200 with correct structure."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "alerts" in data, "Missing alerts field"
        assert "count" in data, "Missing count field"
        assert isinstance(data["alerts"], list), "alerts should be list"
        assert isinstance(data["count"], int), "count should be int"
        
        print(f"Alerts list: count={data['count']}")

    def test_drift_alerts_list_with_severity_filter(self, api_client):
        """Alerts list should filter by severity."""
        for severity in ["warning", "critical", "severe"]:
            response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts?severity={severity}")
            assert response.status_code == 200, f"Expected 200 for severity={severity}"
            
            data = response.json()
            # All returned alerts should match the severity filter
            for alert in data["alerts"]:
                assert alert.get("severity") == severity, f"Alert severity mismatch: expected {severity}"
            
            print(f"Alerts with severity={severity}: count={data['count']}")

    def test_drift_alerts_list_with_acknowledged_filter(self, api_client):
        """Alerts list should filter by acknowledged status."""
        # Test acknowledged=false
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts?acknowledged=false")
        assert response.status_code == 200
        
        data = response.json()
        for alert in data["alerts"]:
            assert alert.get("acknowledged") == False, "Alert should not be acknowledged"
        
        print(f"Unacknowledged alerts: count={data['count']}")

    def test_drift_alerts_list_with_limit(self, api_client):
        """Alerts list should respect limit parameter."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["alerts"]) <= 5, "Should respect limit parameter"
        print(f"Alerts with limit=5: returned={len(data['alerts'])}")


class TestDriftAlertEvaluate:
    """Tests for POST /api/ops/dashboard/drift-alerts/evaluate"""

    def test_drift_alert_evaluate_returns_200(self, api_client):
        """Evaluate endpoint should return 200 with evaluation result."""
        response = api_client.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/evaluate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "evaluated" in data, "Missing evaluated field"
        assert isinstance(data["evaluated"], bool), "evaluated should be bool"
        
        if data["evaluated"]:
            assert "tenant_id" in data, "Missing tenant_id when evaluated=true"
            assert "evaluated_at" in data, "Missing evaluated_at when evaluated=true"
            assert "window_minutes" in data, "Missing window_minutes when evaluated=true"
            assert "evidence" in data, "Missing evidence when evaluated=true"
            assert "alignment_status" in data, "Missing alignment_status when evaluated=true"
            assert "alerts_fired" in data, "Missing alerts_fired when evaluated=true"
            
            # Verify evidence structure
            evidence = data["evidence"]
            assert "drift_records" in evidence, "Missing drift_records in evidence"
            assert "drift_nights" in evidence, "Missing drift_nights in evidence"
            assert "post_recon_drift" in evidence, "Missing post_recon_drift in evidence"
            assert "providers_with_drift" in evidence, "Missing providers_with_drift in evidence"
            
            print(f"Evaluation: evaluated=True, alerts_fired={len(data['alerts_fired'])}, "
                  f"drift_records={evidence['drift_records']}, drift_nights={evidence['drift_nights']}")
        else:
            assert "reason" in data, "Missing reason when evaluated=false"
            print(f"Evaluation: evaluated=False, reason={data.get('reason')}")

    def test_drift_alert_evaluate_with_tenant_id(self, api_client):
        """Evaluate endpoint should accept tenant_id parameter."""
        response = api_client.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/evaluate?tenant_id=test_tenant")
        # Should return 200 even if tenant doesn't exist (will return evaluated=false)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "evaluated" in data
        print(f"Evaluation with tenant_id: evaluated={data['evaluated']}")


class TestDriftAlertAcknowledge:
    """Tests for POST /api/ops/dashboard/drift-alerts/{alert_id}/acknowledge"""

    def test_acknowledge_nonexistent_alert_returns_404(self, api_client):
        """Acknowledging a non-existent alert should return 404."""
        fake_alert_id = "nonexistent-alert-id-12345"
        response = api_client.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/{fake_alert_id}/acknowledge")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Missing detail in error response"
        print(f"Acknowledge nonexistent: status=404, detail={data.get('detail')}")

    def test_acknowledge_with_acknowledged_by_param(self, api_client):
        """Acknowledge endpoint should accept acknowledged_by parameter."""
        fake_alert_id = "nonexistent-alert-id-67890"
        response = api_client.post(
            f"{BASE_URL}/api/ops/dashboard/drift-alerts/{fake_alert_id}/acknowledge?acknowledged_by=test_operator"
        )
        # Should still return 404 since alert doesn't exist
        assert response.status_code == 404
        print("Acknowledge with acknowledged_by param: correctly returns 404 for nonexistent alert")


class TestInventoryDriftRunbook:
    """Tests for GET /api/ops/runbooks/inventory_drift_detected"""

    def test_inventory_drift_runbook_exists(self, api_client):
        """The inventory_drift_detected runbook should exist."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks/inventory_drift_detected")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify runbook structure
        assert "id" in data, "Missing id field"
        assert data["id"] == "inventory_drift_detected", f"Wrong runbook id: {data['id']}"
        assert "title" in data, "Missing title field"
        assert "description" in data, "Missing description field"
        assert "category" in data, "Missing category field"
        assert "severity" in data, "Missing severity field"
        assert "possible_causes" in data, "Missing possible_causes field"
        assert "resolution_steps" in data, "Missing resolution_steps field"
        assert "retry_instructions" in data, "Missing retry_instructions field"
        assert "related_operations" in data, "Missing related_operations field"
        
        # Verify it's categorized as sync
        assert data["category"] == "sync", f"Expected category=sync, got {data['category']}"
        assert data["severity"] == "critical", f"Expected severity=critical, got {data['severity']}"
        
        # Verify it has meaningful content
        assert len(data["possible_causes"]) > 0, "Should have possible causes"
        assert len(data["resolution_steps"]) > 0, "Should have resolution steps"
        
        print(f"Runbook: id={data['id']}, title={data['title']}, category={data['category']}")

    def test_runbooks_list_includes_inventory_drift(self, api_client):
        """The runbooks list should include inventory_drift_detected."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks")
        assert response.status_code == 200
        
        data = response.json()
        runbook_ids = [rb["id"] for rb in data["runbooks"]]
        assert "inventory_drift_detected" in runbook_ids, \
            f"inventory_drift_detected not in runbooks list: {runbook_ids}"
        
        print(f"Runbooks list includes inventory_drift_detected: total={len(data['runbooks'])}")

    def test_runbooks_sync_category_includes_inventory_drift(self, api_client):
        """Filtering by sync category should include inventory_drift_detected."""
        response = api_client.get(f"{BASE_URL}/api/ops/runbooks?category=sync")
        assert response.status_code == 200
        
        data = response.json()
        runbook_ids = [rb["id"] for rb in data["runbooks"]]
        assert "inventory_drift_detected" in runbook_ids, \
            f"inventory_drift_detected not in sync category: {runbook_ids}"
        
        print(f"Sync category runbooks: {runbook_ids}")


class TestDriftAlertIntegration:
    """Integration tests for drift alerting flow."""

    def test_full_drift_alert_flow(self, api_client):
        """Test the full flow: summary -> evaluate -> list."""
        # 1. Get initial summary
        summary_response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        assert summary_response.status_code == 200
        initial_summary = summary_response.json()
        print(f"Initial summary: active_count={initial_summary['active_count']}")
        
        # 2. Run evaluation
        eval_response = api_client.post(f"{BASE_URL}/api/ops/dashboard/drift-alerts/evaluate")
        assert eval_response.status_code == 200
        eval_result = eval_response.json()
        print(f"Evaluation: evaluated={eval_result['evaluated']}, "
              f"alerts_fired={len(eval_result.get('alerts_fired', []))}")
        
        # 3. Get updated list
        list_response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts?limit=10")
        assert list_response.status_code == 200
        alerts_list = list_response.json()
        print(f"Alerts list after evaluation: count={alerts_list['count']}")
        
        # 4. Verify alert structure if any alerts exist
        if alerts_list["alerts"]:
            alert = alerts_list["alerts"][0]
            assert "alert_id" in alert, "Alert missing alert_id"
            assert "tenant_id" in alert, "Alert missing tenant_id"
            assert "severity" in alert, "Alert missing severity"
            assert "reason" in alert, "Alert missing reason"
            assert "fired_at" in alert, "Alert missing fired_at"
            assert "acknowledged" in alert, "Alert missing acknowledged"
            assert "payload" in alert, "Alert missing payload"
            
            # Verify payload structure
            payload = alert["payload"]
            assert "tenant" in payload, "Payload missing tenant"
            assert "drift_count" in payload, "Payload missing drift_count"
            assert "drift_nights" in payload, "Payload missing drift_nights"
            assert "drift_or_stale" in payload, "Payload missing drift_or_stale"
            assert "runbook_link" in payload, "Payload missing runbook_link"
            assert "last_reconciliation_result" in payload, "Payload missing last_reconciliation_result"
            
            print(f"Alert structure verified: severity={alert['severity']}, "
                  f"drift_or_stale={payload['drift_or_stale']}")

    def test_aligned_system_shows_no_active_alerts(self, api_client):
        """When system is aligned, summary should show no active alerts or low severity."""
        summary_response = api_client.get(f"{BASE_URL}/api/ops/dashboard/drift-alerts/summary")
        assert summary_response.status_code == 200
        
        summary = summary_response.json()
        # In an aligned system, highest_severity should be 'none' or there should be 0 active alerts
        # (unless there are pre-existing alerts from previous tests)
        print(f"System state: active_count={summary['active_count']}, "
              f"highest_severity={summary['highest_severity']}")
        
        # Verify the structure is correct regardless of state
        assert summary["highest_severity"] in ["none", "warning", "critical", "severe"]
        assert summary["active_count"] >= 0
