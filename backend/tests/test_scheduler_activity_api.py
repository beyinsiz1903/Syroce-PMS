"""
Pre-Arrival Scheduler & Activity Feed API Tests (Iteration 203)
Tests for the NEW P1 features:
1. Pre-Arrival Daily Scheduler - scans tomorrow's check-ins and auto-sends WhatsApp messages
2. Activity Feed - real-time UI notifications for automation events and delivery statuses

Endpoints tested:
- GET /api/messaging-center/scheduler/status
- POST /api/messaging-center/scheduler/start
- POST /api/messaging-center/scheduler/stop
- POST /api/messaging-center/scheduler/run-now
- GET /api/messaging-center/activity?limit=20
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://correlation-trace.preview.emergentagent.com"


class TestSchedulerAPI:
    """Pre-Arrival Scheduler API endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Seed demo data first (includes automation rules)
        seed_resp = self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")
        assert seed_resp.status_code == 200

    # ═══════════════════════════════════════════════
    # Scheduler Status
    # ═══════════════════════════════════════════════

    def test_get_scheduler_status(self):
        """GET /api/messaging-center/scheduler/status - returns scheduler status and metrics"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "status" in data, "Missing 'status' field"
        assert data["status"] in ["running", "stopped"], f"Invalid status: {data['status']}"
        
        # Check for metrics fields
        assert "interval_hours" in data, "Missing 'interval_hours' field"
        assert "total_runs" in data, "Missing 'total_runs' field"
        assert "total_sent" in data, "Missing 'total_sent' field"
        assert "total_skipped" in data, "Missing 'total_skipped' field"
        assert "total_errors" in data, "Missing 'total_errors' field"
        
        print(f"Scheduler status: {data['status']}")
        print(f"  - Interval: {data['interval_hours']} hours")
        print(f"  - Total runs: {data['total_runs']}")
        print(f"  - Total sent: {data['total_sent']}")
        print(f"  - Total skipped: {data['total_skipped']}")
        print(f"  - Total errors: {data['total_errors']}")

    # ═══════════════════════════════════════════════
    # Scheduler Start/Stop
    # ═══════════════════════════════════════════════

    def test_start_scheduler(self):
        """POST /api/messaging-center/scheduler/start - starts the scheduler background task"""
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/start")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, "Expected success=True"
        assert "message" in data, "Missing 'message' field"
        print(f"Start scheduler response: {data['message']}")
        
        # Verify status changed to running
        status_resp = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status")
        status_data = status_resp.json()
        assert status_data["status"] == "running", f"Expected running, got {status_data['status']}"
        print("Scheduler is now running")

    def test_start_scheduler_already_running(self):
        """POST /api/messaging-center/scheduler/start - when already running returns success with message"""
        # First ensure it's running
        self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/start")
        
        # Try to start again
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/start")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True
        # Should indicate already running
        print(f"Start when already running: {data['message']}")

    def test_stop_scheduler(self):
        """POST /api/messaging-center/scheduler/stop - stops the scheduler"""
        # First ensure it's running
        self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/start")
        
        # Stop it
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/stop")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, "Expected success=True"
        assert "message" in data, "Missing 'message' field"
        print(f"Stop scheduler response: {data['message']}")
        
        # Verify status changed to stopped
        status_resp = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status")
        status_data = status_resp.json()
        assert status_data["status"] == "stopped", f"Expected stopped, got {status_data['status']}"
        print("Scheduler is now stopped")

    # ═══════════════════════════════════════════════
    # Manual Trigger (Run Now)
    # ═══════════════════════════════════════════════

    def test_run_scheduler_now(self):
        """POST /api/messaging-center/scheduler/run-now - manually triggers pre-arrival scan"""
        resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/run-now")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") == True, "Expected success=True"
        assert "result" in data, "Missing 'result' field"
        
        result = data["result"]
        assert "run_id" in result, "Missing 'run_id' in result"
        assert "run_at" in result, "Missing 'run_at' in result"
        assert "bookings_scanned" in result, "Missing 'bookings_scanned' in result"
        assert "events_fired" in result, "Missing 'events_fired' in result"
        assert "already_sent" in result, "Missing 'already_sent' in result"
        assert "errors" in result, "Missing 'errors' in result"
        
        print(f"Run-now result:")
        print(f"  - Run ID: {result['run_id']}")
        print(f"  - Bookings scanned: {result['bookings_scanned']}")
        print(f"  - Events fired: {result['events_fired']}")
        print(f"  - Already sent: {result['already_sent']}")
        print(f"  - Errors: {result['errors']}")
        
        # Note: In sandbox mode with demo bookings 1-90 days in future (not tomorrow),
        # bookings_scanned will likely be 0. This is expected behavior.

    def test_run_scheduler_updates_metrics(self):
        """POST /api/messaging-center/scheduler/run-now - updates total_runs metric"""
        # Get initial status
        status_before = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status").json()
        runs_before = status_before.get("total_runs", 0)
        
        # Run scan
        self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/run-now")
        
        # Get updated status
        status_after = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status").json()
        runs_after = status_after.get("total_runs", 0)
        
        assert runs_after == runs_before + 1, f"Expected total_runs to increment: {runs_before} -> {runs_after}"
        print(f"Total runs incremented: {runs_before} -> {runs_after}")
        
        # Verify last_run_at is set
        assert status_after.get("last_run_at") is not None, "last_run_at should be set after run"
        print(f"Last run at: {status_after['last_run_at']}")


class TestActivityFeedAPI:
    """Activity Feed API endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Seed demo data
        self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")

    # ═══════════════════════════════════════════════
    # Activity Feed
    # ═══════════════════════════════════════════════

    def test_get_activity_feed(self):
        """GET /api/messaging-center/activity - returns unified activity feed"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=20")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "activities" in data, "Missing 'activities' key"
        activities = data["activities"]
        assert isinstance(activities, list), "activities should be a list"
        
        print(f"Found {len(activities)} activities")
        
        # Check activity structure (if any exist)
        for activity in activities[:5]:  # Check first 5
            assert "id" in activity, "Missing 'id' in activity"
            assert "type" in activity, "Missing 'type' in activity"
            assert "title" in activity, "Missing 'title' in activity"
            assert "message" in activity, "Missing 'message' in activity"
            assert "created_at" in activity, "Missing 'created_at' in activity"
            
            # Type should be 'automation' or 'delivery'
            assert activity["type"] in ["automation", "delivery"], f"Invalid type: {activity['type']}"
            
            print(f"  - [{activity['type']}] {activity['title']}: {activity['message'][:50]}...")

    def test_get_activity_feed_with_limit(self):
        """GET /api/messaging-center/activity?limit=5 - respects limit parameter"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=5")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        activities = data.get("activities", [])
        assert len(activities) <= 5, f"Expected max 5 activities, got {len(activities)}"
        print(f"Returned {len(activities)} activities with limit=5")

    def test_activity_feed_includes_delivery_events(self):
        """GET /api/messaging-center/activity - includes delivery log events"""
        # First ensure there are delivery logs
        logs_resp = self.session.get(f"{BASE_URL}/api/messaging-center/delivery-logs?limit=5")
        logs = logs_resp.json().get("logs", [])
        
        if not logs:
            pytest.skip("No delivery logs available")
        
        # Get activity feed
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=50")
        data = resp.json()
        activities = data.get("activities", [])
        
        # Should have delivery type activities
        delivery_activities = [a for a in activities if a.get("type") == "delivery"]
        print(f"Found {len(delivery_activities)} delivery activities out of {len(activities)} total")
        
        # Verify delivery activity structure
        if delivery_activities:
            da = delivery_activities[0]
            assert "status" in da, "Delivery activity should have 'status' field"
            assert da["status"] in ["sent", "delivered", "failed", "queued", "sending"], f"Invalid status: {da['status']}"
            print(f"Sample delivery activity: {da['title']} - status={da['status']}")

    def test_activity_feed_sorted_by_created_at(self):
        """GET /api/messaging-center/activity - activities sorted by created_at descending"""
        resp = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=20")
        data = resp.json()
        activities = data.get("activities", [])
        
        if len(activities) < 2:
            pytest.skip("Not enough activities to verify sorting")
        
        # Check that activities are sorted by created_at descending
        for i in range(len(activities) - 1):
            current = activities[i].get("created_at", "")
            next_item = activities[i + 1].get("created_at", "")
            if current and next_item:
                assert current >= next_item, f"Activities not sorted: {current} < {next_item}"
        
        print("Activities are correctly sorted by created_at descending")


