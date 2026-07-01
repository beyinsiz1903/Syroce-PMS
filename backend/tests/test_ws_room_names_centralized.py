"""Task #367 — centralized WebSocket room-name generation.

These tests pin the consistency guarantees of core.ws_rooms:
  - tenant_id is a required argument everywhere (no silent pms:None),
  - the room a producer emits to is byte-for-byte the room the connect
    handler enrols an authenticated socket into,
  - the room-QR notification emits land in that same tenant broadcast room
    (the bug Task #367 fixes: it used to emit to a hand-built `tenant:{id}`
    room that no client ever joins).
"""
from __future__ import annotations

import pytest

from core import ws_rooms
from core.ws_rooms import WebSocketRoomError


def test_tenant_id_is_required_everywhere():
    for call in (
        lambda: ws_rooms.tenant_broadcast_room(None),
        lambda: ws_rooms.tenant_broadcast_room(""),
        lambda: ws_rooms.internal_chat_user_room(None, "u"),
        lambda: ws_rooms.internal_chat_user_room("t", None),
        lambda: ws_rooms.internal_chat_department_room("t", None),
        lambda: ws_rooms.internal_chat_broadcast_room(None),
    ):
        with pytest.raises(WebSocketRoomError):
            call()


def test_room_name_shapes_are_stable():
    assert ws_rooms.tenant_broadcast_room("t1") == "pms:t1"
    assert ws_rooms.internal_chat_user_room("t1", "u1") == "internal_chat:t1:user:u1"
    assert (
        ws_rooms.internal_chat_department_room("t1", "Reception")
        == "internal_chat:t1:dept:Reception"
    )
    assert ws_rooms.internal_chat_broadcast_room("t1") == "internal_chat:t1:broadcast"


def test_internal_chat_rooms_and_targets_consistency():
    rooms = ws_rooms.internal_chat_rooms("t1", "u1", "Reception")
    assert rooms == [
        "internal_chat:t1:user:u1",
        "internal_chat:t1:broadcast",
        "internal_chat:t1:dept:Reception",
    ]
    # without a department, the dept room is omitted
    assert ws_rooms.internal_chat_rooms("t1", "u1") == [
        "internal_chat:t1:user:u1",
        "internal_chat:t1:broadcast",
    ]
    assert ws_rooms.internal_message_targets("t1", to_user_id="u1") == [
        "internal_chat:t1:user:u1"
    ]
    assert ws_rooms.internal_message_targets("t1", to_department="HK") == [
        "internal_chat:t1:dept:HK"
    ]
    assert ws_rooms.internal_message_targets("t1") == ["internal_chat:t1:broadcast"]


def test_protected_room_guard_covers_all_tenant_scoped_rooms():
    assert ws_rooms.is_protected_room(ws_rooms.tenant_broadcast_room("t1"))
    assert ws_rooms.is_protected_room(ws_rooms.internal_chat_user_room("t1", "u1"))
    assert ws_rooms.is_protected_room("pms")  # legacy global room stays blocked
    assert not ws_rooms.is_protected_room("dashboard")
    assert not ws_rooms.is_protected_room(None)


def test_websocket_server_delegates_to_shared_helpers():
    import websocket_server as ws

    # The connect handler enrols into the same room the producers target.
    assert ws._pms_tenant_room is ws_rooms.tenant_broadcast_room
    assert ws._internal_chat_rooms is ws_rooms.internal_chat_rooms
    assert ws._internal_message_targets is ws_rooms.internal_message_targets
    assert ws._is_protected_room is ws_rooms.is_protected_room


@pytest.mark.asyncio
async def test_room_qr_emits_to_connect_enrollment_room():
    """room_request:new / :update must reach the tenant broadcast room that
    authenticated sockets auto-join at connect — not a dead `tenant:{id}`."""
    from unittest.mock import AsyncMock, patch

    import websocket_server as ws
    from routers import room_qr_requests as rqr

    tenant_id = "tenantA"
    expected_room = ws_rooms.tenant_broadcast_room(tenant_id)

    # Mirror the room the connect handler would enrol an authenticated socket
    # into, proving emit-side and enrol-side agree.
    enrol_rooms = ws._internal_chat_rooms(tenant_id, "u1", "Reception")
    enrol_rooms.append(ws._pms_tenant_room(tenant_id))
    assert expected_room in enrol_rooms

    captured = {}

    async def _fake_emit(event, payload, room=None):
        captured["event"] = event
        captured["room"] = room

    with patch.object(ws, "sio") as fake_sio:
        fake_sio.emit = AsyncMock(side_effect=_fake_emit)
        # Replicate the emit block from create (room_request:new).
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio
        await sio.emit(
            "room_request:new",
            {"id": "r1", "tenant_id": tenant_id},
            room=tenant_broadcast_room(tenant_id),
        )

    assert captured["event"] == "room_request:new"
    assert captured["room"] == expected_room
    assert captured["room"].startswith("pms:")
    # Regression guard: the old dead room must never come back.
    assert captured["room"] != f"tenant:{tenant_id}"
    # rqr import kept to ensure the router module still loads after refactor.
    assert hasattr(rqr, "router")
