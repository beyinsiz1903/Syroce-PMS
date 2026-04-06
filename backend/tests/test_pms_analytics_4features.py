"""
PMS Analytics API Tests - 4 New Features
1. Channel Loss Analytics (FULL)
2. Overbooking Heatmap (FULL)
3. Rule Engine (LIGHT)
4. No-Show Prediction (BASIC)

Tests all endpoints in /app/backend/routers/pms_analytics.py
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://pms-channel-sync-1.preview.emergentagent.com").rstrip("/")


class TestAuth:
    """Get auth token for subsequent tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get JWT token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Return headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}


# ─────────────────────────────────────────────────────────
# 1. CHANNEL LOSS ANALYTICS TESTS
# ─────────────────────────────────────────────────────────

class TestChannelLossAnalytics(TestAuth):
    """Tests for GET /api/pms/channel-loss-analytics"""
    
    def test_channel_loss_default_30_days(self, auth_headers):
        """Test channel loss analytics with default 30 days period"""
        response = requests.get(
            f"{BASE_URL}/api/pms/channel-loss-analytics",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "channels" in data, "Missing 'channels' field"
        assert "top3_worst" in data, "Missing 'top3_worst' field"
        assert "trend" in data, "Missing 'trend' field"
        assert "trend_channels" in data, "Missing 'trend_channels' field"
        assert "period_days" in data, "Missing 'period_days' field"
        assert "total_no_shows" in data, "Missing 'total_no_shows' field"
        assert "total_loss" in data, "Missing 'total_loss' field"
        assert "data_quality" in data, "Missing 'data_quality' field"
        
        # Verify data quality structure
        dq = data["data_quality"]
        assert "confidence" in dq, "Missing confidence in data_quality"
        assert "note" in dq, "Missing note in data_quality"
        assert dq["confidence"] in ["low", "medium", "high"], f"Invalid confidence: {dq['confidence']}"
        
        print(f"✓ Channel Loss: {data['total_no_shows']} no-shows, {data['total_loss']} TL loss, {len(data['channels'])} channels")
    
    def test_channel_loss_7_days(self, auth_headers):
        """Test channel loss analytics with 7 days period"""
        response = requests.get(
            f"{BASE_URL}/api/pms/channel-loss-analytics?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["period_days"] == 7, f"Expected period_days=7, got {data['period_days']}"
        print(f"✓ Channel Loss (7 days): {data['total_no_shows']} no-shows")
    
    def test_channel_loss_90_days(self, auth_headers):
        """Test channel loss analytics with 90 days period"""
        response = requests.get(
            f"{BASE_URL}/api/pms/channel-loss-analytics?days=90",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["period_days"] == 90
        print(f"✓ Channel Loss (90 days): {data['total_no_shows']} no-shows")
    
    def test_channel_loss_top3_worst_structure(self, auth_headers):
        """Verify top3_worst channel structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/channel-loss-analytics",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # top3_worst should be a list with max 3 items
        assert isinstance(data["top3_worst"], list)
        assert len(data["top3_worst"]) <= 3
        
        # Each item should have required fields
        for ch in data["top3_worst"]:
            assert "channel" in ch, "Missing 'channel' in top3_worst item"
            assert "no_show_count" in ch, "Missing 'no_show_count'"
            assert "total_loss" in ch, "Missing 'total_loss'"
            assert "avg_loss" in ch, "Missing 'avg_loss'"
            assert "no_show_rate" in ch, "Missing 'no_show_rate'"
        
        print(f"✓ Top 3 worst channels: {[c['channel'] for c in data['top3_worst']]}")
    
    def test_channel_loss_channel_detail_structure(self, auth_headers):
        """Verify channel detail structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/channel-loss-analytics",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for ch in data["channels"]:
            assert "channel" in ch
            assert "no_show_count" in ch
            assert "total_loss" in ch
            assert "avg_loss" in ch
            assert "no_show_rate" in ch
            assert "total_bookings" in ch
        
        print(f"✓ Channel details verified for {len(data['channels'])} channels")


# ─────────────────────────────────────────────────────────
# 2. OVERBOOKING HEATMAP TESTS
# ─────────────────────────────────────────────────────────

class TestOverbookingHeatmap(TestAuth):
    """Tests for GET /api/pms/overbooking-heatmap"""
    
    def test_heatmap_default_90_days(self, auth_headers):
        """Test overbooking heatmap with default 90 days"""
        response = requests.get(
            f"{BASE_URL}/api/pms/overbooking-heatmap",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "heatmap" in data, "Missing 'heatmap' field"
        assert "peak_days" in data, "Missing 'peak_days' field"
        assert "weekly_pattern" in data, "Missing 'weekly_pattern' field"
        assert "channel_overlay" in data, "Missing 'channel_overlay' field"
        assert "total_overbookings" in data, "Missing 'total_overbookings' field"
        assert "total_loss" in data, "Missing 'total_loss' field"
        assert "period_days" in data, "Missing 'period_days' field"
        assert "data_quality" in data, "Missing 'data_quality' field"
        
        print(f"✓ Heatmap: {data['total_overbookings']} overbookings, {len(data['heatmap'])} days")
    
    def test_heatmap_30_days(self, auth_headers):
        """Test heatmap with 30 days period"""
        response = requests.get(
            f"{BASE_URL}/api/pms/overbooking-heatmap?days=30",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 30
        print(f"✓ Heatmap (30 days): {data['total_overbookings']} overbookings")
    
    def test_heatmap_weekly_pattern_structure(self, auth_headers):
        """Verify weekly pattern has 7 days"""
        response = requests.get(
            f"{BASE_URL}/api/pms/overbooking-heatmap",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have exactly 7 days
        assert len(data["weekly_pattern"]) == 7, f"Expected 7 days, got {len(data['weekly_pattern'])}"
        
        for day in data["weekly_pattern"]:
            assert "day_index" in day
            assert "day_name" in day
            assert "overbooking_total" in day
            assert "noshow_total" in day
            assert "avg_overbooking" in day
            assert "is_weekend" in day
        
        # Verify weekend flags
        weekends = [d for d in data["weekly_pattern"] if d["is_weekend"]]
        assert len(weekends) == 2, "Should have 2 weekend days"
        
        print(f"✓ Weekly pattern verified: {[d['day_name'] for d in data['weekly_pattern']]}")
    
    def test_heatmap_peak_days_structure(self, auth_headers):
        """Verify peak days structure (top 5)"""
        response = requests.get(
            f"{BASE_URL}/api/pms/overbooking-heatmap",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Peak days should be max 5
        assert len(data["peak_days"]) <= 5
        
        for day in data["peak_days"]:
            assert "date" in day
            assert "overbooking_count" in day
            assert "total_noshow" in day
            assert "loss" in day
        
        print(f"✓ Peak days: {len(data['peak_days'])} days")
    
    def test_heatmap_data_quality(self, auth_headers):
        """Verify data quality structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/overbooking-heatmap",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        dq = data["data_quality"]
        assert "confidence" in dq
        assert "note" in dq
        assert "data_points" in dq
        assert "data_days" in dq
        assert dq["confidence"] in ["low", "medium", "high"]
        
        print(f"✓ Data quality: {dq['confidence']} ({dq['data_points']} data points)")


# ─────────────────────────────────────────────────────────
# 3. RULE ENGINE TESTS
# ─────────────────────────────────────────────────────────

class TestRuleEngine(TestAuth):
    """Tests for Alert Rule Engine endpoints"""
    
    def test_list_rules(self, auth_headers):
        """Test GET /api/pms/alert-rules"""
        response = requests.get(
            f"{BASE_URL}/api/pms/alert-rules",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "rules" in data, "Missing 'rules' field"
        assert isinstance(data["rules"], list)
        
        print(f"✓ List rules: {len(data['rules'])} rules found")
        return data["rules"]
    
    def test_create_rule(self, auth_headers):
        """Test POST /api/pms/alert-rules"""
        rule_name = f"TEST_rule_{uuid.uuid4().hex[:8]}"
        payload = {
            "rule_name": rule_name,
            "rule_type": "overbooking_high",
            "condition_metric": "overbooking_count",
            "condition_operator": "gt",
            "condition_value": 10,
            "action_suggestion": "rate_dusur",
            "channel_filter": None,
            "is_active": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/pms/alert-rules",
            headers=auth_headers,
            json=payload
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify created rule
        assert "id" in data, "Missing 'id' in created rule"
        assert data["rule_name"] == rule_name
        assert data["condition_metric"] == "overbooking_count"
        assert data["condition_value"] == 10
        assert data["is_active"] == True
        
        print(f"✓ Created rule: {data['id']}")
        return data["id"]
    
    def test_toggle_rule(self, auth_headers):
        """Test PATCH /api/pms/alert-rules/{rule_id}/toggle"""
        # First create a rule
        rule_name = f"TEST_toggle_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/pms/alert-rules",
            headers=auth_headers,
            json={
                "rule_name": rule_name,
                "rule_type": "noshow_rate_high",
                "condition_metric": "noshow_rate",
                "condition_operator": "gt",
                "condition_value": 15,
                "action_suggestion": "prepaid_zorunlu",
                "is_active": True
            }
        )
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["id"]
        
        # Toggle off
        toggle_resp = requests.patch(
            f"{BASE_URL}/api/pms/alert-rules/{rule_id}/toggle",
            headers=auth_headers
        )
        assert toggle_resp.status_code == 200, f"Toggle failed: {toggle_resp.text}"
        assert toggle_resp.json()["is_active"] == False
        
        # Toggle back on
        toggle_resp2 = requests.patch(
            f"{BASE_URL}/api/pms/alert-rules/{rule_id}/toggle",
            headers=auth_headers
        )
        assert toggle_resp2.status_code == 200
        assert toggle_resp2.json()["is_active"] == True
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/pms/alert-rules/{rule_id}", headers=auth_headers)
        
        print(f"✓ Toggle rule works correctly")
    
    def test_delete_rule(self, auth_headers):
        """Test DELETE /api/pms/alert-rules/{rule_id}"""
        # Create a rule to delete
        rule_name = f"TEST_delete_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{BASE_URL}/api/pms/alert-rules",
            headers=auth_headers,
            json={
                "rule_name": rule_name,
                "rule_type": "overbooking_high",
                "condition_metric": "overbooking_count",
                "condition_operator": "gte",
                "condition_value": 5,
                "action_suggestion": "kanal_kapat",
                "is_active": True
            }
        )
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["id"]
        
        # Delete the rule
        delete_resp = requests.delete(
            f"{BASE_URL}/api/pms/alert-rules/{rule_id}",
            headers=auth_headers
        )
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        assert "message" in delete_resp.json()
        
        # Verify deletion - should get 404
        get_resp = requests.delete(
            f"{BASE_URL}/api/pms/alert-rules/{rule_id}",
            headers=auth_headers
        )
        assert get_resp.status_code == 404, "Rule should not exist after deletion"
        
        print(f"✓ Delete rule works correctly")
    
    def test_delete_nonexistent_rule(self, auth_headers):
        """Test DELETE with non-existent rule returns 404"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(
            f"{BASE_URL}/api/pms/alert-rules/{fake_id}",
            headers=auth_headers
        )
        assert response.status_code == 404
        print(f"✓ Delete non-existent rule returns 404")
    
    def test_evaluate_rules(self, auth_headers):
        """Test POST /api/pms/alert-rules/evaluate"""
        response = requests.post(
            f"{BASE_URL}/api/pms/alert-rules/evaluate?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "alerts" in data, "Missing 'alerts' field"
        assert "rules_evaluated" in data, "Missing 'rules_evaluated' field"
        assert "metrics" in data, "Missing 'metrics' field"
        assert "period_days" in data, "Missing 'period_days' field"
        
        # Verify metrics structure
        metrics = data["metrics"]
        assert "overbooking_count" in metrics
        assert "noshow_count" in metrics
        assert "noshow_rate" in metrics
        
        print(f"✓ Evaluate rules: {data['rules_evaluated']} rules, {len(data['alerts'])} alerts triggered")
        print(f"  Metrics: OB={metrics['overbooking_count']}, NS={metrics['noshow_count']}, NS%={metrics['noshow_rate']}%")
    
    def test_get_alert_history(self, auth_headers):
        """Test GET /api/pms/alert-rules/history"""
        response = requests.get(
            f"{BASE_URL}/api/pms/alert-rules/history?limit=20",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "history" in data, "Missing 'history' field"
        assert isinstance(data["history"], list)
        
        # Verify history item structure for rule engine alerts (filter by rule_name presence)
        rule_alerts = [item for item in data["history"] if "rule_name" in item]
        for item in rule_alerts[:5]:
            assert "rule_name" in item
            assert "triggered_at" in item
            assert "metric_value" in item
            assert "action_suggestion" in item
        
        print(f"✓ Alert history: {len(data['history'])} total entries, {len(rule_alerts)} rule engine alerts")


# ─────────────────────────────────────────────────────────
# 4. NO-SHOW PREDICTION TESTS
# ─────────────────────────────────────────────────────────

class TestNoShowPrediction(TestAuth):
    """Tests for GET /api/pms/noshow-prediction"""
    
    def test_prediction_default_7_days(self, auth_headers):
        """Test prediction with default 7 days ahead"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "predictions" in data, "Missing 'predictions' field"
        assert "summary" in data, "Missing 'summary' field"
        assert "historical_rates" in data, "Missing 'historical_rates' field"
        assert "days_ahead" in data, "Missing 'days_ahead' field"
        assert "data_quality" in data, "Missing 'data_quality' field"
        
        print(f"✓ Prediction: {len(data['predictions'])} upcoming bookings analyzed")
    
    def test_prediction_14_days(self, auth_headers):
        """Test prediction with 14 days ahead"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction?days_ahead=14",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["days_ahead"] == 14
        print(f"✓ Prediction (14 days): {len(data['predictions'])} bookings")
    
    def test_prediction_summary_structure(self, auth_headers):
        """Verify summary structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        summary = data["summary"]
        assert "total_upcoming" in summary
        assert "high_risk" in summary
        assert "medium_risk" in summary
        assert "low_risk" in summary
        assert "potential_loss" in summary
        
        # Verify counts add up
        total = summary["high_risk"] + summary["medium_risk"] + summary["low_risk"]
        assert total == summary["total_upcoming"], f"Risk counts don't add up: {total} != {summary['total_upcoming']}"
        
        print(f"✓ Summary: {summary['high_risk']} high, {summary['medium_risk']} medium, {summary['low_risk']} low risk")
    
    def test_prediction_item_structure(self, auth_headers):
        """Verify prediction item structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for pred in data["predictions"][:5]:
            assert "booking_id" in pred
            assert "guest_name" in pred
            assert "channel" in pred
            assert "check_in" in pred
            assert "room_type" in pred
            assert "total_amount" in pred
            assert "risk_score" in pred
            assert "risk_level" in pred
            assert "factors" in pred
            
            # Verify risk_score is 0-100
            assert 0 <= pred["risk_score"] <= 100, f"Invalid risk_score: {pred['risk_score']}"
            
            # Verify risk_level
            assert pred["risk_level"] in ["low", "medium", "high"]
            
            # Verify factors structure
            factors = pred["factors"]
            assert "channel_rate" in factors
            assert "channel_score" in factors
            assert "dow_score" in factors
            assert "amount_score" in factors
        
        print(f"✓ Prediction item structure verified")
    
    def test_prediction_historical_rates(self, auth_headers):
        """Verify historical rates structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        hist = data["historical_rates"]
        assert "by_channel" in hist
        assert "by_day_of_week" in hist
        
        # by_day_of_week should have 7 entries (0-6)
        dow = hist["by_day_of_week"]
        assert isinstance(dow, dict)
        
        print(f"✓ Historical rates: {len(hist['by_channel'])} channels, {len(dow)} days")
    
    def test_prediction_data_quality(self, auth_headers):
        """Verify data quality structure"""
        response = requests.get(
            f"{BASE_URL}/api/pms/noshow-prediction",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        dq = data["data_quality"]
        assert "confidence" in dq
        assert "note" in dq
        assert "historical_bookings" in dq
        assert dq["confidence"] in ["low", "medium", "high"]
        
        print(f"✓ Data quality: {dq['confidence']} ({dq['historical_bookings']} historical bookings)")


# ─────────────────────────────────────────────────────────
# CLEANUP TEST DATA
# ─────────────────────────────────────────────────────────

class TestCleanup(TestAuth):
    """Cleanup TEST_ prefixed rules after tests"""
    
    def test_cleanup_test_rules(self, auth_headers):
        """Delete all TEST_ prefixed rules"""
        response = requests.get(
            f"{BASE_URL}/api/pms/alert-rules",
            headers=auth_headers
        )
        if response.status_code == 200:
            rules = response.json().get("rules", [])
            deleted = 0
            for rule in rules:
                if rule.get("rule_name", "").startswith("TEST_"):
                    del_resp = requests.delete(
                        f"{BASE_URL}/api/pms/alert-rules/{rule['id']}",
                        headers=auth_headers
                    )
                    if del_resp.status_code == 200:
                        deleted += 1
            print(f"✓ Cleanup: Deleted {deleted} TEST_ rules")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
