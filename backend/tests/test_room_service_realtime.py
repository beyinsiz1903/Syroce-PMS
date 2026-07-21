"""Task #64 — Real-time room service order updates.

These tests cover the in-process pub/sub layer + the new PATCH status
endpoint without spinning up a real ASGI server. The connection
manager is exercised directly with a minimal fake WebSocket so the
tests stay fast and deterministic across CI environments where a live
backend may not be available.

Covered:

  - ``RoomServiceOrderStream`` only delivers events to sockets
    subscribed to the same ``(tenant, booking)`` key, not to any other
    booking and not to other tenants.
  - ``emit_order_event`` extracts tenant/booking from the order doc and
    is a silent no-op when either is missing (it must NEVER bubble up
    to the originating HTTP request).
  - Dead sockets are pruned on the next broadcast.
  - The ``_VALID_ORDER_STATUSES`` set in ``guest_app`` matches the
    statuses the mobile UI knows how to render (``STATUS_LABEL`` /
    ``STATUS_TONE`` in ``orders.tsx``) so a backend-side typo can't
    silently render as an unknown badge.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _real_core_security():
    """Return the actual ``core.security`` *module*.

    ``core/__init__.py`` does ``from core.security import security as security``
    where the inner ``security`` is the package's HTTPBearer instance. That
    rebinds ``core.security`` on the package to the HTTPBearer object,
    so ``import core.security as cs`` then yields the HTTPBearer instead
    of the module. ``sys.modules`` still holds the real module — fetch
    it from there instead so monkeypatch can rewrite real attributes.
    """
    importlib.import_module("core.security")
    return sys.modules["core.security"]

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _FakeWebSocket:
    """Minimal stand-in for FastAPI's ``WebSocket`` used by the
    ``RoomServiceOrderStream`` API. We only need ``accept`` and
    ``send_text`` here; everything else (path params, query params)
    happens in the route handler which we don't exercise in this unit
    test."""

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.fail_on_send:
            raise ConnectionError("simulated disconnect")
        self.sent.append(text)


@pytest.mark.asyncio
async def test_broadcast_only_reaches_matching_booking_subscribers():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    ws_a1 = _FakeWebSocket()
    ws_a2 = _FakeWebSocket()
    ws_b = _FakeWebSocket()
    ws_other_tenant = _FakeWebSocket()

    await stream.connect(ws_a1, "tenant1", "bookingA")
    await stream.connect(ws_a2, "tenant1", "bookingA")
    await stream.connect(ws_b, "tenant1", "bookingB")
    await stream.connect(ws_other_tenant, "tenant2", "bookingA")

    delivered = await stream.broadcast(
        "tenant1", "bookingA", {"type": "room_service_order", "order": {"id": "o1"}}
    )

    assert delivered == 2, "event should reach both bookingA subscribers"
    assert len(ws_a1.sent) == 1
    assert len(ws_a2.sent) == 1
    assert ws_b.sent == [], "bookingB must not see bookingA's event"
    assert ws_other_tenant.sent == [], (
        "tenant2 must not see tenant1's event even on the same booking_id"
    )

    payload = json.loads(ws_a1.sent[0])
    assert payload["order"] == {"id": "o1"}
    assert payload["type"] == "room_service_order"
    assert "timestamp" in payload, "broadcast must stamp every frame"


@pytest.mark.asyncio
async def test_broadcast_no_subscribers_is_noop():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    delivered = await stream.broadcast("tenantX", "bookingX", {"type": "x"})
    assert delivered == 0


@pytest.mark.asyncio
async def test_dead_sockets_are_pruned_on_broadcast():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    healthy = _FakeWebSocket()
    broken = _FakeWebSocket(fail_on_send=True)

    await stream.connect(healthy, "t", "b")
    await stream.connect(broken, "t", "b")
    assert stream.connection_count("t", "b") == 2

    delivered = await stream.broadcast("t", "b", {"type": "x"})
    assert delivered == 1, "broken socket must not count as delivered"
    assert stream.connection_count("t", "b") == 1, (
        "broken socket must be pruned so it can't pile up across broadcasts"
    )


@pytest.mark.asyncio
async def test_disconnect_removes_subscriber():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    ws = _FakeWebSocket()
    await stream.connect(ws, "t", "b")
    await stream.disconnect(ws, "t", "b")
    assert stream.connection_count("t", "b") == 0

    # A second disconnect on an already-empty bucket must not raise —
    # the WS endpoint runs disconnect from a `finally:` so it can be
    # reached after a partial connect failure.
    await stream.disconnect(ws, "t", "b")


@pytest.mark.asyncio
async def test_emit_order_event_uses_tenant_and_booking_from_doc():
    from domains.guest.experience_router import room_service_realtime as rsr

    stream = rsr.order_stream  # the module-level singleton
    ws_match = _FakeWebSocket()
    ws_wrong_booking = _FakeWebSocket()
    await stream.connect(ws_match, "tenantE", "bookingE")
    await stream.connect(ws_wrong_booking, "tenantE", "bookingF")
    try:
        delivered = await rsr.emit_order_event(
            {
                "id": "ord-1",
                "tenant_id": "tenantE",
                "booking_id": "bookingE",
                "status": "preparing",
            },
            event_type="status_changed",
        )
        assert delivered == 1
        assert len(ws_match.sent) == 1
        assert ws_wrong_booking.sent == []
        payload = json.loads(ws_match.sent[0])
        assert payload["event"] == "status_changed"
        assert payload["order"]["id"] == "ord-1"
        # _id stripping guarantees we never leak a Mongo BSON id over
        # the wire even if the caller forgets to project it out.
        assert "_id" not in payload["order"]
    finally:
        await stream.disconnect(ws_match, "tenantE", "bookingE")
        await stream.disconnect(ws_wrong_booking, "tenantE", "bookingF")


@pytest.mark.asyncio
async def test_emit_order_event_missing_keys_is_silent_noop():
    from domains.guest.experience_router import room_service_realtime as rsr

    # Missing tenant_id → must not raise, must not deliver. This is
    # critical: the create/update HTTP endpoints call emit_order_event
    # in their happy path and a raise here would roll back the user's
    # action.
    delivered = await rsr.emit_order_event(
        {"id": "ord-x", "booking_id": "bookingE"}, event_type="created"
    )
    assert delivered == 0

    delivered = await rsr.emit_order_event(
        {"id": "ord-y", "tenant_id": "tenantE"}, event_type="created"
    )
    assert delivered == 0


def test_valid_order_statuses_match_mobile_ui_labels():
    """A status the backend accepts but the mobile UI doesn't recognise
    would render as a generic '—' badge with the wrong tone — defeating
    the realtime UX. Pin the two sets together at test time."""
    from domains.guest.experience_router.guest_app import _VALID_ORDER_STATUSES

    # Mirror of STATUS_LABEL/STATUS_TONE keys in mobile/app/(guest)/orders.tsx.
    mobile_known_statuses = {
        "pending", "confirmed", "preparing", "delivered", "cancelled",
    }
    assert _VALID_ORDER_STATUSES == mobile_known_statuses


# ──────────────────────────────────────────────────────────────────────
# Authorization regressions (post-review)
# ──────────────────────────────────────────────────────────────────────


def test_status_patch_role_allowlist_excludes_guest_and_agency():
    """PATCH status is staff-only — guests/agency must not be in the allowlist."""
    from domains.guest.experience_router.guest_app import (
        _ROOM_SERVICE_STAFF_ROLES,
    )
    from models.enums import UserRole

    assert UserRole.GUEST not in _ROOM_SERVICE_STAFF_ROLES
    assert UserRole.AGENCY_AGENT not in _ROOM_SERVICE_STAFF_ROLES
    assert UserRole.AGENCY_ADMIN not in _ROOM_SERVICE_STAFF_ROLES
    assert UserRole.FRONT_DESK in _ROOM_SERVICE_STAFF_ROLES
    assert UserRole.HOUSEKEEPING in _ROOM_SERVICE_STAFF_ROLES


def test_status_patch_dependency_rejects_guest_role():
    """`require_role` dependency raises 403 for GUEST, passes for staff."""
    import asyncio

    from fastapi import HTTPException

    from domains.guest.experience_router.guest_app import (
        _ROOM_SERVICE_STAFF_ROLES,
    )
    from models.enums import UserRole
    from modules.pms_core.role_permission_service import require_role

    dep = require_role(*_ROOM_SERVICE_STAFF_ROLES)

    class _U:
        def __init__(self, role):
            self.role = role
            self.id = "u1"
            self.tenant_id = "t1"

    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(dep(current_user=_U(UserRole.GUEST)))
    assert exc.value.status_code == 403

    asyncio.get_event_loop().run_until_complete(dep(current_user=_U(UserRole.FRONT_DESK)))


# ──────────────────────────────────────────────────────────────────────
# WebSocket auth parity with HTTP (jti revocation, deleted user, tenant
# mismatch, mass-revoke watermark)
# ──────────────────────────────────────────────────────────────────────


def _make_jwt(payload: dict) -> str:
    """Sign a JWT with the backend's JWT_SECRET so the WS auth path
    accepts it. Tests run in-process so the same secret is in scope."""
    import jwt
    from core.security import JWT_ALGORITHM, JWT_SECRET
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_ws_auth_rejects_missing_or_malformed_token(monkeypatch):
    from domains.guest.experience_router.guest_app import (
        _authenticate_ws_token,
    )

    assert await _authenticate_ws_token(None) is None
    assert await _authenticate_ws_token("") is None
    assert await _authenticate_ws_token("not-a-jwt") is None


@pytest.mark.asyncio
async def test_ws_auth_rejects_token_for_deleted_user(monkeypatch):
    from domains.guest.experience_router import guest_app as ga
    core_security = _real_core_security()

    # Bypass the per-process user cache so our find_one stub is hit.
    monkeypatch.setattr(core_security, "_user_doc_cache_get", lambda uid: None)
    monkeypatch.setattr(core_security, "_user_doc_cache_set", lambda uid, doc: None)
    monkeypatch.setattr(core_security, "is_jti_revoked", _async_return(False))

    class _Users:
        async def find_one(self, *_a, **_kw):
            return None  # user deleted

    class _Db:
        users = _Users()

    monkeypatch.setattr(ga, "db", _Db())

    token = _make_jwt({"user_id": "ghost", "tenant_id": "tenantX"})
    assert await ga._authenticate_ws_token(token) is None


@pytest.mark.asyncio
async def test_ws_auth_rejects_revoked_jti(monkeypatch):
    from domains.guest.experience_router import guest_app as ga
    core_security = _real_core_security()

    monkeypatch.setattr(core_security, "_user_doc_cache_get", lambda uid: None)
    monkeypatch.setattr(core_security, "_user_doc_cache_set", lambda uid, doc: None)
    monkeypatch.setattr(core_security, "is_jti_revoked", _async_return(True))

    class _Users:
        async def find_one(self, *_a, **_kw):  # pragma: no cover - guarded by jti
            return {"id": "u1", "tenant_id": "tenantX", "role": "front_desk"}

    class _Db:
        users = _Users()

    monkeypatch.setattr(ga, "db", _Db())

    token = _make_jwt({"user_id": "u1", "tenant_id": "tenantX", "jti": "revoked-1"})
    assert await ga._authenticate_ws_token(token) is None


@pytest.mark.asyncio
async def test_ws_auth_rejects_tenant_mismatch(monkeypatch):
    from domains.guest.experience_router import guest_app as ga
    core_security = _real_core_security()

    monkeypatch.setattr(core_security, "_user_doc_cache_get", lambda uid: None)
    monkeypatch.setattr(core_security, "_user_doc_cache_set", lambda uid, doc: None)
    monkeypatch.setattr(core_security, "is_jti_revoked", _async_return(False))

    class _Users:
        async def find_one(self, *_a, **_kw):
            return {"id": "u1", "tenant_id": "real_tenant", "role": "front_desk"}

    class _Db:
        users = _Users()

    monkeypatch.setattr(ga, "db", _Db())

    token = _make_jwt({"user_id": "u1", "tenant_id": "forged_tenant"})
    assert await ga._authenticate_ws_token(token) is None


@pytest.mark.asyncio
async def test_ws_auth_rejects_token_older_than_password_change(monkeypatch):
    from domains.guest.experience_router import guest_app as ga
    core_security = _real_core_security()

    monkeypatch.setattr(core_security, "_user_doc_cache_get", lambda uid: None)
    monkeypatch.setattr(core_security, "_user_doc_cache_set", lambda uid, doc: None)
    monkeypatch.setattr(core_security, "is_jti_revoked", _async_return(False))

    class _Users:
        async def find_one(self, *_a, **_kw):
            return {
                "id": "u1",
                "tenant_id": "tenantX",
                "role": "front_desk",
                # Watermark in the future: any pre-existing token is invalid.
                "tokens_invalid_before": 9_999_999_999,
            }

    class _Db:
        users = _Users()

    monkeypatch.setattr(ga, "db", _Db())

    # iat well before the watermark.
    token = _make_jwt({"user_id": "u1", "tenant_id": "tenantX", "iat": 1_000_000})
    assert await ga._authenticate_ws_token(token) is None


@pytest.mark.asyncio
async def test_ws_booking_authz_staff_can_subscribe_anywhere_in_tenant(monkeypatch):
    """Staff roles bypass guest↔booking ownership checks (kitchen
    display, front desk monitoring) — booking just needs to be in
    their tenant."""
    from domains.guest.experience_router import guest_app as ga

    class _Bookings:
        async def find_one(self, *_a, **_kw):
            return {"id": "bkX", "guest_id": "someone_else"}

    class _Db:
        bookings = _Bookings()

    monkeypatch.setattr(ga, "db", _Db())

    identity = {
        "user_id": "staff1",
        "tenant_id": "t1",
        "role": "front_desk",
        "email": "fd@example.com",
    }
    assert await ga._user_can_subscribe_to_booking(identity, "bkX") is True


@pytest.mark.asyncio
async def test_ws_booking_authz_guest_blocked_from_other_guests_booking(monkeypatch):
    """Critical authz: a guest authenticated against the same tenant
    must NOT receive live order events for another guest's booking."""
    from domains.guest.experience_router import guest_app as ga

    class _Bookings:
        async def find_one(self, *_a, **_kw):
            return {"id": "bkX", "guest_id": "guest_other"}

    class _Guests:
        def find(self, *_a, **_kw):
            async def _gen():
                # The attacker's guest record(s) — different id than the booking's guest_id.
                yield {"id": "guest_attacker"}
            return _gen()

    class _Db:
        bookings = _Bookings()
        guests = _Guests()

    monkeypatch.setattr(ga, "db", _Db())

    identity = {
        "user_id": "u_attacker",
        "tenant_id": "t1",
        "role": "guest",
        "email": "attacker@example.com",
    }
    assert await ga._user_can_subscribe_to_booking(identity, "bkX") is False


