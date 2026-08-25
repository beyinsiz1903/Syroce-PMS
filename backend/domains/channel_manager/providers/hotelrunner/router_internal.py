"""
HotelRunner Router — Internal / Diagnostic Endpoints
=====================================================

Read-only diagnostic endpoints used by the Channel Manager UI:
  - PMS room types dropdown
  - Cached HR rooms (last fetch result, no live API call)
  - Local reservation cache
  - Sync log history
  - In-process API usage stats (no HTTP egress)

Mounted under the main `/api/channel-manager/hotelrunner` prefix by the
parent router.
"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from core.database import db
from core.security import get_current_user
from models.schemas import User

from .factory import get_provider

router = APIRouter()

# In-process micro-cache for /usage. The endpoint is polled by the CM dashboard
# every few seconds; rebuilding the provider + reading two timestamps from Mongo
# costs ~1s per call. A 30-second TTL is well below operator perception while
# slashing per-tenant load by ~30x.
_USAGE_CACHE: dict[str, tuple[float, dict]] = {}
_USAGE_TTL_SEC = 30.0


def _provider_room_number(event: dict[str, Any]) -> str:
    normalized = event.get("normalization_result") or {}
    value = normalized.get("provider_room_number")
    if value not in (None, ""):
        return str(value)
    rooms = (event.get("raw_payload") or {}).get("rooms") or []
    if rooms and isinstance(rooms[0], dict):
        return str(rooms[0].get("number") or rooms[0].get("room_number") or "")
    return ""


def _duration_ms(start: Any, end: Any) -> int:
    if not start or not end:
        return 0
    try:
        started_at = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        ended_at = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return max(0, int((ended_at - started_at).total_seconds() * 1000))
    except (TypeError, ValueError):
        return 0


def _reservation_view(
    event: dict[str, Any], booking: dict | None, imported: dict | None
) -> dict[str, Any]:
    """Project a unified ingest event without exposing its raw PII payload."""
    normalized = event.get("normalization_result") or {}
    provider_room = _provider_room_number(event)
    pms_room = str((booking or {}).get("room_number") or "")
    processing_status = str(event.get("processing_status") or "pending")
    return {
        "id": event.get("id"),
        "hr_number": event.get("external_reservation_id") or normalized.get("external_reservation_id", ""),
        "guest_name": normalized.get("guest_name", ""),
        "channel": normalized.get("source_system", "") or "hotelrunner",
        "channel_display": normalized.get("source_system", "") or "HotelRunner",
        "checkin_date": normalized.get("check_in", ""),
        "checkout_date": normalized.get("check_out", ""),
        "total": normalized.get("total_amount", 0),
        "currency": normalized.get("currency", "TRY"),
        "state": normalized.get("status", "confirmed"),
        "pms_status": "imported" if booking else (imported or {}).get("import_status", processing_status),
        "booking_status": (booking or {}).get("status"),
        "booking_id": (booking or {}).get("id"),
        "provider_room_number": provider_room,
        "pms_room_number": pms_room,
        "room_assignment_matches": bool(provider_room and pms_room and provider_room == pms_room),
        "room_type_code": normalized.get("room_type_code", ""),
        "event_type": event.get("event_type", ""),
        "received_via": event.get("received_via", ""),
        "received_at": event.get("received_at"),
        "processing_status": processing_status,
    }


def _event_log_view(event: dict[str, Any]) -> dict[str, Any]:
    processing_status = str(event.get("processing_status") or "pending")
    return {
        "id": event.get("id"),
        "status": (
            "success"
            if processing_status in {"processed", "duplicate"}
            else ("pending" if processing_status == "pending" else "error")
        ),
        "sync_type": event.get("event_type") or "reservation_event",
        "initiator": event.get("received_via") or "webhook",
        "records_synced": 1 if processing_status in {"processed", "duplicate"} else 0,
        "timestamp": event.get("received_at"),
        "duration_ms": _duration_ms(event.get("received_at"), event.get("processed_at")),
        "external_reservation_id": event.get("external_reservation_id", ""),
        "decision": event.get("decision_result", ""),
        "processing_status": processing_status,
        "error": event.get("processing_error"),
        "source": "unified_ingest",
    }


@router.get("/pms-room-types")
async def get_pms_room_types(current_user: User = Depends(get_current_user)):
    """Get distinct PMS room types for mapping dropdown."""
    types = await db.rooms.distinct("room_type", {"tenant_id": current_user.tenant_id})
    return {"room_types": [t for t in types if t]}


@router.get("/cached-rooms")
async def get_cached_hr_rooms(current_user: User = Depends(get_current_user)):
    """Get cached HotelRunner rooms from last fetch."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "cached_rooms": 1, "rooms_fetched_at": 1},
    )
    if not conn:
        return {"rooms": [], "fetched_at": None}
    return {
        "rooms": conn.get("cached_rooms", []),
        "fetched_at": conn.get("rooms_fetched_at"),
    }


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get latest HotelRunner reservations from the authoritative ingest flow."""
    events = (
        await db.raw_channel_events.find(
            {"tenant_id": current_user.tenant_id, "provider": "hotelrunner"},
            {
                "_id": 0,
                "id": 1,
                "external_reservation_id": 1,
                "event_type": 1,
                "received_via": 1,
                "received_at": 1,
                "processing_status": 1,
                "normalization_result": 1,
                "raw_payload.rooms.number": 1,
                "raw_payload.rooms.room_number": 1,
            },
        )
        .sort("received_at", -1)
        .to_list(500)
    )
    latest: dict[str, dict] = {}
    for event in events:
        external_id = str(event.get("external_reservation_id") or "")
        if external_id and external_id not in latest:
            latest[external_id] = event

    external_ids = list(latest)
    bookings: dict[str, dict] = {}
    imports: dict[str, dict] = {}
    if external_ids:
        booking_docs = await db.bookings.find(
            {
                "tenant_id": current_user.tenant_id,
                "external_reservation_id": {"$in": external_ids},
                "booking_source": {"$ne": "ota_unmatched_hold"},
            },
            {"_id": 0, "id": 1, "external_reservation_id": 1, "status": 1, "room_number": 1},
        ).to_list(500)
        bookings = {str(row.get("external_reservation_id")): row for row in booking_docs}
        import_docs = await db.imported_reservations.find(
            {"tenant_id": current_user.tenant_id, "external_reservation_id": {"$in": external_ids}},
            {"_id": 0, "external_reservation_id": 1, "import_status": 1},
        ).to_list(500)
        imports = {str(row.get("external_reservation_id")): row for row in import_docs}

    reservations = [
        _reservation_view(event, bookings.get(external_id), imports.get(external_id))
        for external_id, event in latest.items()
    ]
    if pms_status:
        reservations = [row for row in reservations if row["pms_status"] == pms_status]
    return {"reservations": reservations[:100], "count": min(len(reservations), 100), "source": "unified_ingest"}


@router.get("/sync-logs")
async def get_sync_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get real callback/pull processing history from unified ingest events."""
    events = (
        await db.raw_channel_events.find(
            {"tenant_id": current_user.tenant_id, "provider": "hotelrunner"},
            {
                "_id": 0,
                "id": 1,
                "external_reservation_id": 1,
                "event_type": 1,
                "received_via": 1,
                "received_at": 1,
                "processed_at": 1,
                "processing_status": 1,
                "processing_error": 1,
                "decision_result": 1,
            },
        )
        .sort("received_at", -1)
        .to_list(limit)
    )
    logs = [_event_log_view(event) for event in events]
    return {"logs": logs, "count": len(logs), "source": "unified_ingest"}


@router.get("/usage")
async def get_api_usage(current_user: User = Depends(get_current_user)):
    """Get HotelRunner API usage statistics (in-process counters, no HTTP egress)."""
    tenant_id = current_user.tenant_id
    now = time.monotonic()
    cached = _USAGE_CACHE.get(tenant_id)
    if cached and (now - cached[0]) < _USAGE_TTL_SEC:
        return cached[1]

    provider, conn = await get_provider(tenant_id)
    stats = provider.get_usage_stats()
    stats["last_sync_at"] = conn.get("last_sync_at")
    stats["connected_at"] = conn.get("connected_at")
    _USAGE_CACHE[tenant_id] = (now, stats)
    return stats
