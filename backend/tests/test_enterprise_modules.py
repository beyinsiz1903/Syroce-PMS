"""
API-level tests for the 3 new enterprise modules:
1. Revenue Management Engine
2. Real-Time Operational Event System
3. Guest Journey Layer

Uses httpx to test against the running backend.
"""
import pytest
import httpx
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "")

pytestmark = pytest.mark.skipif(not API_URL, reason="REACT_APP_BACKEND_URL not set")

@pytest.fixture(scope="session")
def auth_headers():
    """Get auth token once for all tests."""
    resp = httpx.post(f"{API_URL}/api/auth/login", json={"email": "demo@hotel.com", "password": "demo123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ════════════════════════════════════════════════
# 1. REVENUE MANAGEMENT ENGINE API TESTS
# ════════════════════════════════════════════════

def test_revenue_dashboard(auth_headers):
    """GET /api/revenue-engine/dashboard should return comprehensive data."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "period_30d" in data
    assert "daily_trend" in data
    assert "opportunities" in data
    assert "adr" in data["period_30d"]
    assert "revpar" in data["period_30d"]


def test_occupancy_forecast(auth_headers):
    """GET /api/revenue-engine/occupancy-forecast should return forecast."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/occupancy-forecast?days=3", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "forecast" in data
    assert len(data["forecast"]) == 3
    for d in data["forecast"]:
        assert "date" in d
        assert "occupancy_pct" in d
        assert "demand_level" in d


def test_rate_suggestions(auth_headers):
    """GET /api/revenue-engine/rate-suggestions should return 7 days."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/rate-suggestions?days=7", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 7
    for s in data["suggestions"]:
        assert "ideal_adr" in s
        assert "recommendation" in s
        assert s["recommendation"] in ("increase", "decrease", "maintain")


def test_yield_recommendations(auth_headers):
    """GET /api/revenue-engine/yield-recommendations should return yield rules."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/yield-recommendations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    for rec in data["recommendations"]:
        assert "stop_sell" in rec
        assert "min_stay" in rec
        assert "cta" in rec
        assert "ctd" in rec


def test_booking_pace(auth_headers):
    """GET /api/revenue-engine/booking-pace should return pace analysis."""
    from datetime import date
    today = date.today().isoformat()
    resp = httpx.get(f"{API_URL}/api/revenue-engine/booking-pace?target_date={today}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "pace_index" in data
    assert "pace_status" in data
    assert data["pace_status"] in ("ahead", "behind", "on_track")


def test_ideal_adr(auth_headers):
    """GET /api/revenue-engine/ideal-adr should return ADR calculation."""
    from datetime import date
    today = date.today().isoformat()
    resp = httpx.get(f"{API_URL}/api/revenue-engine/ideal-adr?target_date={today}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "ideal_adr" in data
    assert "recommendation" in data
    assert "demand_multiplier" in data


def test_lead_time_analysis(auth_headers):
    """GET /api/revenue-engine/lead-time-analysis should return distribution."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/lead-time-analysis?days_back=30", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "distribution" in data
    assert "average_lead_time" in data


def test_channel_performance(auth_headers):
    """GET /api/revenue-engine/channel-performance should return channel data."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/channel-performance?days_back=30", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "channels" in data
    assert "total_bookings" in data
    assert "direct_booking_share" in data


def test_apply_rate(auth_headers):
    """POST /api/revenue-engine/apply-rate should apply rate override."""
    from datetime import date, timedelta
    target = (date.today() + timedelta(days=5)).isoformat()
    resp = httpx.post(f"{API_URL}/api/revenue-engine/apply-rate",
                      json={"target_date": target, "new_rate": 250.0}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    assert data["new_rate"] == 250.0


def test_rate_suggestions_max_limit(auth_headers):
    """Should reject days > 30."""
    resp = httpx.get(f"{API_URL}/api/revenue-engine/rate-suggestions?days=31", headers=auth_headers)
    assert resp.status_code == 400


# ════════════════════════════════════════════════
# 2. OPERATIONAL EVENT SYSTEM API TESTS
# ════════════════════════════════════════════════

def test_publish_event(auth_headers):
    """POST /api/event-system/publish should create an event."""
    resp = httpx.post(f"{API_URL}/api/event-system/publish",
                      json={"event_type": "check_in_created", "payload": {"booking_id": "test-b1", "guest": "Test Guest"}},
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    assert "event_id" in data


def test_publish_unknown_event(auth_headers):
    """Should reject unknown event types."""
    resp = httpx.post(f"{API_URL}/api/event-system/publish",
                      json={"event_type": "totally_unknown", "payload": {}}, headers=auth_headers)
    assert resp.status_code == 400


def test_live_feed(auth_headers):
    """GET /api/event-system/live-feed should return events."""
    resp = httpx.get(f"{API_URL}/api/event-system/live-feed?limit=10", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "count" in data


def test_unread_count(auth_headers):
    """GET /api/event-system/unread-count should return count."""
    resp = httpx.get(f"{API_URL}/api/event-system/unread-count", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_unread" in data
    assert "critical" in data


def test_mark_read(auth_headers):
    """POST /api/event-system/mark-read should mark events read."""
    # First publish an event
    pub = httpx.post(f"{API_URL}/api/event-system/publish",
                     json={"event_type": "room_ready", "payload": {"room": "101"}}, headers=auth_headers)
    eid = pub.json()["event_id"]
    # Mark read
    resp = httpx.post(f"{API_URL}/api/event-system/mark-read",
                      json={"event_ids": [eid]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["success"]


def test_acknowledge_event(auth_headers):
    """POST /api/event-system/acknowledge should acknowledge event."""
    pub = httpx.post(f"{API_URL}/api/event-system/publish",
                     json={"event_type": "audit_exception", "payload": {"issue": "balance"}}, headers=auth_headers)
    eid = pub.json()["event_id"]
    resp = httpx.post(f"{API_URL}/api/event-system/acknowledge",
                      json={"event_id": eid, "note": "Reviewed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["success"]


def test_event_stats(auth_headers):
    """GET /api/event-system/stats should return statistics."""
    resp = httpx.get(f"{API_URL}/api/event-system/stats?hours=24", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_events" in data
    assert "by_type" in data
    assert "by_priority" in data


def test_front_desk_queue(auth_headers):
    """GET /api/event-system/front-desk-queue should return queue."""
    resp = httpx.get(f"{API_URL}/api/event-system/front-desk-queue", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "pending_arrivals" in data
    assert "arrivals" in data


def test_housekeeping_board(auth_headers):
    """GET /api/event-system/housekeeping-board should return board."""
    resp = httpx.get(f"{API_URL}/api/event-system/housekeeping-board", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data


# ════════════════════════════════════════════════
# 3. GUEST JOURNEY LAYER API TESTS
# ════════════════════════════════════════════════

def test_satisfaction_dashboard(auth_headers):
    """GET /api/guest-journey/satisfaction-dashboard should return data."""
    resp = httpx.get(f"{API_URL}/api/guest-journey/satisfaction-dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "open_requests" in data
    assert "avg_resolution_minutes" in data
    assert "reputation" in data


def test_guest_requests_list(auth_headers):
    """GET /api/guest-journey/guest-requests should return list."""
    resp = httpx.get(f"{API_URL}/api/guest-journey/guest-requests", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "requests" in data
    assert "count" in data


def test_message_templates(auth_headers):
    """GET /api/guest-journey/message-templates should return templates."""
    resp = httpx.get(f"{API_URL}/api/guest-journey/message-templates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 5
    triggers = [t["trigger"] for t in data["templates"]]
    assert "pre_arrival_3d" in triggers


def test_reputation_summary(auth_headers):
    """GET /api/guest-journey/reputation-summary should return summary."""
    resp = httpx.get(f"{API_URL}/api/guest-journey/reputation-summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_reviews" in data
    assert "average_rating" in data


def test_online_checkin_invalid_booking(auth_headers):
    """POST /api/guest-journey/online-checkin with invalid booking should fail."""
    resp = httpx.post(f"{API_URL}/api/guest-journey/online-checkin",
                      json={"booking_id": "nonexistent", "arrival_time": "14:00"},
                      headers=auth_headers)
    assert resp.status_code == 400


def test_guest_request_invalid_type(auth_headers):
    """POST /api/guest-journey/guest-request with invalid type should fail."""
    resp = httpx.post(f"{API_URL}/api/guest-journey/guest-request",
                      json={"booking_id": "test", "request_type": "invalid_xyz", "description": "test"},
                      headers=auth_headers)
    assert resp.status_code == 400


def test_send_message_invalid_channel(auth_headers):
    """POST /api/guest-journey/send-message with invalid channel should fail."""
    resp = httpx.post(f"{API_URL}/api/guest-journey/send-message",
                      json={"booking_id": "test", "channel": "telegram", "message_type": "test", "content": "test"},
                      headers=auth_headers)
    assert resp.status_code == 400


def test_submit_review_invalid_rating(auth_headers):
    """POST /api/guest-journey/submit-review with rating > 5 should fail."""
    resp = httpx.post(f"{API_URL}/api/guest-journey/submit-review",
                      json={"booking_id": "test", "rating": 6}, headers=auth_headers)
    assert resp.status_code == 400