@pytest.mark.asyncio
async def test_ws_booking_authz_guest_owns_booking(monkeypatch):
    """The booking's owning guest must be able to subscribe."""
    from domains.guest.experience_router import guest_app as ga

    class _Bookings:
        async def find_one(self, *_a, **_kw):
            return {"id": "bk1", "guest_id": "guest_self"}

    class _Guests:
        def find(self, *_a, **_kw):
            async def _gen():
                yield {"id": "guest_self"}
            return _gen()

    class _Db:
        bookings = _Bookings()
        guests = _Guests()

    monkeypatch.setattr(ga, "db", _Db())

    identity = {
        "user_id": "u1",
        "tenant_id": "t1",
        "role": "guest",
        "email": "guest@example.com",
    }
    assert await ga._user_can_subscribe_to_booking(identity, "bk1") is True


@pytest.mark.asyncio
async def test_ws_booking_authz_guest_blocked_when_booking_missing(monkeypatch):
    """A booking that doesn't exist in the user's tenant must yield
    a forbidden, not a tenant-wide read primitive."""
    from domains.guest.experience_router import guest_app as ga

    class _Bookings:
        async def find_one(self, *_a, **_kw):
            return None

    class _Db:
        bookings = _Bookings()

    monkeypatch.setattr(ga, "db", _Db())

    identity = {
        "user_id": "u1",
        "tenant_id": "t1",
        "role": "guest",
        "email": "guest@example.com",
    }
    assert await ga._user_can_subscribe_to_booking(identity, "nonexistent") is False


