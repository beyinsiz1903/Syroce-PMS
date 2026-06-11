"""Centralized tenant-scoped WebSocket room-name generation.

Single source of truth for every tenant-scoped WebSocket room name used
across the realtime layer: socket.io connect-time enrolment, PMS
booking/room-status broadcasts, internal-chat DM/department/broadcast
routing, and the room-QR request notifications.

Why this module exists (Task #367 — consistency hardening, NOT an IDOR
fix; the core WS auth/handshake/tenant-binding is already centralized):
building room names by hand with f-strings scattered across emit points
risks (a) emitting to a room nobody is enrolled in — e.g. the room-QR
router used to emit to ``tenant:{id}`` while connect enrols clients into
``pms:{id}``, so those notifications reached no one — and (b) typo'ing the
tenant prefix on a future edit. Routing every producer and the connect-time
consumer through these helpers keeps the emit side and the enrolment side
byte-for-byte identical.

``tenant_id`` is a REQUIRED argument everywhere. A missing tenant would
collapse the tenant boundary (the whole point of these scoped rooms), so
the helpers refuse to build a room name without one instead of silently
producing ``pms:None``.
"""
from __future__ import annotations


class WebSocketRoomError(ValueError):
    """Raised when a tenant-scoped room name is requested without the
    identifiers needed to keep it tenant-isolated."""


# Canonical room-name prefixes. Kept here so the prefix string lives in
# exactly one place; the protected-room guards below compare against these
# same constants rather than re-typing the literal.
_PMS_PREFIX = "pms:"
_INTERNAL_CHAT_PREFIX = "internal_chat:"
# Legacy global PMS room (pre Task #43). No longer produced anywhere, but
# still treated as protected so a client cannot manually join it.
_LEGACY_PMS_ROOM = "pms"


def _require(value: str | None, name: str) -> str:
    if not value or not isinstance(value, str):
        raise WebSocketRoomError(
            f"{name} is required to build a tenant-scoped WebSocket room name"
        )
    return value


def tenant_broadcast_room(tenant_id: str) -> str:
    """Tenant-wide broadcast room.

    Authenticated sockets are auto-enrolled into this room at connect time,
    so it is the canonical destination for any tenant-scoped fan-out that
    should reach every connected client of the tenant: PMS booking and
    room-status updates as well as room-QR request notifications.
    """
    return f"{_PMS_PREFIX}{_require(tenant_id, 'tenant_id')}"


def internal_chat_user_room(tenant_id: str, user_id: str) -> str:
    """Per-user DM room within a tenant."""
    return (
        f"{_INTERNAL_CHAT_PREFIX}{_require(tenant_id, 'tenant_id')}"
        f":user:{_require(user_id, 'user_id')}"
    )


def internal_chat_department_room(tenant_id: str, department: str) -> str:
    """Per-department room within a tenant."""
    return (
        f"{_INTERNAL_CHAT_PREFIX}{_require(tenant_id, 'tenant_id')}"
        f":dept:{_require(department, 'department')}"
    )


def internal_chat_broadcast_room(tenant_id: str) -> str:
    """Tenant-wide internal-chat broadcast room."""
    return f"{_INTERNAL_CHAT_PREFIX}{_require(tenant_id, 'tenant_id')}:broadcast"


def internal_chat_rooms(
    tenant_id: str, user_id: str, department: str | None = None
) -> list[str]:
    """The full set of internal-chat rooms a user belongs to (DM,
    tenant broadcast, and — when known — their department room).

    Used both at connect time (enrolment) and by the protected-room guard
    so the membership computed for joining and for authorizing are derived
    from the exact same source.
    """
    rooms = [
        internal_chat_user_room(tenant_id, user_id),
        internal_chat_broadcast_room(tenant_id),
    ]
    if department:
        rooms.append(internal_chat_department_room(tenant_id, department))
    return rooms


def internal_message_targets(
    tenant_id: str,
    *,
    to_user_id: str | None = None,
    to_department: str | None = None,
) -> list[str]:
    """Resolve the tenant-scoped room set for an internal-chat event.

    Routing rules mirror the inbox query in messaging/router.py:
      - to_user_id provided  → DM, deliver only to that user's room
      - to_department provided → deliver to that department's room
      - neither               → broadcast to all users in the tenant
    """
    if to_user_id:
        return [internal_chat_user_room(tenant_id, to_user_id)]
    if to_department:
        return [internal_chat_department_room(tenant_id, to_department)]
    return [internal_chat_broadcast_room(tenant_id)]


def is_internal_chat_room(room: str) -> bool:
    """Whether a room name belongs to the protected internal-chat namespace."""
    return isinstance(room, str) and room.startswith(_INTERNAL_CHAT_PREFIX)


def is_protected_room(room: str) -> bool:
    """Whether a room name belongs to a tenant-scoped protected namespace.

    Tenant-scoped rooms (``internal_chat:{tenant_id}:*``, ``pms:{tenant_id}``)
    MUST never be joined manually by the client — the server enrols the
    socket at connect time based on the authenticated JWT identity. The
    legacy global ``pms`` room is also blocked so an unauthenticated or
    cross-tenant client cannot eavesdrop on the backwards-compat fallback.
    """
    if not isinstance(room, str):
        return False
    return (
        room.startswith(_INTERNAL_CHAT_PREFIX)
        or room.startswith(_PMS_PREFIX)
        or room == _LEGACY_PMS_ROOM
    )
