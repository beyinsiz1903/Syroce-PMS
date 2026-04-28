"""Task #44 — Tenant- and user-isolation regression tests for the
WebSocket broadcast helpers.

We don't spin up a full socket.io server here; instead we patch the
delivery primitives (``ws_redis_adapter.publish`` for the multi-instance
path and ``sio.emit`` for direct fan-out) and assert which rooms each
helper targets. That gives the same guarantee the task asks for — "events
do not cross to the wrong user/tenant" — without the flakiness of an
in-process socket server.

Covered:

  - ``broadcast_internal_message`` routes DMs ONLY to the recipient's
    user-room, department msgs ONLY to the dept-room, and broadcasts ONLY
    to the tenant-broadcast room.
  - ``broadcast_internal_message_read`` writes ONLY to the original
    sender's user-room (so unrelated staff don't see read receipts).
  - The ``internal_typing`` event handler fans out ONLY to the recipient's
    user-room based on the *authenticated* identity (client-supplied
    tenant/from-user values are ignored).
  - The PMS helpers ``broadcast_booking_update`` and
    ``broadcast_room_status_update`` route to ``pms:{tenant_id}`` and
    refuse to broadcast when ``tenant_id`` is missing (Task #43).
  - Cross-tenant: tenant A's DM never lands in tenant B's room.

Why patching ``ws_redis_adapter.publish`` is sufficient: the adapter
itself owns the socket.io fan-out (its local handler is wired to
``sio.emit`` in ``server.py``). If we asked socket.io to deliver an event
to room X, every client *not* enrolled in X would not see it — so by
asserting "publish was called with room X and only X" we are asserting
the exact same property the task asks about.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

import websocket_server as ws


# ──────────────────────────────────────────────────────────────────────
# broadcast_internal_message — DM / dept / broadcast routing
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dm_message_is_routed_only_to_recipient_user_room():
    """A DM to user U in tenant T must hit exactly one room:
    ``internal_chat:T:user:U`` — never the dept room, never broadcast,
    never another tenant's room."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock()
        with patch(
            "infra.ws_redis_adapter.ws_redis_adapter", fake_adapter
        ):
            await ws.broadcast_internal_message(
                "tenantA",
                {"id": "msg-1", "message": "hi"},
                to_user_id="userZ",
                to_department=None,
            )

    # Exactly one publish call, exactly to the recipient's DM room.
    assert fake_adapter.publish.await_count == 1
    args, _ = fake_adapter.publish.await_args
    assert args[0] == "internal_chat:tenantA:user:userZ"
    assert args[1] == "internal_message"
    # No direct sio.emit fallback should have fired (adapter was available).
    fake_sio.emit.assert_not_called()


@pytest.mark.asyncio
async def test_department_message_routes_only_to_department_room():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock()
        with patch(
            "infra.ws_redis_adapter.ws_redis_adapter", fake_adapter
        ):
            await ws.broadcast_internal_message(
                "tenantA",
                {"id": "msg-2"},
                to_user_id=None,
                to_department="Reception",
            )

    rooms = [c.args[0] for c in fake_adapter.publish.await_args_list]
    assert rooms == ["internal_chat:tenantA:dept:Reception"]


@pytest.mark.asyncio
async def test_tenant_broadcast_message_routes_only_to_broadcast_room():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock()
        with patch(
            "infra.ws_redis_adapter.ws_redis_adapter", fake_adapter
        ):
            await ws.broadcast_internal_message(
                "tenantA",
                {"id": "msg-3"},
                to_user_id=None,
                to_department=None,
            )

    rooms = [c.args[0] for c in fake_adapter.publish.await_args_list]
    assert rooms == ["internal_chat:tenantA:broadcast"]