@pytest.mark.asyncio
async def test_ws_auth_accepts_valid_token(monkeypatch):
    from domains.guest.experience_router import guest_app as ga
    core_security = _real_core_security()

    monkeypatch.setattr(core_security, "_user_doc_cache_get", lambda uid: None)
    monkeypatch.setattr(core_security, "_user_doc_cache_set", lambda uid, doc: None)
    monkeypatch.setattr(core_security, "is_jti_revoked", _async_return(False))

    class _Users:
        async def find_one(self, *_a, **_kw):
            return {"id": "u1", "tenant_id": "tenantX", "role": "front_desk"}

    class _Db:
        users = _Users()

    monkeypatch.setattr(ga, "db", _Db())

    token = _make_jwt({"user_id": "u1", "tenant_id": "tenantX"})
    identity = await ga._authenticate_ws_token(token)
    assert identity == {
        "user_id": "u1",
        "tenant_id": "tenantX",
        "role": "front_desk",
        "email": None,
    }


def _async_return(value):
    """Return an async function that always resolves to ``value`` —
    handy for stubbing ``is_jti_revoked`` etc. in monkeypatching."""
    async def _stub(*_a, **_kw):
        return value
    return _stub


# ──────────────────────────────────────────────────────────────────────
# Task #69 — Staff (tenant-wide) fan-out + GET /guest/staff/...
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_staff_broadcast_reaches_every_tenant_subscriber():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    staff1 = _FakeWebSocket()
    staff2 = _FakeWebSocket()
    other_tenant_staff = _FakeWebSocket()
    await stream.connect_staff(staff1, "t1")
    await stream.connect_staff(staff2, "t1")
    await stream.connect_staff(other_tenant_staff, "t2")

    delivered = await stream.broadcast_staff(
        "t1", {"type": "room_service_order", "order": {"id": "o1"}}
    )
    assert delivered == 2
    assert len(staff1.sent) == 1 and len(staff2.sent) == 1
    assert other_tenant_staff.sent == [], (
        "tenant2 staff must not see tenant1 events"
    )


