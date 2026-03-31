"""
HotelRunner v2 Shadow Automation API Tests
============================================
Tests for the new shadow automation endpoints:
- GET /automation/status — automation status
- POST /automation/trigger — manual snapshot trigger
- GET /automation/trends — trend data (readiness, drift, latency, failure)
- GET /automation/alerts — alert history
- GET /automation/daily-summaries — daily summaries
- POST /automation/alerts/acknowledge — acknowledge alert
- GET /ops-dashboard — includes automation field
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TENANT_ID = "syroce_default"
PROPERTY_ID = "default"


class TestAutomationStatus:
    """Tests for GET /api/channel/hotelrunner-v2/automation/status"""

    def test_automation_status_returns_200(self):
        """Test automation status endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/status",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Automation status returned 200")

    def test_automation_status_response_structure(self):
        """Test automation status response has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/status",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "tenant_id" in data, "Missing tenant_id"
        assert "automation_active" in data, "Missing automation_active"
        assert "schedule" in data, "Missing schedule"
        assert "snapshots_24h" in data, "Missing snapshots_24h"
        assert "active_alerts" in data, "Missing active_alerts"
        assert "alerts_24h" in data, "Missing alerts_24h"
        assert "checked_at" in data, "Missing checked_at"

        # Schedule structure
        schedule = data["schedule"]
        assert "snapshot_interval" in schedule, "Missing snapshot_interval"
        assert "daily_summary" in schedule, "Missing daily_summary"
        assert "retention_cleanup" in schedule, "Missing retention_cleanup"

        print(f"✓ Automation status has all required fields")
        print(f"  - automation_active: {data['automation_active']}")
        print(f"  - snapshots_24h: {data['snapshots_24h']}")
        print(f"  - active_alerts: {data['active_alerts']}")


class TestAutomationTrigger:
    """Tests for POST /api/channel/hotelrunner-v2/automation/trigger"""

    def test_trigger_snapshot_returns_200(self):
        """Test manual snapshot trigger returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/trigger",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Automation trigger returned 200")

    def test_trigger_snapshot_response_structure(self):
        """Test trigger response has readiness, chain, and alerts data"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/trigger",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200
        data = response.json()

        # Required fields from run_periodic_snapshot
        assert "tenant_id" in data, "Missing tenant_id"
        assert "snapshot_type" in data, "Missing snapshot_type"
        assert "created_at" in data, "Missing created_at"
        assert "observation" in data, "Missing observation"
        assert "readiness" in data, "Missing readiness"
        assert "write_criteria" in data, "Missing write_criteria"

        # Readiness structure
        readiness = data["readiness"]
        assert "overall_score" in readiness, "Missing overall_score in readiness"
        assert "verdict" in readiness, "Missing verdict in readiness"

        # Dry-run chain may or may not be present
        if "dry_run_chain" in data and data["dry_run_chain"]:
            chain = data["dry_run_chain"]
            assert "success" in chain, "Missing success in dry_run_chain"
            assert "step_count" in chain, "Missing step_count in dry_run_chain"

        print(f"✓ Trigger snapshot has all required fields")
        print(f"  - readiness.overall_score: {readiness.get('overall_score')}")
        print(f"  - readiness.verdict: {readiness.get('verdict')}")
        print(f"  - alerts_generated: {data.get('alerts_generated', 0)}")


class TestAutomationTrends:
    """Tests for GET /api/channel/hotelrunner-v2/automation/trends"""

    def test_trends_returns_200(self):
        """Test trends endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/trends",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Automation trends returned 200")

    def test_trends_response_structure(self):
        """Test trends response has all 4 trend arrays"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/trends",
            params={"tenant_id": TENANT_ID, "hours": 168},
        )
        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "tenant_id" in data, "Missing tenant_id"
        assert "period_hours" in data, "Missing period_hours"
        assert "data_points" in data, "Missing data_points"
        assert "readiness_trend" in data, "Missing readiness_trend"
        assert "drift_trend" in data, "Missing drift_trend"
        assert "latency_trend" in data, "Missing latency_trend"
        assert "failure_trend" in data, "Missing failure_trend"

        # All trends should be arrays
        assert isinstance(data["readiness_trend"], list), "readiness_trend should be a list"
        assert isinstance(data["drift_trend"], list), "drift_trend should be a list"
        assert isinstance(data["latency_trend"], list), "latency_trend should be a list"
        assert isinstance(data["failure_trend"], list), "failure_trend should be a list"

        print(f"✓ Trends has all required fields")
        print(f"  - period_hours: {data['period_hours']}")
        print(f"  - data_points: {data['data_points']}")
        print(f"  - readiness_trend count: {len(data['readiness_trend'])}")
        print(f"  - drift_trend count: {len(data['drift_trend'])}")
        print(f"  - latency_trend count: {len(data['latency_trend'])}")
        print(f"  - failure_trend count: {len(data['failure_trend'])}")


class TestAutomationAlerts:
    """Tests for GET /api/channel/hotelrunner-v2/automation/alerts"""

    def test_alerts_returns_200(self):
        """Test alerts endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/alerts",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Automation alerts returned 200")

    def test_alerts_response_structure(self):
        """Test alerts response has alerts array and count"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/alerts",
            params={"tenant_id": TENANT_ID, "limit": 50},
        )
        assert response.status_code == 200
        data = response.json()

        assert "alerts" in data, "Missing alerts"
        assert "count" in data, "Missing count"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        assert isinstance(data["count"], int), "count should be an integer"

        print(f"✓ Alerts has required fields")
        print(f"  - count: {data['count']}")

        # If there are alerts, verify structure
        if data["alerts"]:
            alert = data["alerts"][0]
            assert "tenant_id" in alert, "Alert missing tenant_id"
            assert "rule_id" in alert, "Alert missing rule_id"
            assert "severity" in alert, "Alert missing severity"
            print(f"  - First alert rule_id: {alert.get('rule_id')}")
            print(f"  - First alert severity: {alert.get('severity')}")

    def test_alerts_filter_by_severity(self):
        """Test alerts can be filtered by severity"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/alerts",
            params={"tenant_id": TENANT_ID, "severity": "critical"},
        )
        assert response.status_code == 200
        data = response.json()

        # All returned alerts should be critical
        for alert in data["alerts"]:
            assert alert.get("severity") == "critical", f"Expected critical, got {alert.get('severity')}"

        print(f"✓ Alerts filter by severity works (critical count: {data['count']})")


