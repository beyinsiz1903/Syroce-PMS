"""Task #92 — System Health card for room-service live connections.

These tests pin down three things:

  1. ``RoomServiceOrderStream`` exposes correct aggregate gauges
     (``total_room_count``, ``total_connection_count``, staff variants)
     and a sliding 1-hour event-delivery counter that prunes expired
     entries on read.
  2. ``emit_order_event`` records one event-delivery tick per locally
     delivered recipient — mirroring how operators read the gauge
     ("how many guest screens were updated in the last hour").
  3. The new ``/normalized/room-service`` endpoint and the
     ``normalized_overview`` aggregator surface the gauge as a
     subsystem entry whose status stays "healthy" with no traffic.
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _FakeWebSocket:
    """Mirrors the helper in test_room_service_realtime — kept local
    so this file is self-contained and doesn't accidentally import a
    fixture that may move between the two suites.
    """

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


# ── Aggregate gauges ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_total_room_count_distinct_per_tenant_booking():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    assert stream.total_room_count() == 0
    assert stream.total_connection_count() == 0

    a = _FakeWebSocket()
    b = _FakeWebSocket()
    c = _FakeWebSocket()
    await stream.connect(a, "tenant1", "bookA")
    await stream.connect(b, "tenant1", "bookA")  # same room, second socket
    await stream.connect(c, "tenant2", "bookA")  # different tenant

    assert stream.total_room_count() == 2, (
        "two distinct (tenant, booking) rooms regardless of socket count"
    )
    assert stream.total_connection_count() == 3

    # Disconnecting the only socket on a room must reduce both gauges.
    await stream.disconnect(c, "tenant2", "bookA")
    assert stream.total_room_count() == 1
    assert stream.total_connection_count() == 2


@pytest.mark.asyncio
async def test_staff_aggregate_gauges():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    s1 = _FakeWebSocket()
    s2 = _FakeWebSocket()
    s3 = _FakeWebSocket()
    await stream.connect_staff(s1, "tenant1")
    await stream.connect_staff(s2, "tenant1")
    await stream.connect_staff(s3, "tenant2")

    assert stream.total_staff_room_count() == 2
    assert stream.total_staff_connection_count() == 3


# ── Sliding-window event counter ─────────────────────────────────


def test_record_event_delivery_and_recent_count_window(monkeypatch):
    from domains.guest.experience_router import room_service_realtime as rsr

    stream = rsr.RoomServiceOrderStream()

    # Freeze the clock so we can drop entries at deterministic offsets.
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(rsr.time, "monotonic", lambda: fake_now["t"])

    # Two deliveries "now" → both inside the 1h window.
    stream.record_event_delivery(2)
    assert stream.recent_event_count(3600) == 2

    # Move the clock forward 30 minutes and add one more.
    fake_now["t"] += 30 * 60
    stream.record_event_delivery(1)
    assert stream.recent_event_count(3600) == 3

    # Move forward to 1h05m — the original two should now have aged out;
    # only the one recorded at t+30m is still within the trailing hour.
    fake_now["t"] += 35 * 60
    assert stream.recent_event_count(3600) == 1


def test_record_event_delivery_zero_or_negative_is_noop():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    stream.record_event_delivery(0)
    stream.record_event_delivery(-5)
    assert stream.recent_event_count(3600) == 0


@pytest.mark.asyncio
async def test_emit_order_event_records_one_tick_per_recipient():
    from domains.guest.experience_router import room_service_realtime as rsr

    # Fresh stream so we don't pick up timestamps from neighbouring tests
    # in the suite; the module-level singleton is shared global state.
    fresh = rsr.RoomServiceOrderStream()
    rsr.order_stream = fresh  # type: ignore[assignment]
    try:
        ws_a = _FakeWebSocket()
        ws_b = _FakeWebSocket()
        await fresh.connect(ws_a, "tenantE", "bookingE")
        await fresh.connect(ws_b, "tenantE", "bookingE")

        delivered = await rsr.emit_order_event(
            {
                "id": "ord-1",
                "tenant_id": "tenantE",
                "booking_id": "bookingE",
                "status": "preparing",
            },
            event_type="status_changed",
        )
        assert delivered == 2
        # One tick per recipient — mirrors the "guest screens updated" gauge.
        assert fresh.recent_event_count(3600) == 2
    finally:
        # Restore the module singleton so unrelated tests don't see a
        # surprise empty stream.
        importlib.reload(rsr)


# ── Normalized endpoint ──────────────────────────────────────────


class _FakeUser:
    def __init__(self, tenant_id: str = "tenant-rs-test") -> None:
        self.tenant_id = tenant_id
        self.id = "user-1"
        self.role = "admin"


@pytest.mark.asyncio
async def test_normalized_room_service_reports_local_gauges(monkeypatch):
    from domains.guest.experience_router import room_service_realtime as rsr
    from routers import system_health_normalized as shn

    fresh = rsr.RoomServiceOrderStream()
    monkeypatch.setattr(rsr, "order_stream", fresh)

    a = _FakeWebSocket()
    b = _FakeWebSocket()
    c = _FakeWebSocket()
    s1 = _FakeWebSocket()
    await fresh.connect(a, "t1", "bA")
    await fresh.connect(b, "t1", "bA")
    await fresh.connect(c, "t2", "bA")
    await fresh.connect_staff(s1, "t1")
    fresh.record_event_delivery(7)

    # Force the bridge view to a known shape so the test isn't coupled
    # to whichever singleton state the test runner happened to leave.
    class _StubAdapter:
        def get_metrics(self):
            return {
                "active": True,
                "subscribed_channels": [
                    "room_service:t1:bA",
                    "room_service:t2:bA",
                    "ws:broadcast:pms",
                ],
            }

    import infra.ws_redis_adapter as adapter_mod
    monkeypatch.setattr(adapter_mod, "ws_redis_adapter", _StubAdapter())

    result = await shn.normalized_room_service(_FakeUser())  # type: ignore[arg-type]

    assert result["status"] == "healthy"
    assert result["scope_id"] == "room-service"
    detail = result["detail"]
    assert detail["active_bookings_local"] == 2
    assert detail["guest_sockets_local"] == 3
    assert detail["staff_tenants_local"] == 1
    assert detail["staff_sockets_local"] == 1
    assert detail["events_last_hour"] == 7
    assert detail["bridge_active"] is True
    # Only the two `room_service:` channels are counted; `ws:broadcast:pms`
    # belongs to the chat bridge and must not leak into this gauge.
    assert detail["bridge_room_service_channels"] == 2
    assert "events delivered" in (result["evidence_summary"] or "")


@pytest.mark.asyncio
async def test_normalized_room_service_handles_bridge_failure(monkeypatch):
    """Adapter read errors must not flip the room-service card into a
    degraded state — the local gauges are still meaningful and the bridge
    has its own subsystem entry on the dashboard.
    """
    from domains.guest.experience_router import room_service_realtime as rsr
    from routers import system_health_normalized as shn

    fresh = rsr.RoomServiceOrderStream()
    monkeypatch.setattr(rsr, "order_stream", fresh)

    class _BrokenAdapter:
        def get_metrics(self):
            raise RuntimeError("redis down")

    import infra.ws_redis_adapter as adapter_mod
    monkeypatch.setattr(adapter_mod, "ws_redis_adapter", _BrokenAdapter())

    result = await shn.normalized_room_service(_FakeUser())  # type: ignore[arg-type]

    assert result["status"] == "healthy"
    assert result["detail"]["bridge_active"] is False
    assert result["detail"]["bridge_room_service_channels"] == 0


# ── Overview aggregator includes the new subsystem ───────────────


@pytest.mark.asyncio
async def test_overview_includes_room_service_subsystem(monkeypatch):
    from routers import system_health_normalized as shn

    user = _FakeUser()

    async def healthy(_u):
        return shn._health_response(
            status="healthy", severity="info",
            scope_type="tenant", scope_id=user.tenant_id,
            detail={"ok": True},
        )

    monkeypatch.setattr(shn, "normalized_channel_manager", healthy)
    monkeypatch.setattr(shn, "normalized_workers", healthy)
    monkeypatch.setattr(shn, "normalized_security", healthy)
    monkeypatch.setattr(shn, "normalized_observability", healthy)
    monkeypatch.setattr(shn, "normalized_alerts", healthy)
    monkeypatch.setattr(shn, "normalized_ws_bridge", healthy)
    monkeypatch.setattr(shn, "normalized_room_service", healthy)

    out = await shn.normalized_overview(user)

    assert "room_service" in out["subsystems"], (
        "the System Health overview must surface the new room-service "
        "card alongside the existing subsystems"
    )
    assert out["subsystems"]["room_service"]["status"] == "healthy"
    assert out["overall_status"] == "healthy"