@pytest.mark.asyncio
async def test_staff_dead_socket_pruned_on_broadcast():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    healthy = _FakeWebSocket()
    broken = _FakeWebSocket(fail_on_send=True)
    await stream.connect_staff(healthy, "t1")
    await stream.connect_staff(broken, "t1")
    assert stream.staff_connection_count("t1") == 2

    delivered = await stream.broadcast_staff("t1", {"type": "x"})
    assert delivered == 1
    assert stream.staff_connection_count("t1") == 1


@pytest.mark.asyncio
async def test_staff_disconnect_removes_subscriber():
    from domains.guest.experience_router.room_service_realtime import (
        RoomServiceOrderStream,
    )

    stream = RoomServiceOrderStream()
    ws = _FakeWebSocket()
    await stream.connect_staff(ws, "t1")
    await stream.disconnect_staff(ws, "t1")
    assert stream.staff_connection_count("t1") == 0
    # idempotent — finally-block must not raise on a second disconnect.
    await stream.disconnect_staff(ws, "t1")


@pytest.mark.asyncio
async def test_emit_order_event_fans_out_to_both_booking_and_staff():
    """A single order change must reach both the guest's per-booking
    subscriber and every tenant-staff subscriber, so a kitchen
    dashboard can be wired without per-booking sockets."""
    from domains.guest.experience_router import room_service_realtime as rsr

    stream = rsr.order_stream
    guest_ws = _FakeWebSocket()
    staff_ws = _FakeWebSocket()
    wrong_tenant_staff = _FakeWebSocket()
    await stream.connect(guest_ws, "tenantE", "bookingE")
    await stream.connect_staff(staff_ws, "tenantE")
    await stream.connect_staff(wrong_tenant_staff, "tenantOther")
    try:
        delivered = await rsr.emit_order_event(
            {
                "id": "ord-1",
                "tenant_id": "tenantE",
                "booking_id": "bookingE",
                "status": "confirmed",
            },
            event_type="status_changed",
        )
        # 1 guest + 1 staff = 2 (and NOT the wrong-tenant staff).
        assert delivered == 2
        assert len(guest_ws.sent) == 1
        assert len(staff_ws.sent) == 1
        assert wrong_tenant_staff.sent == []

        staff_payload = json.loads(staff_ws.sent[0])
        assert staff_payload["event"] == "status_changed"
        assert staff_payload["order"]["id"] == "ord-1"
    finally:
        await stream.disconnect(guest_ws, "tenantE", "bookingE")
        await stream.disconnect_staff(staff_ws, "tenantE")
        await stream.disconnect_staff(wrong_tenant_staff, "tenantOther")


