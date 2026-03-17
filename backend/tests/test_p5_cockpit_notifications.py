"""
P5 Runtime Cockpit, Notifications & Quarantine Tests
=====================================================

Tests:
  1. Notification Event Config (sync, 6 tests)
  2. Notification Events DB logic (mocked, 9 tests)
  3. Quarantine Visibility (mocked, 10 tests)
  4. Cockpit API (httpx, 5 tests)
  5. Notification API (httpx, 4 tests)
  6. Quarantine API (httpx, 3 tests)
Total: 37 tests
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

TEST_TENANT = "test-tenant-p5"
TEST_PROPERTY = "test-prop-p5"


# ══════════════════════════════════════════════════════════════
# 1. NOTIFICATION EVENT CONFIG — SYNC (no DB)
# ══════════════════════════════════════════════════════════════

class TestNotificationEventConfig:

    def test_severity_model(self):
        from domains.channel_manager.notification_events_service import EVENT_CONFIG, EventType, EventSeverity
        assert EVENT_CONFIG[EventType.TENANT_BECAME_READY]["severity"] == EventSeverity.INFO
        assert EVENT_CONFIG[EventType.TENANT_FELL_OUT_OF_READY]["severity"] == EventSeverity.BLOCKER
        assert EVENT_CONFIG[EventType.VERIFY_FAILURE_SPIKE]["severity"] == EventSeverity.CRITICAL
        assert EVENT_CONFIG[EventType.MAPPING_BROKEN_DETECTED]["severity"] == EventSeverity.WARNING

    def test_cooldown_values(self):
        from domains.channel_manager.notification_events_service import EVENT_CONFIG, EventType
        assert EVENT_CONFIG[EventType.TENANT_BECAME_READY]["cooldown_seconds"] == 0
        assert EVENT_CONFIG[EventType.VERIFY_FAILURE_SPIKE]["cooldown_seconds"] == 300
        assert EVENT_CONFIG[EventType.MAPPING_BROKEN_DETECTED]["cooldown_seconds"] == 600

    def test_state_change_flags(self):
        from domains.channel_manager.notification_events_service import EVENT_CONFIG, EventType
        assert EVENT_CONFIG[EventType.TENANT_BECAME_READY]["is_state_change"] is True
        assert EVENT_CONFIG[EventType.MAPPING_BROKEN_DETECTED]["is_state_change"] is False

    def test_config_returns_all_10(self):
        from domains.channel_manager.notification_events_service import get_event_config
        config = get_event_config()
        assert len(config) == 10
        assert config["tenant_fell_out_of_ready"]["severity"] == "blocker"

    def test_all_have_description(self):
        from domains.channel_manager.notification_events_service import EVENT_CONFIG
        for etype, cfg in EVENT_CONFIG.items():
            assert len(cfg.get("description", "")) > 0

    def test_severity_values(self):
        from domains.channel_manager.notification_events_service import EventSeverity
        assert EventSeverity.INFO == "info"
        assert EventSeverity.WARNING == "warning"
        assert EventSeverity.CRITICAL == "critical"
        assert EventSeverity.BLOCKER == "blocker"


# ══════════════════════════════════════════════════════════════
# 2. NOTIFICATION EVENTS DB — MOCKED
# ══════════════════════════════════════════════════════════════

def _mock_db_for_notifications():
    """Create a mock db that supports notification collections."""
    mock_db = MagicMock()
    events_col = MagicMock()
    state_col = MagicMock()

    def get_col(name):
        if name == "notification_events":
            return events_col
        if name == "notification_state":
            return state_col
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=get_col)
    return mock_db, events_col, state_col


class TestNotificationEventsDB:

    @pytest.mark.asyncio
    async def test_emit_basic_event(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        events_col.find_one = AsyncMock(return_value=None)  # no recent event
        events_col.insert_one = AsyncMock()
        state_col.find_one = AsyncMock(return_value=None)

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            evt = await emit_event(TEST_TENANT, EventType.MAPPING_BROKEN_DETECTED, {"broken": 3})
            assert evt is not None
            assert evt["event_type"] == "mapping_broken_detected"
            assert evt["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_cooldown_suppresses(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        events_col.find_one = AsyncMock(return_value={"event_type": "mapping_broken_detected"})
        events_col.insert_one = AsyncMock()

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            evt = await emit_event(TEST_TENANT, EventType.MAPPING_BROKEN_DETECTED)
            assert evt is None  # suppressed

    @pytest.mark.asyncio
    async def test_state_change_dedup(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        state_col.find_one = AsyncMock(return_value={"last_event_type": "hard_fail_cleared"})
        events_col.insert_one = AsyncMock()

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            evt = await emit_event(TEST_TENANT, EventType.HARD_FAIL_CLEARED)
            assert evt is None  # already in this state

    @pytest.mark.asyncio
    async def test_different_state_fires(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        state_col.find_one = AsyncMock(return_value={"last_event_type": "tenant_became_ready"})
        state_col.update_one = AsyncMock()
        events_col.insert_one = AsyncMock()

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            with patch("domains.channel_manager.notification_events_service._dispatch_to_slack", AsyncMock()):
                evt = await emit_event(TEST_TENANT, EventType.TENANT_FELL_OUT_OF_READY)
                assert evt is not None
                assert evt["severity"] == "blocker"

    @pytest.mark.asyncio
    async def test_unknown_event(self):
        from domains.channel_manager.notification_events_service import emit_event
        assert await emit_event(TEST_TENANT, "xyz_nonexistent") is None

    @pytest.mark.asyncio
    async def test_event_history(self):
        from domains.channel_manager.notification_events_service import get_event_history
        mock_db, events_col, _ = _mock_db_for_notifications()

        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.skip = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[
            {"event_type": "hard_fail_cleared", "severity": "info", "timestamp": "2025-01-01T00:00:00"}
        ])
        events_col.find = MagicMock(return_value=cursor)

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            history = await get_event_history(TEST_TENANT)
            assert len(history) == 1
            assert history[0]["event_type"] == "hard_fail_cleared"

    @pytest.mark.asyncio
    async def test_event_summary(self):
        from domains.channel_manager.notification_events_service import get_event_summary
        mock_db, events_col, _ = _mock_db_for_notifications()

        async def mock_agg(*args, **kwargs):
            for doc in [
                {"_id": {"severity": "info", "event_type": "hard_fail_cleared"}, "count": 5, "last_at": "2025-01-01"},
                {"_id": {"severity": "critical", "event_type": "hard_fail_spike"}, "count": 2, "last_at": "2025-01-01"},
            ]:
                yield doc

        events_col.aggregate = MagicMock(return_value=mock_agg())
        events_col.count_documents = AsyncMock(return_value=3)

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            summary = await get_event_summary(TEST_TENANT)
            assert summary["total_events"] == 7
            assert summary["by_severity"]["info"] == 5
            assert summary["by_severity"]["critical"] == 2

    @pytest.mark.asyncio
    async def test_provider_specific_no_crosstalk(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        events_col.find_one = AsyncMock(return_value=None)
        events_col.insert_one = AsyncMock()

        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            e1 = await emit_event(TEST_TENANT, EventType.MAPPING_BROKEN_DETECTED, provider="exely")
            assert e1 is not None
            assert e1["provider"] == "exely"

    @pytest.mark.asyncio
    async def test_emit_with_slack_dispatch(self):
        from domains.channel_manager.notification_events_service import emit_event, EventType
        mock_db, events_col, state_col = _mock_db_for_notifications()
        state_col.find_one = AsyncMock(return_value=None)
        state_col.update_one = AsyncMock()
        events_col.insert_one = AsyncMock()

        mock_dispatch = AsyncMock()
        with patch("domains.channel_manager.notification_events_service.db", mock_db):
            with patch("domains.channel_manager.notification_events_service._dispatch_to_slack", mock_dispatch):
                evt = await emit_event(TEST_TENANT, EventType.TENANT_FELL_OUT_OF_READY)
                assert evt is not None
                mock_dispatch.assert_awaited_once()


# ══════════════════════════════════════════════════════════════
# 3. QUARANTINE VISIBILITY — MOCKED
# ══════════════════════════════════════════════════════════════

def _mock_quarantine_db(quarantined_docs=None):
    mock_db = MagicMock()
    cs_col = MagicMock()
    room_col = MagicMock()
    rate_col = MagicMock()

    def get_col(name):
        if name == "ari_change_sets":
            return cs_col
        if name == "room_mappings":
            return room_col
        if name == "rate_plan_mappings":
            return rate_col
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=get_col)

    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=quarantined_docs or [])
    cs_col.find = MagicMock(return_value=cursor)
    cs_col.count_documents = AsyncMock(return_value=0)

    return mock_db, cs_col, room_col, rate_col


def _make_quarantined(failure_type="unmapped", provider="exely", age_minutes=0):
    now = datetime.now(timezone.utc)
    hf_at = (now - timedelta(minutes=age_minutes)).isoformat()
    return {
        "id": str(uuid.uuid4()), "tenant_id": TEST_TENANT,
        "provider": provider, "room_type_code": f"R_{uuid.uuid4().hex[:4]}",
        "rate_plan_code": "RP1", "status": "hard_fail",
        "hard_fail_reason": "test", "hard_fail_at": hf_at,
        "hard_fail_failures": [{"failure_type": failure_type, "reason": "t", "operator_action": "fix"}],
        "created_at": hf_at,
    }


class TestQuarantineService:

    @pytest.mark.asyncio
    async def test_empty(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        mock_db, *_ = _mock_quarantine_db([])
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert r["total_quarantined"] == 0

    @pytest.mark.asyncio
    async def test_classification(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [
            _make_quarantined("unmapped"), _make_quarantined("unmapped"), _make_quarantined("ambiguous"),
        ]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert r["total_quarantined"] == 3
            assert r["by_classification"]["unmapped"] == 2
            assert r["by_classification"]["ambiguous"] == 1

    @pytest.mark.asyncio
    async def test_age_bucket_fresh(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [_make_quarantined(age_minutes=2), _make_quarantined(age_minutes=2)]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert r["by_age_bucket"]["lt_5min"] == 2

    @pytest.mark.asyncio
    async def test_age_buckets_mixed(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [
            _make_quarantined(age_minutes=1),
            _make_quarantined(age_minutes=15),
            _make_quarantined(age_minutes=60),
            _make_quarantined(age_minutes=180),
        ]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert r["by_age_bucket"]["lt_5min"] == 1
            assert r["by_age_bucket"]["5_30min"] == 1
            assert r["by_age_bucket"]["30_120min"] == 1
            assert r["by_age_bucket"]["gt_2h"] == 1

    @pytest.mark.asyncio
    async def test_provider_breakdown(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [
            _make_quarantined(provider="exely"), _make_quarantined(provider="exely"),
            _make_quarantined(provider="hotelrunner"),
        ]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert r["by_provider"]["exely"] == 2
            assert r["by_provider"]["hotelrunner"] == 1

    @pytest.mark.asyncio
    async def test_safe_release_no_mapping(self):
        from domains.channel_manager.quarantine_service import check_safe_release
        mock_db, cs_col, room_col, rate_col = _mock_quarantine_db()
        room_col.find_one = AsyncMock(return_value=None)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await check_safe_release(TEST_TENANT, "NONEXISTENT")
            assert r["safe_to_release"] is False
            assert len(r["issues"]) > 0

    @pytest.mark.asyncio
    async def test_safe_release_valid(self):
        from domains.channel_manager.quarantine_service import check_safe_release
        mock_db, cs_col, room_col, rate_col = _mock_quarantine_db()
        room_col.find_one = AsyncMock(return_value={
            "pms_room_type_id": "R1", "is_active": True, "provider_room_code": "VALID",
        })
        cs_col.count_documents = AsyncMock(return_value=0)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await check_safe_release(TEST_TENANT, "VALID", provider="exely")
            assert r["safe_to_release"] is True

    @pytest.mark.asyncio
    async def test_stale_detection(self):
        from domains.channel_manager.quarantine_service import check_safe_release
        mock_db, cs_col, room_col, rate_col = _mock_quarantine_db()
        room_col.find_one = AsyncMock(return_value={
            "pms_room_type_id": "R1", "is_active": True,
        })
        cs_col.count_documents = AsyncMock(return_value=2)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await check_safe_release(TEST_TENANT, "STALE", provider="exely")
            assert r["stale_count"] == 2

    @pytest.mark.asyncio
    async def test_sorted_by_age(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [_make_quarantined(age_minutes=1), _make_quarantined(age_minutes=100)]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            items = r["items"]
            assert len(items) == 2
            assert items[0]["age_minutes"] >= items[1]["age_minutes"]

    @pytest.mark.asyncio
    async def test_items_limited(self):
        from domains.channel_manager.quarantine_service import get_quarantine_overview
        docs = [_make_quarantined(age_minutes=i) for i in range(60)]
        mock_db, *_ = _mock_quarantine_db(docs)
        with patch("domains.channel_manager.quarantine_service.db", mock_db):
            r = await get_quarantine_overview(TEST_TENANT)
            assert len(r["items"]) <= 50


# ══════════════════════════════════════════════════════════════
# 4. ALL API ENDPOINT TESTS — Single httpx session
# ══════════════════════════════════════════════════════════════

class TestAllAPIs:
    """All API tests in a single httpx session to avoid event loop issues."""

    @pytest.mark.asyncio
    async def test_all_api_endpoints(self):
        from httpx import AsyncClient, ASGITransport
        from server import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            login = await c.post("/api/auth/login", json={"email": "demo@hotel.com", "password": "demo123"})
            assert login.status_code == 200
            token = login.json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}

            # ── Cockpit: all sections ──
            res = await c.get("/api/lockdown/runtime/cockpit", headers=h)
            assert res.status_code == 200
            data = res.json()
            for s in ["health", "flow", "reliability", "drift_heal", "hard_fail", "quarantine"]:
                assert s in data, f"Missing cockpit section: {s}"

            # ── Cockpit: health keys ──
            for k in ["is_production_ready", "active_incidents", "quarantine_count", "verify_success_pct", "push_loop_status"]:
                assert k in data["health"], f"Missing health key: {k}"

            # ── Cockpit: flow keys ──
            for k in ["queued", "coalesced", "emitted", "dropped", "hard_fail_blocked", "cycle_count"]:
                assert k in data["flow"], f"Missing flow key: {k}"

            # ── Cockpit: reliability keys ──
            for k in ["verify_success_ratio", "verify_success_count", "verify_fail_count", "dead_letters"]:
                assert k in data["reliability"], f"Missing reliability key: {k}"

            # ── Cockpit: quarantine keys ──
            for k in ["total_quarantined", "by_classification", "by_age_bucket", "by_provider"]:
                assert k in data["quarantine"], f"Missing quarantine key: {k}"

            # ── Notification: config ──
            res = await c.get("/api/lockdown/notifications/config", headers=h)
            assert res.status_code == 200
            assert "tenant_became_ready" in res.json()["event_types"]
            assert "tenant_fell_out_of_ready" in res.json()["event_types"]

            # ── Notification: evaluate ──
            res = await c.post("/api/lockdown/notifications/evaluate", headers=h)
            assert res.status_code == 200
            assert "is_ready" in res.json()
            assert "events_emitted" in res.json()

            # ── Notification: events list ──
            res = await c.get("/api/lockdown/notifications/events", headers=h)
            assert res.status_code == 200
            assert "events" in res.json()

            # ── Notification: summary ──
            res = await c.get("/api/lockdown/notifications/summary", headers=h)
            assert res.status_code == 200
            assert "total_events" in res.json()
            assert "by_severity" in res.json()

            # ── Quarantine: overview ──
            res = await c.get("/api/lockdown/runtime/quarantine/overview", headers=h)
            assert res.status_code == 200
            assert "total_quarantined" in res.json()

            # ── Quarantine: check-release (blocked) ──
            res = await c.post(
                "/api/lockdown/runtime/quarantine/check-release",
                json={"room_type_code": "NONEXISTENT"},
                headers=h,
            )
            assert res.status_code == 200
            assert res.json()["safe_to_release"] is False
            assert "checks" in res.json()

            # ── Quarantine: safe-release (blocked by guard) ──
            res = await c.post(
                "/api/lockdown/runtime/quarantine/safe-release",
                json={"room_type_code": "NONEXISTENT"},
                headers=h,
            )
            assert res.status_code == 200
            assert res.json()["released"] is False
            assert "guard" in res.json()