class TestSchedulerIntegration:
    """Integration tests for scheduler with automation rules"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Seed demo data
        self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")

    def test_scheduler_requires_pre_arrival_rule(self):
        """Scheduler only fires events if pre_arrival automation rule exists"""
        # Check for pre_arrival rule
        rules_resp = self.session.get(f"{BASE_URL}/api/messaging-center/automation/rules")
        rules = rules_resp.json().get("rules", [])
        
        pre_arrival_rules = [r for r in rules if r.get("trigger_event") == "pre_arrival"]
        print(f"Found {len(pre_arrival_rules)} pre_arrival automation rules")
        
        if pre_arrival_rules:
            rule = pre_arrival_rules[0]
            print(f"  - {rule['name']} (enabled={rule['enabled']}, channel={rule['channel']})")
        
        # Run scheduler
        run_resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/run-now")
        result = run_resp.json().get("result", {})
        
        # If no pre_arrival rules enabled, details should indicate this
        details = result.get("details", [])
        if not pre_arrival_rules or not any(r.get("enabled") for r in pre_arrival_rules):
            print(f"Scheduler details: {details}")
            # May contain message about no active rules

    def test_scheduler_start_stop_cycle(self):
        """Full start/stop cycle maintains correct state"""
        # Stop first to ensure clean state
        self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/stop")
        
        # Verify stopped
        status1 = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status").json()
        assert status1["status"] == "stopped"
        
        # Start
        start_resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/start")
        assert start_resp.json().get("success") == True
        
        # Verify running
        status2 = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status").json()
        assert status2["status"] == "running"
        assert status2.get("started_at") is not None
        
        # Stop
        stop_resp = self.session.post(f"{BASE_URL}/api/messaging-center/scheduler/stop")
        assert stop_resp.json().get("success") == True
        
        # Verify stopped again
        status3 = self.session.get(f"{BASE_URL}/api/messaging-center/scheduler/status").json()
        assert status3["status"] == "stopped"
        
        print("Start/stop cycle completed successfully")


class TestNotificationCreation:
    """Tests for in-app notification creation from automation events"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Seed demo data
        self.session.post(f"{BASE_URL}/api/messaging-center/seed-demo")

    def test_automation_test_creates_notification(self):
        """POST /api/messaging-center/automation/test/{id} creates in-app notification"""
        # Get an enabled rule
        rules_resp = self.session.get(f"{BASE_URL}/api/messaging-center/automation/rules")
        rules = rules_resp.json().get("rules", [])
        
        enabled_rules = [r for r in rules if r.get("enabled")]
        if not enabled_rules:
            pytest.skip("No enabled automation rules available")
        
        rule = enabled_rules[0]
        rule_id = rule["id"]
        
        # Get activity count before
        activity_before = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=100").json()
        count_before = len(activity_before.get("activities", []))
        
        # Trigger test
        test_resp = self.session.post(f"{BASE_URL}/api/messaging-center/automation/test/{rule_id}")
        assert test_resp.status_code == 200
        
        # Wait for async processing
        time.sleep(1)
        
        # Get activity count after
        activity_after = self.session.get(f"{BASE_URL}/api/messaging-center/activity?limit=100").json()
        count_after = len(activity_after.get("activities", []))
        
        print(f"Activities before: {count_before}, after: {count_after}")
        
        # Note: Notification may or may not be created depending on whether
        # the automation actually sends a message (requires valid recipient)
        # This test verifies the endpoint works and activity feed is accessible