@pytest.mark.asyncio
async def test_staff_open_statuses_are_three_pre_delivery_states():
    """The staff dashboard hides delivered/cancelled by default —
    pin the set so the UI's ``STATUS_FLOW`` (pending → confirmed →
    preparing → delivered) stays in lock-step with what we list."""
    from domains.guest.experience_router.guest_app import _STAFF_OPEN_STATUSES

    assert _STAFF_OPEN_STATUSES == {"pending", "confirmed", "preparing"}


@pytest.mark.asyncio
async def test_staff_list_filters_today_open_and_enriches_room_number(monkeypatch):
    """End-to-end shape check on `list_staff_room_service_orders`:
    it must scope to the caller's tenant, restrict to today's open
    orders by default, and enrich each row with `room_number` via the
    rooms collection (with a booking-row fallback)."""
    from domains.guest.experience_router import guest_app as ga
    from datetime import UTC, datetime

    today_iso = datetime.now(UTC).isoformat()

    captured_query: dict = {}

    class _OrdersCursor:
        def __init__(self, docs):
            self._docs = docs
        def sort(self, *_a, **_kw):
            return self
        async def to_list(self, _limit):
            return self._docs

    class _Orders:
        def find(self, query, _proj=None):
            captured_query.update(query)
            return _OrdersCursor([
                # Open + room_id resolves via rooms_map.
                {
                    "id": "o1", "tenant_id": "t1", "booking_id": "bk1",
                    "room_id": "r1", "items": [{"name": "Coffee", "price": 4, "quantity": 1}],
                    "total_amount": 4, "status": "pending", "ordered_at": today_iso,
                },
                # Open + missing room_id, falls back via booking lookup.
                {
                    "id": "o2", "tenant_id": "t1", "booking_id": "bk2",
                    "room_id": None, "items": [{"name": "Tea", "price": 3, "quantity": 1}],
                    "total_amount": 3, "status": "preparing", "ordered_at": today_iso,
                },
            ])

    class _Rooms:
        def find(self, query, _proj=None):
            assert query.get("tenant_id") == "t1", "rooms lookup must be tenant-scoped"
            wanted = set(query["id"]["$in"])
            async def _gen():
                for r in [
                    {"id": "r1", "room_number": "101"},
                    {"id": "r2", "room_number": "202"},
                ]:
                    if r["id"] in wanted:
                        yield r
            return _gen()

    class _Bookings:
        def find(self, query, _proj=None):
            assert query.get("tenant_id") == "t1", "bookings lookup must be tenant-scoped"
            wanted = set(query["id"]["$in"])
            async def _gen():
                for b in [{"id": "bk2", "room_id": "r2", "room_number": None}]:
                    if b["id"] in wanted:
                        yield b
            return _gen()

    class _Db:
        room_service_orders = _Orders()
        rooms = _Rooms()
        bookings = _Bookings()

    monkeypatch.setattr(ga, "db", _Db())

    class _U:
        tenant_id = "t1"
        id = "staff1"

    result = await ga.list_staff_room_service_orders(
        include_completed=False, current_user=_U(), _role=None,
    )
    orders = result["orders"]
    assert {o["id"] for o in orders} == {"o1", "o2"}
    by_id = {o["id"]: o for o in orders}
    assert by_id["o1"]["room_number"] == "101"
    assert by_id["o2"]["room_number"] == "202", (
        "missing room_id must fall back to booking → room_id → rooms"
    )
    # tenant scoping + today filter on the orders query
    assert captured_query["tenant_id"] == "t1"
    assert captured_query["status"]["$in"] == ["confirmed", "pending", "preparing"]
    assert "ordered_at" in captured_query


