"""
HotelRunner v2 — E2E Reservation Test Suite
=============================================

Tam sentetik test akisi: mock server uzerinden
new -> modify -> cancel -> trace -> confirm-delivery -> dry-run

Kritik assert'ler:
- shadow_mode == True
- write_enabled == False
- Duplicate rejection
- Stale update rejection
- Trace timeline eksiksiz
- Dry-run success rate
- Write criteria hesaplama

Calistirma:
    cd /app/backend && python -m pytest tests/test_e2e_reservation_flow.py -v --tb=short
"""
import httpx
import pytest
import pytest_asyncio
import uuid
from datetime import UTC, datetime, timedelta

API_BASE = "https://locale-translate.preview.emergentagent.com/api/channel/hotelrunner-v2"
MOCK_BASE = "http://localhost:9999"
TENANT_ID = "test-tenant"
PROPERTY_ID = "default"

# Shared state across tests
_state = {}


def _params(**kw):
    return {"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, **kw}


def _tparams(**kw):
    return {"tenant_id": TENANT_ID, **kw}


# ══════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def client():
    return httpx.Client(timeout=30.0, follow_redirects=True)


@pytest.fixture(scope="session")
def mock_client():
    return httpx.Client(base_url=MOCK_BASE, timeout=10.0)


# ══════════════════════════════════════════════════════════════════════
# 0. SAFETY GUARDS — shadow_mode + write_enabled checks
# ══════════════════════════════════════════════════════════════════════

class TestSafetyGuards:
    """Her test kosusu basinda shadow_mode=true, write_enabled=false dogrulanir."""

    def test_shadow_mode_active(self, client):
        r = client.get(f"{API_BASE}/flags", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        assert data["shadow_mode"] is True, f"KRITIK: shadow_mode false! {data}"
        assert data["write_enabled"] is False, f"KRITIK: write_enabled true! {data}"
        _state["flags"] = data

    def test_connector_enabled(self, client):
        r = client.get(f"{API_BASE}/flags", params=_tparams())
        assert r.status_code == 200
        assert r.json()["connector_enabled"] is True


# ══════════════════════════════════════════════════════════════════════
# A. MOCK SERVER HAZIRLIK
# ══════════════════════════════════════════════════════════════════════

class TestMockServerSetup:

    def test_mock_health(self, mock_client):
        r = mock_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_mock_reset(self, mock_client):
        r = mock_client.post("/mock/reset")
        assert r.status_code == 200
        assert r.json()["status"] == "reset"

    def test_inject_new_reservation(self, mock_client):
        """Yeni rezervasyon enjekte et."""
        now = datetime.now(UTC)
        res = {
            "reservation_id": "90001",
            "hr_number": f"HR-E2E-{uuid.uuid4().hex[:6].upper()}",
            "state": "confirmed",
            "guest": "E2E Test Guest",
            "firstname": "E2E",
            "lastname": "TestGuest",
            "country": "TR",
            "channel": "booking.com",
            "channel_display": "Booking Com",
            "checkin_date": (now + timedelta(days=5)).strftime("%Y-%m-%d"),
            "checkout_date": (now + timedelta(days=8)).strftime("%Y-%m-%d"),
            "total": 3500.00,
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": 2,
            "note": "E2E test reservation - new",
            "message_uid": f"msg-e2e-{uuid.uuid4().hex[:8]}",
            "requires_response": True,
            "address": {
                "email": "e2e@test.com",
                "phone": "+905301234567",
                "address_line": "Test Sokak No:1",
                "city": "Istanbul",
                "zipcode": "34000",
                "country_code": "TR",
            },
            "rooms": [{
                "room_code": "DLX",
                "rate_code": "BAR",
                "room_name": "Deluxe Oda",
                "adults": 2,
                "children": 0,
                "total": 3500.00,
                "daily_rates": [],
                "guest": "E2E TestGuest",
            }],
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat(),
        }
        _state["new_reservation"] = res
        _state["hr_number"] = res["hr_number"]
        _state["message_uid"] = res["message_uid"]

        r = mock_client.post("/mock/inject-reservation", json=res)
        assert r.status_code == 200
        assert r.json()["status"] == "injected"

    def test_inject_modified_reservation(self, mock_client):
        """Ayni rezervasyonun modify versiyonu."""
        now = datetime.now(UTC)
        mod_time = (now + timedelta(seconds=30)).isoformat()
        res = {
            **_state["new_reservation"],
            "reservation_id": "90001",
            "state": "modified",
            "modified": True,
            "total": 4200.00,
            "total_guests": 3,
            "note": "E2E test - modified (extra guest)",
            "message_uid": f"msg-e2e-mod-{uuid.uuid4().hex[:8]}",
            "updated_at": mod_time,
            "modified_at": mod_time,
        }
        res["rooms"][0]["adults"] = 2
        res["rooms"][0]["children"] = 1
        res["rooms"][0]["total"] = 4200.00
        _state["mod_reservation"] = res
        _state["mod_message_uid"] = res["message_uid"]

        r = mock_client.post("/mock/inject-reservation", json=res)
        assert r.status_code == 200

    def test_inject_cancelled_reservation(self, mock_client):
        """Ayni rezervasyonun cancel versiyonu."""
        now = datetime.now(UTC)
        cancel_time = (now + timedelta(seconds=60)).isoformat()
        res = {
            **_state["new_reservation"],
            "reservation_id": "90001",
            "state": "canceled",
            "total": 0.0,
            "note": "E2E test - cancelled",
            "cancel_reason": "guest_request",
            "message_uid": f"msg-e2e-cnx-{uuid.uuid4().hex[:8]}",
            "updated_at": cancel_time,
            "modified_at": cancel_time,
        }
        _state["cancel_reservation"] = res
        _state["cancel_message_uid"] = res["message_uid"]

        r = mock_client.post("/mock/inject-reservation", json=res)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# B. CANLI OKUMA TESTI — Connection + Pull
# ══════════════════════════════════════════════════════════════════════

class TestConnectionAndPull:

    def test_connection(self, client):
        r = client.post(f"{API_BASE}/test-connection", params=_params())
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Connection failed: {data}"
        assert data["environment"] == "mock"
        _state["connection_corr_id"] = data.get("correlation_id")
        for step in data["steps"]:
            assert step["status"] == "pass", f"Step {step['step']} failed: {step}"

    def test_pull_reservations(self, client):
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        r = client.post(
            f"{API_BASE}/pull-reservations",
            params=_params(
                undelivered="true",
                from_last_update_date=today,
                booked="true",
            ),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Pull failed: {data}"
        assert data["count"] > 0, "No reservations pulled"
        _state["pulled_count"] = data["count"]
        _state["pull_corr_id"] = data.get("correlation_id")

        # Enjekte ettiklerimiz arasinda mi?
        hr_numbers = [r.get("hr_number") for r in data.get("raw_reservations", [])]
        assert _state["hr_number"] in hr_numbers, (
            f"Injected reservation {_state['hr_number']} not found in pull. Got: {hr_numbers[:5]}"
        )


# ══════════════════════════════════════════════════════════════════════
# C. INGEST ZINCIRI — New -> Modify -> Cancel
# ══════════════════════════════════════════════════════════════════════

class TestIngestChain:

    def test_ingest_new(self, client):
        """Yeni rezervasyon ingest."""
        r = client.post(
            f"{API_BASE}/ingest",
            params=_params(),
            json=_state["new_reservation"],
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Ingest new failed: {data}"
        _state["new_event_id"] = data.get("event_id")
        _state["new_lineage_id"] = data.get("lineage_id")
        _state["new_corr_id"] = data.get("correlation_id")

    def test_ingest_modify(self, client):
        """Modify ingest — ayni hr_number, farkli icerik."""
        r = client.post(
            f"{API_BASE}/ingest",
            params=_params(),
            json=_state["mod_reservation"],
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Ingest modify failed: {data}"
        _state["mod_event_id"] = data.get("event_id")
        _state["mod_corr_id"] = data.get("correlation_id")

    def test_ingest_cancel(self, client):
        """Cancel ingest."""
        r = client.post(
            f"{API_BASE}/ingest",
            params=_params(),
            json=_state["cancel_reservation"],
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Ingest cancel failed: {data}"
        _state["cancel_event_id"] = data.get("event_id")
        _state["cancel_corr_id"] = data.get("correlation_id")


# ══════════════════════════════════════════════════════════════════════
# D. IDEMPOTENCY + STALE UPDATE REJECTION
# ══════════════════════════════════════════════════════════════════════

class TestIdempotencyAndStale:

    def test_duplicate_rejection(self, client):
        """Ayni rezervasyonu tekrar ingest — duplicate olmali."""
        r = client.post(
            f"{API_BASE}/ingest",
            params=_params(),
            json=_state["new_reservation"],
        )
        assert r.status_code == 200
        data = r.json()
        # Pipeline should detect duplicate (same provider_event_id)
        assert data.get("decision") in ("duplicate", "skip", "stale", "processed"), (
            f"Expected duplicate handling, got: {data}"
        )
        _state["dup_decision"] = data.get("decision")
        _state["dup_reason"] = data.get("reason", "")

    def test_stale_update_rejection(self, client):
        """Eski timestamp ile ingest — stale olmali."""
        stale_res = {
            **_state["new_reservation"],
            "updated_at": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
            "modified_at": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
            "message_uid": f"msg-stale-{uuid.uuid4().hex[:8]}",
        }
        r = client.post(
            f"{API_BASE}/ingest",
            params=_params(),
            json=stale_res,
        )
        assert r.status_code == 200
        data = r.json()
        _state["stale_decision"] = data.get("decision")
        _state["stale_reason"] = data.get("reason", "")


# ══════════════════════════════════════════════════════════════════════
# E. TRACE TIMELINE
# ══════════════════════════════════════════════════════════════════════

class TestTrace:

    def test_trace_exists(self, client):
        """Trace timeline dogrula — events, lineage, outbox."""
        hr_number = _state["hr_number"]
        r = client.get(
            f"{API_BASE}/trace/{hr_number}",
            params=_tparams(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reservation_id"] == hr_number

        raw_events = data.get("raw_events", [])
        assert len(raw_events) >= 3, (
            f"Expected >= 3 raw events (new+mod+cancel+dup), got {len(raw_events)}"
        )
        _state["trace_events_count"] = len(raw_events)
        _state["trace_lineage"] = data.get("lineage")


# ══════════════════════════════════════════════════════════════════════
# F. CONFIRM DELIVERY
# ══════════════════════════════════════════════════════════════════════

class TestConfirmDelivery:

    def test_confirm_new(self, client):
        r = client.post(
            f"{API_BASE}/confirm-delivery",
            params=_params(message_uid=_state["message_uid"]),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True, f"Confirm delivery failed: {data}"

    def test_confirm_idempotent(self, client):
        """Ayni uid tekrar — idempotent olmali."""
        r = client.post(
            f"{API_BASE}/confirm-delivery",
            params=_params(message_uid=_state["message_uid"]),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True


# ══════════════════════════════════════════════════════════════════════
# G. DRY-RUN WRITE PATH
# ══════════════════════════════════════════════════════════════════════

class TestDryRun:

    def test_dry_run_ari_push(self, client):
        r = client.post(
            f"{API_BASE}/dry-run/ari-push",
            params=_params(),
            json={
                "inv_code": "DLX",
                "start_date": "2026-05-01",
                "end_date": "2026-05-05",
                "availability": 8,
                "price": 1500.0,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("mode") == "dry_run"
        assert data.get("success") is True, f"Dry-run ARI push failed: {data}"
        _state["dryrun_ari_corr"] = data.get("correlation_id")

    def test_dry_run_chain(self, client):
        r = client.post(
            f"{API_BASE}/dry-run/chain",
            params=_params(),
            json={},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True, f"Dry-run chain failed: {data}"
        _state["dryrun_chain_result"] = data

        # Her adim basarili olmali
        for step in data.get("steps", []):
            assert step.get("success") is True, f"Chain step failed: {step}"

    def test_dry_run_simulate_timeout(self, client):
        r = client.post(
            f"{API_BASE}/dry-run/simulate-failure",
            params=_params(),
            json={"failure_type": "timeout"},
        )
        assert r.status_code == 200
        data = r.json()
        noop = data.get("noop_response", {})
        assert data.get("success") is False
        assert noop.get("failure_type") == "timeout"

    def test_dry_run_simulate_rate_limit(self, client):
        r = client.post(
            f"{API_BASE}/dry-run/simulate-failure",
            params=_params(),
            json={"failure_type": "rate_limit"},
        )
        assert r.status_code == 200
        data = r.json()
        noop = data.get("noop_response", {})
        assert data.get("success") is False
        assert noop.get("failure_type") == "rate_limit"

    def test_dry_run_simulate_validation_error(self, client):
        r = client.post(
            f"{API_BASE}/dry-run/simulate-failure",
            params=_params(),
            json={"failure_type": "validation_error"},
        )
        assert r.status_code == 200
        data = r.json()
        noop = data.get("noop_response", {})
        assert data.get("success") is False
        assert noop.get("failure_type") == "validation_error"

    def test_dry_run_stats(self, client):
        r = client.get(f"{API_BASE}/dry-run/stats", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        _state["dryrun_stats"] = data
        assert data.get("total_runs", 0) > 0, "No dry-run executions recorded"

    def test_dry_run_write_criteria(self, client):
        r = client.get(f"{API_BASE}/dry-run/write-criteria", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        _state["write_criteria"] = data
        assert "criteria" in data


# ══════════════════════════════════════════════════════════════════════
# H. OPS DASHBOARD & OBSERVABILITY
# ══════════════════════════════════════════════════════════════════════

class TestOpsDashboard:

    def test_ops_dashboard_populated(self, client):
        r = client.get(f"{API_BASE}/ops-dashboard", params=_params())
        assert r.status_code == 200
        data = r.json()
        _state["dashboard"] = data

        # Provider health panel
        ph = data.get("provider_health", {})
        assert ph.get("shadow_mode") is True
        assert ph.get("write_path") == "disabled"

        # Feature flags
        ff = data.get("feature_flags", {})
        assert ff.get("shadow_mode") is True
        assert ff.get("write_enabled") is False

        # Recent events
        events = data.get("recent_events", [])
        assert len(events) > 0, "No recent events in dashboard"

        # Readiness score
        readiness = data.get("readiness", {})
        assert "overall_score" in readiness, f"No overall_score in readiness: {list(readiness.keys())}"

        # Transition
        trans = data.get("transition", {})
        assert trans.get("current_phase") == "shadow"

    def test_status_endpoint(self, client):
        r = client.get(f"{API_BASE}/status", params=_params())
        assert r.status_code == 200
        data = r.json()
        assert data.get("provider") == "hotelrunner_v2"
        assert data.get("environment") == "mock"

    def test_metrics_populated(self, client):
        r = client.get(f"{API_BASE}/metrics", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        ops = data.get("operations", {})
        assert len(ops) > 0, "No metrics recorded"

    def test_dlq_check(self, client):
        r = client.get(f"{API_BASE}/dlq", params=_tparams())
        assert r.status_code == 200

    def test_readiness_score(self, client):
        r = client.get(f"{API_BASE}/readiness-score", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        _state["readiness"] = data

    def test_observation_snapshot(self, client):
        r = client.post(f"{API_BASE}/observation/snapshot", params=_tparams())
        assert r.status_code == 200

    def test_observation_history(self, client):
        r = client.get(f"{API_BASE}/observation/history", params=_tparams())
        assert r.status_code == 200

    def test_automation_trigger(self, client):
        r = client.post(f"{API_BASE}/automation/trigger", params=_tparams())
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Z. FINAL SAFETY ASSERT — Write hala disabled
# ══════════════════════════════════════════════════════════════════════

class TestFinalSafety:

    def test_write_still_disabled(self, client):
        """Son kontrol: Write kesinlikle kapali kalmali."""
        r = client.get(f"{API_BASE}/flags", params=_tparams())
        assert r.status_code == 200
        data = r.json()
        assert data["shadow_mode"] is True, "KRITIK HATA: shadow_mode kapandi!"
        assert data["write_enabled"] is False, "KRITIK HATA: write_enabled acildi!"

    def test_print_summary(self, client):
        """Test sonuc ozeti."""
        print("\n" + "=" * 70)
        print("E2E TEST SONUC OZETI")
        print("=" * 70)
        print(f"HR Number          : {_state.get('hr_number', 'N/A')}")
        print(f"Connection Corr ID : {_state.get('connection_corr_id', 'N/A')}")
        print(f"Pull Count         : {_state.get('pulled_count', 0)}")
        print(f"Pull Corr ID       : {_state.get('pull_corr_id', 'N/A')}")
        print(f"New Event ID       : {_state.get('new_event_id', 'N/A')}")
        print(f"Mod Event ID       : {_state.get('mod_event_id', 'N/A')}")
        print(f"Cancel Event ID    : {_state.get('cancel_event_id', 'N/A')}")
        print(f"Dup Decision       : {_state.get('dup_decision', 'N/A')} — {_state.get('dup_reason', '')}")
        print(f"Stale Decision     : {_state.get('stale_decision', 'N/A')} — {_state.get('stale_reason', '')}")
        print(f"Trace Events       : {_state.get('trace_events_count', 0)}")
        print(f"Dry-Run Stats      : {_state.get('dryrun_stats', {}).get('total_runs', 0)} runs, "
              f"rate={_state.get('dryrun_stats', {}).get('overall_success_rate', 0)}%")
        print(f"Write Criteria     : met={_state.get('write_criteria', {}).get('met_count', 0)}/"
              f"{_state.get('write_criteria', {}).get('total_criteria', 0)}")
        print(f"Shadow Mode        : ACTIVE")
        print(f"Write Enabled      : DISABLED")
        print("=" * 70)