@pytest.mark.asyncio
async def test_dm_does_not_leak_to_other_tenants_broadcast():
    """If the helper somehow fanned out to another tenant's room we
    would see it in the call list — assert it doesn't."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock()
        with patch(
            "infra.ws_redis_adapter.ws_redis_adapter", fake_adapter
        ):
            await ws.broadcast_internal_message(
                "tenantA",
                {"id": "msg-A"},
                to_user_id="userA1",
            )

    rooms = [c.args[0] for c in fake_adapter.publish.await_args_list]
    # No tenant-B room appears.
    assert all("tenantB" not in r for r in rooms)
    assert all(r.startswith("internal_chat:tenantA:") for r in rooms)


# ──────────────────────────────────────────────────────────────────────
# broadcast_internal_message_read — read receipts
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_receipt_routes_only_to_original_senders_user_room():
    """When user R reads a message that S originally sent in tenant T,
    only S's DM room (``internal_chat:T:user:S``) should receive the
    receipt — never the reader's room, never broadcast."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_internal_message_read(
            reader_id="userR",
            sender_id="userS",
            tenant_id="tenantA",
            message_ids=["m1"],
            partner_id="userR",
        )

    assert fake_adapter.publish.await_count == 1
    args, _ = fake_adapter.publish.await_args
    assert args[0] == "internal_chat:tenantA:user:userS"
    assert args[1] == "internal_message_read"


@pytest.mark.asyncio
async def test_read_receipt_dropped_when_sender_id_missing():
    """Without a sender we don't know whose room to write to. Anything
    other than 'no-op' would broadcast and leak read activity."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_internal_message_read(
            reader_id="userR",
            sender_id=None,
            tenant_id="tenantA",
        )
    fake_adapter.publish.assert_not_called()


@pytest.mark.asyncio
async def test_read_receipt_dropped_when_tenant_id_missing():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_internal_message_read(
            reader_id="userR",
            sender_id="userS",
            tenant_id=None,
        )
    fake_adapter.publish.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# internal_typing event — recipient-only routing using *authenticated*
# identity (client-supplied tenant/from-user are ignored)
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_typing_event_routes_only_to_recipient_room():
    sid = "sid-sender-1"
    ws.sid_identity[sid] = {
        "user_id": "userS",
        "tenant_id": "tenantA",
        "department": "Reception",
    }
    try:
        fake_adapter = type("A", (), {"publish": AsyncMock()})()
        with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
            await ws.internal_typing(sid, {
                "to_user_id": "userR",
                "from_user_name": "Sender Name",
                "is_typing": True,
            })
        assert fake_adapter.publish.await_count == 1
        args, _ = fake_adapter.publish.await_args
        # Recipient's tenant-scoped DM room — NOT the sender's, NOT broadcast,
        # NOT a third user's.
        assert args[0] == "internal_chat:tenantA:user:userR"
        assert args[1] == "internal_user_typing"
        # The authoritative tenant_id and from_user_id come from the socket
        # identity, not from client-supplied data.
        envelope = args[2]
        assert envelope["from_user_id"] == "userS"
        assert envelope["tenant_id"] == "tenantA"
    finally:
        ws.sid_identity.pop(sid, None)


@pytest.mark.asyncio
async def test_typing_event_ignores_client_supplied_tenant_to_block_spoofing():
    """Even if the client asserts a different tenant in the payload, the
    event must be routed to the *authenticated* tenant's room — never
    the impostor tenant."""
    sid = "sid-spoof"
    ws.sid_identity[sid] = {
        "user_id": "userHonest",
        "tenant_id": "tenantA",
        "department": None,
    }
    try:
        fake_adapter = type("A", (), {"publish": AsyncMock()})()
        with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
            await ws.internal_typing(sid, {
                "to_user_id": "userR",
                "tenant_id": "tenantB",  # spoof attempt
                "from_user_id": "userImpostor",  # spoof attempt
            })
        rooms = [c.args[0] for c in fake_adapter.publish.await_args_list]
        assert rooms == ["internal_chat:tenantA:user:userR"]
    finally:
        ws.sid_identity.pop(sid, None)


@pytest.mark.asyncio
async def test_typing_event_dropped_for_unauthenticated_socket():
    """No identity → silently dropped (no third-user spoofing)."""
    sid = "sid-anon"
    ws.sid_identity.pop(sid, None)
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.internal_typing(sid, {
            "to_user_id": "userR",
            "tenant_id": "tenantA",
        })
    fake_adapter.publish.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# Task #43 — booking_update / room_status_update tenant isolation
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_booking_update_routes_to_tenant_pms_room():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_booking_update(
            {"id": "B-1"}, event_type="checkin", tenant_id="tenantA",
        )

    assert fake_adapter.publish.await_count == 1
    args, _ = fake_adapter.publish.await_args
    assert args[0] == "pms:tenantA"
    assert args[1] == "booking_update"
    envelope = args[2]
    assert envelope["event_type"] == "checkin"
    assert envelope["tenant_id"] == "tenantA"


@pytest.mark.asyncio
async def test_broadcast_booking_update_isolates_two_tenants():
    """Same payload sent for two tenants must produce two distinct
    target rooms with no cross-pollination."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_booking_update({"id": "X"}, tenant_id="tenantA")
        await ws.broadcast_booking_update({"id": "Y"}, tenant_id="tenantB")

    rooms = [c.args[0] for c in fake_adapter.publish.await_args_list]
    assert rooms == ["pms:tenantA", "pms:tenantB"]