def test_staff_ws_role_check_rejects_guest_role():
    """The staff WS endpoint must close 4403 for non-staff identities,
    so a guest-issued JWT can't tap the tenant-wide stream."""
    from domains.guest.experience_router.guest_app import (
        _ROOM_SERVICE_STAFF_ROLES,
    )
    from models.enums import UserRole

    allowed = {r.value for r in _ROOM_SERVICE_STAFF_ROLES}
    assert UserRole.GUEST.value not in allowed
    assert UserRole.AGENCY_AGENT.value not in allowed


@pytest.mark.asyncio
async def test_enrich_order_with_room_number_uses_room_id(monkeypatch):
    """Status broadcasts must carry room_number so the staff dashboard
    can render brand-new rows without a follow-up REST refetch."""
    from domains.guest.experience_router import guest_app as ga

    class _Rooms:
        async def find_one(self, query, _proj=None):
            assert query.get("tenant_id") == "t1"
            assert query.get("id") == "r1"
            return {"room_number": "404"}

    class _Db:
        rooms = _Rooms()
        bookings = None  # not used on this code path

    monkeypatch.setattr(ga, "db", _Db())

    order = {"id": "o", "tenant_id": "t1", "room_id": "r1"}
    await ga._enrich_order_with_room_number(order)
    assert order["room_number"] == "404"


@pytest.mark.asyncio
async def test_enrich_order_falls_back_to_booking_when_room_id_missing(monkeypatch):
    """Older order docs may not have stored room_id; we must walk
    booking → room_id → rooms before giving up."""
    from domains.guest.experience_router import guest_app as ga

    class _Bookings:
        async def find_one(self, query, _proj=None):
            assert query.get("tenant_id") == "t1"
            assert query.get("id") == "bk1"
            return {"room_id": "r9"}

    class _Rooms:
        async def find_one(self, query, _proj=None):
            assert query.get("id") == "r9"
            return {"room_number": "909"}

    class _Db:
        bookings = _Bookings()
        rooms = _Rooms()

    monkeypatch.setattr(ga, "db", _Db())

    order = {"id": "o", "tenant_id": "t1", "booking_id": "bk1"}
    await ga._enrich_order_with_room_number(order)
    assert order["room_number"] == "909"


@pytest.mark.asyncio
async def test_enrich_order_swallows_db_errors(monkeypatch):
    """A failing room lookup must NOT bubble up — emit_order_event is
    on the HTTP happy path and a raise here would roll back the user's
    status update."""
    from domains.guest.experience_router import guest_app as ga

    class _Rooms:
        async def find_one(self, *_a, **_kw):
            raise RuntimeError("db down")

    class _Db:
        rooms = _Rooms()

    monkeypatch.setattr(ga, "db", _Db())

    order = {"id": "o", "tenant_id": "t1", "room_id": "r1"}
    await ga._enrich_order_with_room_number(order)  # must not raise
    assert "room_number" not in order  # left absent on failure


@pytest.mark.asyncio
async def test_enrich_order_is_noop_when_room_number_already_present(monkeypatch):
    """If the order already carries a room_number, we must NOT do an
    extra DB round-trip — keeps emit_order_event cheap on the hot path."""
    from domains.guest.experience_router import guest_app as ga

    class _Rooms:
        async def find_one(self, *_a, **_kw):  # pragma: no cover - guarded
            raise AssertionError("rooms.find_one must not be called")

    class _Db:
        rooms = _Rooms()

    monkeypatch.setattr(ga, "db", _Db())

    order = {"id": "o", "tenant_id": "t1", "room_id": "r1", "room_number": "preset"}
    await ga._enrich_order_with_room_number(order)
    assert order["room_number"] == "preset"