class TestAutomationDailySummaries:
    """Tests for GET /api/channel/hotelrunner-v2/automation/daily-summaries"""

    def test_daily_summaries_returns_200(self):
        """Test daily summaries endpoint returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/daily-summaries",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Daily summaries returned 200")

    def test_daily_summaries_response_structure(self):
        """Test daily summaries response has summaries array and count"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/daily-summaries",
            params={"tenant_id": TENANT_ID, "limit": 30},
        )
        assert response.status_code == 200
        data = response.json()

        assert "summaries" in data, "Missing summaries"
        assert "count" in data, "Missing count"
        assert isinstance(data["summaries"], list), "summaries should be a list"

        print(f"✓ Daily summaries has required fields")
        print(f"  - count: {data['count']}")

        # If there are summaries, verify structure
        if data["summaries"]:
            summary = data["summaries"][0]
            assert "tenant_id" in summary, "Summary missing tenant_id"
            assert "summary_date" in summary, "Summary missing summary_date"
            print(f"  - First summary date: {summary.get('summary_date')}")


class TestAutomationAcknowledgeAlert:
    """Tests for POST /api/channel/hotelrunner-v2/automation/alerts/acknowledge"""

    def test_acknowledge_alert_returns_200(self):
        """Test acknowledge alert endpoint returns 200"""
        # First get an alert to acknowledge
        alerts_response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/alerts",
            params={"tenant_id": TENANT_ID, "limit": 1},
        )
        assert alerts_response.status_code == 200

        alerts_data = alerts_response.json()
        if not alerts_data["alerts"]:
            pytest.skip("No alerts to acknowledge")

        alert = alerts_data["alerts"][0]
        rule_id = alert.get("rule_id", "")
        snapshot_time = alert.get("snapshot_time", "")

        # Acknowledge the alert
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/automation/alerts/acknowledge",
            params={"tenant_id": TENANT_ID},
            json={"rule_id": rule_id, "snapshot_time": snapshot_time},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "modified" in data, "Missing modified field"
        print(f"✓ Acknowledge alert returned 200")
        print(f"  - modified: {data['modified']}")


class TestOpsDashboardAutomation:
    """Tests for GET /api/channel/hotelrunner-v2/ops-dashboard automation field"""

    def test_ops_dashboard_includes_automation(self):
        """Test ops-dashboard includes automation status and trends"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "automation" in data, "Missing automation field in ops-dashboard"

        automation = data["automation"]
        assert "status" in automation, "Missing status in automation"
        assert "trends" in automation, "Missing trends in automation"

        # Verify status structure
        status = automation["status"]
        assert "automation_active" in status, "Missing automation_active in status"
        assert "snapshots_24h" in status, "Missing snapshots_24h in status"

        # Verify trends structure
        trends = automation["trends"]
        assert "readiness_trend" in trends, "Missing readiness_trend in trends"
        assert "drift_trend" in trends, "Missing drift_trend in trends"
        assert "latency_trend" in trends, "Missing latency_trend in trends"
        assert "failure_trend" in trends, "Missing failure_trend in trends"
        assert "data_points" in trends, "Missing data_points in trends"

        print(f"✓ Ops dashboard includes automation field")
        print(f"  - automation_active: {status.get('automation_active')}")
        print(f"  - snapshots_24h: {status.get('snapshots_24h')}")
        print(f"  - trend data_points: {trends.get('data_points')}")


class TestCeleryBeatSchedules:
    """Tests to verify Celery Beat schedules are configured"""

    def test_celery_app_has_hrv2_schedules(self):
        """Verify celery_app.py has HRv2 shadow automation schedules"""
        import sys
        sys.path.insert(0, "/app/backend")

        from celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        # Check for HRv2 shadow automation schedules
        assert "hrv2-shadow-snapshot" in beat_schedule, "Missing hrv2-shadow-snapshot schedule"
        assert "hrv2-daily-summary" in beat_schedule, "Missing hrv2-daily-summary schedule"
        assert "hrv2-retention-cleanup" in beat_schedule, "Missing hrv2-retention-cleanup schedule"

        # Verify task names
        assert beat_schedule["hrv2-shadow-snapshot"]["task"] == "celery_tasks.hrv2_shadow_snapshot_task"
        assert beat_schedule["hrv2-daily-summary"]["task"] == "celery_tasks.hrv2_daily_summary_task"
        assert beat_schedule["hrv2-retention-cleanup"]["task"] == "celery_tasks.hrv2_retention_cleanup_task"

        print(f"✓ Celery Beat has all HRv2 shadow automation schedules")
        print(f"  - hrv2-shadow-snapshot: every 6 hours")
        print(f"  - hrv2-daily-summary: daily at 00:00 UTC")
        print(f"  - hrv2-retention-cleanup: weekly on Sunday at 05:00 UTC")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