@pytest.mark.asyncio
async def test_broadcast_booking_update_drops_when_tenant_id_missing():
    """Defence in depth: a forgotten kwarg must NOT silently broadcast
    to every connected client (the original bug Task #43 closes)."""
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_booking_update({"id": "Z"})  # no tenant_id
    fake_adapter.publish.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_room_status_update_routes_to_tenant_pms_room():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_room_status_update(
            "101", "clean", tenant_id="tenantA",
        )
    args, _ = fake_adapter.publish.await_args
    assert args[0] == "pms:tenantA"
    assert args[1] == "room_status_update"


@pytest.mark.asyncio
async def test_broadcast_room_status_update_drops_when_tenant_id_missing():
    fake_adapter = type("A", (), {"publish": AsyncMock()})()
    with patch("infra.ws_redis_adapter.ws_redis_adapter", fake_adapter):
        await ws.broadcast_room_status_update("101", "dirty")
    fake_adapter.publish.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# join_room — protected-room enforcement
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_join_room_denies_other_tenants_pms_room():
    """User from tenantA cannot join pms:tenantB even with a forged
    join_room request — this is the exact attack Task #43 prevents."""
    sid = "sid-tA"
    ws.sid_identity[sid] = {
        "user_id": "u1",
        "tenant_id": "tenantA",
        "department": None,
    }
    try:
        with patch.object(ws, "sio") as fake_sio:
            fake_sio.emit = AsyncMock()
            fake_sio.enter_room = AsyncMock()
            await ws.join_room(sid, {"room": "pms:tenantB"})
        # Denied → enter_room must not have been called for the impostor room
        assert fake_sio.enter_room.await_count == 0
        # The 'room_join_denied' notification was emitted instead.
        fake_sio.emit.assert_called_once()
        assert fake_sio.emit.await_args.args[0] == "room_join_denied"
    finally:
        ws.sid_identity.pop(sid, None)


@pytest.mark.asyncio
async def test_join_room_denies_legacy_global_pms_room():
    """The legacy global ``'pms'`` room must be off-limits — joining it
    used to be the cross-tenant leak surface this task closes."""
    sid = "sid-anon"
    # Not enrolling identity → unauthenticated path also denied.
    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock()
        fake_sio.enter_room = AsyncMock()
        await ws.join_room(sid, {"room": "pms"})
    assert fake_sio.enter_room.await_count == 0
    fake_sio.emit.assert_called_once()
    assert fake_sio.emit.await_args.args[0] == "room_join_denied"


@pytest.mark.asyncio
async def test_join_room_allows_own_tenants_pms_room_explicit_request():
    """Reconnect logic on the client may re-request its own PMS room;
    that should still be honoured (the tenant matches the JWT)."""
    sid = "sid-self"
    ws.sid_identity[sid] = {
        "user_id": "u1",
        "tenant_id": "tenantA",
        "department": None,
    }
    try:
        with patch.object(ws, "sio") as fake_sio:
            fake_sio.emit = AsyncMock()
            fake_sio.enter_room = AsyncMock()
            await ws.join_room(sid, {"room": "pms:tenantA"})
        fake_sio.enter_room.assert_awaited_once_with(sid, "pms:tenantA")
    finally:
        ws.sid_identity.pop(sid, None)