# ──────────────────────────────────────────────────────────────────────
# Task #70 — multi-pod cross-instance bridge
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_order_event_bridges_via_ws_redis_adapter(monkeypatch):
    """A status change emitted on pod B must reach a guest WebSocket
    pinned to pod A through the ws_redis_adapter Redis pub/sub bridge.

    Simulated in-process with two ``RoomServiceOrderStream`` instances
    and two ``WebSocketRedisAdapter`` instances connected by a fake
    in-memory Redis bus. The dispatcher half of the bridge is the
    ``room_service:`` prefix detection in ``websocket_server.local_broadcast``,
    which is wired in here as each adapter's local handler.
    """
    import asyncio

    from domains.guest.experience_router import room_service_realtime as rsr
    from infra.ws_redis_adapter import WebSocketRedisAdapter

    # Pod A owns the guest socket; pod B owns the staff request that
    # mutates the order status. Each pod gets its own connection
    # manager — the singleton `rsr.order_stream` represents pod A's
    # because that's where the test's emit_order_event is invoked
    # against (we monkeypatch it onto pod B for the publish call).
    stream_a = rsr.RoomServiceOrderStream()
    stream_b = rsr.RoomServiceOrderStream()

    queues: dict[str, list[asyncio.Queue]] = {}

    class _FakePubSub:
        def __init__(self) -> None:
            self._queues: list[asyncio.Queue] = []

        async def subscribe(self, channel):
            q: asyncio.Queue = asyncio.Queue()
            queues.setdefault(channel, []).append(q)
            self._queues.append(q)

        async def unsubscribe(self, channel=None):
            pass

        async def listen(self):
            while True:
                for q in list(self._queues):
                    try:
                        msg = q.get_nowait()
                    except asyncio.QueueEmpty:
                        continue
                    yield msg
                await asyncio.sleep(0.01)

        async def close(self):
            pass

    class _FakeRedis:
        def __init__(self, pubsub):
            self._pubsub = pubsub

        def pubsub(self):
            return self._pubsub

        async def publish(self, channel, message):
            for q in queues.get(channel, []):
                await q.put({"type": "message", "data": message})
            return len(queues.get(channel, []))

    # Each adapter dispatches `room_service:` rooms to *its own* stream
    # — same shape as the production handler in websocket_server.local_broadcast.
    def _make_handler(stream):
        async def _handler(room, event, data):
            parsed = rsr.parse_room_key(room)
            if parsed is None:
                return
            tenant_id, booking_id = parsed
            await stream.broadcast(tenant_id, booking_id, data)
        return _handler

    ps_a = _FakePubSub()
    adapter_a = WebSocketRedisAdapter()
    await adapter_a.initialize(
        _FakeRedis(ps_a), "inst-A", local_handler=_make_handler(stream_a)
    )

    ps_b = _FakePubSub()
    adapter_b = WebSocketRedisAdapter()
    await adapter_b.initialize(
        _FakeRedis(ps_b), "inst-B", local_handler=_make_handler(stream_b)
    )

    # Pod A's guest opens a WS for booking B1; the connect path issues
    # adapter_a.subscribe(room) so pod A starts receiving cross-pod
    # publishes for that channel.
    ws_guest = _FakeWebSocket()
    await stream_a.connect(ws_guest, "tenant1", "bookingB1")
    # Connect's adapter call goes through the singleton — also subscribe
    # adapter_a directly so this fake pod is wired up the same way.
    await adapter_a.subscribe(rsr._room_key("tenant1", "bookingB1"))

    try:
        # Pod B writes a status change. Patch the singleton adapter so
        # rsr.emit_order_event publishes through adapter_b (i.e. as if
        # the staff PATCH landed on pod B).
        monkeypatch.setattr(
            "infra.ws_redis_adapter.ws_redis_adapter", adapter_b
        )
        # Pod B's local stream is empty; the only consumer is pod A's
        # guest socket — which must still receive the event via Redis.
        await rsr.emit_order_event(
            {
                "id": "order-XPOD",
                "tenant_id": "tenant1",
                "booking_id": "bookingB1",
                "status": "preparing",
            },
            event_type="status_changed",
        )

        # Wait up to ~1s for the bridge to deliver — Done-looks-like #2.
        for _ in range(100):
            await asyncio.sleep(0.01)
            if ws_guest.sent:
                break

        assert ws_guest.sent, (
            "guest socket on pod A must receive the event written on pod B "
            "via the ws_redis_adapter bridge"
        )
        payload = json.loads(ws_guest.sent[-1])
        assert payload["event"] == "status_changed"
        assert payload["order"]["id"] == "order-XPOD"
        assert payload["order"]["status"] == "preparing"
    finally:
        await stream_a.disconnect(ws_guest, "tenant1", "bookingB1")
        await adapter_a.close()
        await adapter_b.close()


@pytest.mark.asyncio
async def test_emit_order_event_falls_back_to_local_when_adapter_unwired():
    """When the ws_redis_adapter has not been initialised (its
    ``_local_handler`` is None — true in tests and very early startup),
    ``emit_order_event`` must still fan out to the in-process
    ``order_stream`` so the publishing pod's own subscribers don't
    silently lose updates."""
    from domains.guest.experience_router import room_service_realtime as rsr
    from infra.ws_redis_adapter import ws_redis_adapter

    # Sanity guard: this test relies on the singleton being unwired.
    assert ws_redis_adapter._local_handler is None

    ws = _FakeWebSocket()
    await rsr.order_stream.connect(ws, "tenantFB", "bookingFB")
    try:
        delivered = await rsr.emit_order_event(
            {
                "id": "ord-fb",
                "tenant_id": "tenantFB",
                "booking_id": "bookingFB",
                "status": "preparing",
            },
            event_type="status_changed",
        )
        assert delivered == 1
        assert len(ws.sent) == 1
    finally:
        await rsr.order_stream.disconnect(ws, "tenantFB", "bookingFB")


@pytest.mark.asyncio
async def test_emit_order_event_uses_adapter_when_wired(monkeypatch):
    """When the ws_redis_adapter *is* wired (bootstrap phase F has run),
    ``emit_order_event`` must:

      * deliver locally via ``order_stream.broadcast`` (accurate per-
        socket delivery count, dead-socket pruning); and
      * fan the same event out to peer pods via
        ``adapter.publish_remote_only`` — the remote-only variant so
        the publishing pod is not double-delivered through the
        adapter's local-handler dispatch.
    """
    from domains.guest.experience_router import room_service_realtime as rsr
    from infra.ws_redis_adapter import ws_redis_adapter

    remote_calls: list[tuple] = []

    async def _fake_publish_remote_only(room, event, data):
        remote_calls.append((room, event, data))

    # `_adapter_is_wired()` only checks `_local_handler is not None`, so
    # any non-None sentinel is enough to flip emit_order_event onto the
    # bridged path. The handler itself is NOT invoked from
    # publish_remote_only — the local broadcast handles origin-pod fan-out.
    async def _unused_local_handler(*_a, **_kw):  # pragma: no cover
        raise AssertionError(
            "local_handler must NOT be called when publishing locally; "
            "double-delivery on the origin pod would result"
        )

    monkeypatch.setattr(
        ws_redis_adapter, "_local_handler", _unused_local_handler
    )
    monkeypatch.setattr(
        ws_redis_adapter, "publish_remote_only", _fake_publish_remote_only
    )

    ws = _FakeWebSocket()
    await rsr.order_stream.connect(ws, "tenantW", "bookingW")
    try:
        delivered = await rsr.emit_order_event(
            {
                "id": "ord-w",
                "tenant_id": "tenantW",
                "booking_id": "bookingW",
                "status": "delivered",
            },
            event_type="status_changed",
        )
        # Accurate local count — not a connection_count() proxy.
        assert delivered == 1
        # Local origin-pod fan-out fired exactly once (no double-delivery).
        assert len(ws.sent) == 1
        # Cross-pod publish fired exactly once with the right shape.
        assert len(remote_calls) == 1
        room, event, data = remote_calls[0]
        assert room == "room_service:tenantW:bookingW"
        assert event == "room_service_order"
        assert data["event"] == "status_changed"
        assert data["order"]["id"] == "ord-w"
    finally:
        await rsr.order_stream.disconnect(ws, "tenantW", "bookingW")


def test_parse_room_key_round_trips():
    """`parse_room_key` is the inverse of `_room_key`; the dispatcher in
    websocket_server.local_broadcast relies on this contract."""
    from domains.guest.experience_router.room_service_realtime import (
        _room_key,
        parse_room_key,
    )

    assert parse_room_key(_room_key("t1", "b1")) == ("t1", "b1")
    # Non-room-service rooms must return None so the dispatcher falls
    # through to the socket.io path.
    assert parse_room_key("pms:t1") is None
    assert parse_room_key("internal_chat:t1:user:u1") is None
    assert parse_room_key("") is None
    # Malformed prefix must not match.
    assert parse_room_key("room_service:") is None
    assert parse_room_key("room_service:t1") is None
    assert parse_room_key("room_service::b1") is None
    assert parse_room_key("room_service:t1:") is None
